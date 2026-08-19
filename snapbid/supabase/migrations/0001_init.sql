-- ===========================================================================
-- SnapBid — Phase 0 + Phase 1 schema
--
-- Money is stored as integer cents everywhere (never float). Quantities are
-- numeric(12,3) so "3.5 squares" works.
-- ===========================================================================

create extension if not exists "pgcrypto";

-- --- enums -----------------------------------------------------------------
create type trade            as enum ('roofing', 'remodeling');
create type user_role        as enum ('owner', 'staff');
create type guarantee_status as enum ('active', 'met', 'comped', 'extended');
create type estimate_status  as enum ('draft', 'sent', 'viewed', 'signed', 'declined');
create type payment_type     as enum ('deposit', 'subscription');
create type payment_status   as enum ('pending', 'succeeded', 'failed', 'refunded');
create type follow_up_channel as enum ('sms', 'email');
create type follow_up_status  as enum ('scheduled', 'sent', 'cancelled', 'failed');

-- --- organizations ---------------------------------------------------------
create table organizations (
  id                        uuid primary key default gen_random_uuid(),
  name                      text        not null,
  trade                     trade       not null,
  logo_url                  text,
  brand_color               text        not null default '#1d4ed8',
  phone                     text,
  email                     text,
  address                   text,
  default_tax_rate          numeric(6,4) not null default 0,      -- 0.0875 = 8.75%
  default_terms             text,
  default_deposit_percent   numeric(5,2) not null default 25,     -- percent of total
  onboarding_completed_at   timestamptz,

  -- billing / 14-day guarantee engine
  stripe_customer_id        text,
  stripe_subscription_id    text,
  stripe_connect_account_id text,
  guarantee_started_at      timestamptz,
  guarantee_met_at          timestamptz,
  guarantee_status          guarantee_status not null default 'active',
  billing_starts_at         timestamptz,
  guarantee_extended_at     timestamptz,   -- set when the one-time extension is used

  created_at                timestamptz not null default now(),
  updated_at                timestamptz not null default now()
);

-- --- users (profile row mirroring auth.users) ------------------------------
create table users (
  id          uuid primary key references auth.users(id) on delete cascade,
  org_id      uuid not null references organizations(id) on delete cascade,
  email       text not null,
  full_name   text,
  role        user_role not null default 'owner',
  created_at  timestamptz not null default now()
);
create index users_org_id_idx on users(org_id);

-- --- price book ------------------------------------------------------------
create table price_book_items (
  id               uuid primary key default gen_random_uuid(),
  org_id           uuid not null references organizations(id) on delete cascade,
  name             text not null,
  description      text,
  category         text not null default 'General',
  unit             text not null default 'ea',
  unit_price_cents integer not null check (unit_price_cents >= 0),
  trade            trade,
  is_active        boolean not null default true,
  created_at       timestamptz not null default now(),
  updated_at       timestamptz not null default now()
);
create index price_book_items_org_idx on price_book_items(org_id, is_active);

-- --- leads -----------------------------------------------------------------
create table leads (
  id            uuid primary key default gen_random_uuid(),
  org_id        uuid not null references organizations(id) on delete cascade,
  contact_name  text not null,
  email         text,
  phone         text,
  job_address   text,
  source        text,
  notes         text,
  created_at    timestamptz not null default now()
);
create index leads_org_idx on leads(org_id);

-- --- estimates -------------------------------------------------------------
create table estimates (
  id             uuid primary key default gen_random_uuid(),
  org_id         uuid not null references organizations(id) on delete cascade,
  lead_id        uuid not null references leads(id) on delete cascade,
  title          text not null default 'Estimate',
  status         estimate_status not null default 'draft',
  subtotal_cents integer not null default 0,
  tax_rate       numeric(6,4) not null default 0,
  tax_cents      integer not null default 0,
  total_cents    integer not null default 0,
  notes          text,
  created_by     uuid references users(id) on delete set null,
  created_at     timestamptz not null default now(),
  updated_at     timestamptz not null default now()
);
create index estimates_org_status_idx on estimates(org_id, status);

create table estimate_line_items (
  id                  uuid primary key default gen_random_uuid(),
  estimate_id         uuid not null references estimates(id) on delete cascade,
  price_book_item_id  uuid references price_book_items(id) on delete set null,
  name                text not null,
  description         text,
  unit                text not null default 'ea',
  quantity            numeric(12,3) not null check (quantity > 0),
  unit_price_cents    integer not null check (unit_price_cents >= 0),
  line_total_cents    integer not null,
  position            integer not null default 0,
  -- Phase 2 seam: AI-extracted items carry a confidence score and review flag.
  ai_confidence       numeric(4,3),
  needs_review        boolean not null default false,
  created_at          timestamptz not null default now()
);
create index estimate_line_items_estimate_idx on estimate_line_items(estimate_id, position);

-- --- proposals -------------------------------------------------------------
create table proposals (
  id                    uuid primary key default gen_random_uuid(),
  org_id                uuid not null references organizations(id) on delete cascade,
  estimate_id           uuid not null unique references estimates(id) on delete cascade,
  public_token          text not null unique,
  cover_note            text,
  terms                 text,
  deposit_amount_cents  integer not null default 0 check (deposit_amount_cents >= 0),
  sent_at               timestamptz,
  first_viewed_at       timestamptz,
  viewed_at             timestamptz,
  view_count            integer not null default 0,
  signed_at             timestamptz,
  signature_name        text,
  signature_ip          text,
  signature_user_agent  text,
  declined_at           timestamptz,
  created_at            timestamptz not null default now(),
  updated_at            timestamptz not null default now()
);
create index proposals_org_idx on proposals(org_id);

-- --- payments --------------------------------------------------------------
create table payments (
  id            uuid primary key default gen_random_uuid(),
  org_id        uuid not null references organizations(id) on delete cascade,
  proposal_id   uuid references proposals(id) on delete set null,
  type          payment_type not null,
  amount_cents  integer not null,
  currency      text not null default 'usd',
  status        payment_status not null default 'pending',
  stripe_ref    text,
  created_at    timestamptz not null default now(),
  updated_at    timestamptz not null default now()
);
-- Plain (not partial) unique constraint: the Stripe webhook upserts on this
-- column, and ON CONFLICT cannot infer a partial index. Postgres treats NULLs
-- as distinct, so rows without a Stripe reference are still allowed.
alter table payments add constraint payments_stripe_ref_key unique (stripe_ref);
create index payments_org_idx on payments(org_id);

-- --- follow_ups (Phase 3 seam: table exists, engine not built yet) ----------
create table follow_ups (
  id            uuid primary key default gen_random_uuid(),
  org_id        uuid not null references organizations(id) on delete cascade,
  proposal_id   uuid not null references proposals(id) on delete cascade,
  channel       follow_up_channel not null,
  step          integer not null default 1,
  scheduled_for timestamptz not null,
  sent_at       timestamptz,
  status        follow_up_status not null default 'scheduled',
  body          text,
  created_at    timestamptz not null default now()
);
create index follow_ups_due_idx on follow_ups(status, scheduled_for);

-- --- updated_at triggers ---------------------------------------------------
create or replace function set_updated_at() returns trigger
language plpgsql as $$
begin
  new.updated_at = now();
  return new;
end;
$$;

create trigger organizations_updated_at   before update on organizations   for each row execute function set_updated_at();
create trigger price_book_items_updated_at before update on price_book_items for each row execute function set_updated_at();
create trigger estimates_updated_at        before update on estimates        for each row execute function set_updated_at();
create trigger proposals_updated_at        before update on proposals        for each row execute function set_updated_at();
create trigger payments_updated_at         before update on payments         for each row execute function set_updated_at();

-- ===========================================================================
-- Row Level Security: every row is reachable only from its own org.
--
-- current_org_id() is SECURITY DEFINER so that reading `users` from inside a
-- policy on `users` does not recurse through that same policy.
-- ===========================================================================
create or replace function current_org_id() returns uuid
language sql stable security definer set search_path = public as $$
  select org_id from public.users where id = auth.uid();
$$;

alter table organizations     enable row level security;
alter table users             enable row level security;
alter table price_book_items  enable row level security;
alter table leads             enable row level security;
alter table estimates         enable row level security;
alter table estimate_line_items enable row level security;
alter table proposals         enable row level security;
alter table payments          enable row level security;
alter table follow_ups        enable row level security;

create policy org_self_read on organizations
  for select using (id = current_org_id());
create policy org_self_write on organizations
  for update using (id = current_org_id()) with check (id = current_org_id());

create policy users_same_org on users
  for select using (org_id = current_org_id());
create policy users_self_update on users
  for update using (id = auth.uid()) with check (id = auth.uid());

-- Org-scoped tables share one policy shape.
create policy pbi_org  on price_book_items for all using (org_id = current_org_id()) with check (org_id = current_org_id());
create policy leads_org on leads            for all using (org_id = current_org_id()) with check (org_id = current_org_id());
create policy est_org   on estimates        for all using (org_id = current_org_id()) with check (org_id = current_org_id());
create policy prop_org  on proposals        for all using (org_id = current_org_id()) with check (org_id = current_org_id());
create policy pay_org   on payments         for all using (org_id = current_org_id()) with check (org_id = current_org_id());
create policy fu_org    on follow_ups       for all using (org_id = current_org_id()) with check (org_id = current_org_id());

-- Line items inherit their estimate's org.
create policy eli_org on estimate_line_items for all
  using (exists (select 1 from estimates e where e.id = estimate_id and e.org_id = current_org_id()))
  with check (exists (select 1 from estimates e where e.id = estimate_id and e.org_id = current_org_id()));

-- NOTE: the public proposal page (/p/<token>) is deliberately NOT exposed via
-- an anon RLS policy. It is served by a server route using the service-role
-- key, which looks the token up and returns only the fields a customer may
-- see. That keeps token-guessing surface off the database API entirely.
