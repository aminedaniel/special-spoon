# SnapBid

An estimate-to-close engine for specialty trade contractors: a job-site visit
becomes a priced, branded proposal in minutes, and the proposal collects a
signature and a deposit on its own.

This repository covers the first two phases of the build blueprint:

- **Phase 0 — scaffold.** Next.js (App Router) + Tailwind + Supabase auth, org/user
  model, logged-in dashboard shell.
- **Phase 1 — estimate → proposal → deposit, no AI yet.** Trade onboarding with a
  seeded price book, price-book CRUD + CSV import/export, a manual estimate builder,
  a branded public proposal page with PDF, Stripe deposit + e-signature, and the
  14-day guarantee engine wired into billing.

Phases 2–4 (AI intake, follow-up engine) are **not** built. The seams they slot into
are marked in the code and listed at the bottom of this file.

---

## 1. What you need

| Service | Why | Free to start |
|---|---|---|
| [Supabase](https://supabase.com) project | Postgres, auth, file storage | yes |
| [Stripe](https://stripe.com) account | subscription billing + job deposits | yes (test mode) |
| Node 20+ | build & run | — |

## 2. Set up Supabase

1. Create a project, then open **SQL Editor** and run, in order:
   - `supabase/migrations/0001_init.sql` — schema, enums, RLS policies
   - `supabase/migrations/0002_storage.sql` — `branding` and `job-photos` buckets
2. **Authentication → Providers → Email**: enable email/password.
   For local development also turn **Confirm email** *off* — otherwise signup
   cannot hand you a session and you have to confirm by email before signing in.
3. **Project Settings → API**: copy the project URL, the `anon` key, and the
   `service_role` key.

The service-role key bypasses RLS. It is used in exactly four places — signup
provisioning, the public proposal page, the Stripe webhook, and the guarantee cron
— and never reaches the browser.

## 3. Set up Stripe

1. **Products → add a product**, e.g. "SnapBid" with a **recurring monthly** price
   ($299). Copy the price ID (`price_...`) into `STRIPE_SUBSCRIPTION_PRICE_ID`.
2. **Developers → API keys**: copy the secret key.
3. **Developers → Webhooks**: add an endpoint at `https://<your-domain>/api/webhooks/stripe`
   listening for `checkout.session.completed`, `invoice.paid`,
   `invoice.payment_failed`. Copy the signing secret into `STRIPE_WEBHOOK_SECRET`.

   Locally: `stripe listen --forward-to localhost:3000/api/webhooks/stripe`.

Optional:

- `STRIPE_COMP_COUPON_ID` — a 100%-off, one-month coupon. When set, a comped
  guarantee applies it to the subscription so the free month is literal rather
  than only deferred.
- **Stripe Connect** — set `organizations.stripe_connect_account_id` for an org and
  deposits settle into that contractor's own account (destination charge). Without
  it, deposits land on the platform account and you pay contractors out manually.

## 4. Run it

```bash
git clone https://github.com/<owner>/snapbid.git
cd snapbid
cp .env.example .env.local     # then fill in the values
npm install
npm run dev                    # http://localhost:3000
```

Checks:

```bash
npm run typecheck   # tsc --noEmit
npm run lint        # eslint
npm test            # vitest — money, guarantee engine, CSV, PDF, pipeline
npm run build       # production build
```

## 5. Walking through the whole flow

1. **Sign up** at `/signup` (business name, your name, email, password).
2. **Onboarding** (`/onboarding`): pick roofing or remodeling — that seeds the price
   book from `src/lib/seed/price-books.ts` (28 roofing / 38 remodeling line items)
   and sets the default terms for that trade. Add branding (logo, color) and
   defaults (sales tax %, deposit %). Finishing sets
   `guarantee_started_at = now`, `billing_starts_at = now + 14 days`,
   `guarantee_status = active`.
3. **Card capture** (`/onboarding/billing`): Stripe Checkout in subscription mode with
   `trial_end = billing_starts_at`, so a card is on file and **nothing is charged
   today**. Skippable if Stripe is not configured.
4. **Price book** (`/price-book`): edit any seeded price, add items, import a CSV
   (`name, category, unit, price`, with `item`/`rate`/`uom` understood as aliases),
   export a CSV.
5. **New estimate** (`/estimates/new`): customer + job, then add line items from the
   price book (with a per-job price override) or as custom lines. Totals recalculate
   server-side on every change.
6. **Create the proposal link**: cover note, deposit amount (pre-filled from your
   default %), terms. That publishes `/p/<token>` and moves the estimate to `sent`.
7. **Open the proposal link** in another browser — the estimate flips to `viewed` and
   the contractor's view counter ticks. Download the PDF from the same page.
8. **Accept it**: type a name, tick the box. That timestamps `signed_at` with the
   signer's IP and user agent, locks the estimate, and — if the signature lands inside
   the guarantee window — flips the org to `guarantee_status = met`. If a deposit was
   requested, the customer goes straight to Stripe Checkout.
9. **Dashboard** shows the pipeline by status, win rate, signed and outstanding value,
   and the live guarantee banner.

### Testing the guarantee engine

The daily sweep is a route, so you can run it by hand:

```bash
curl -H "Authorization: Bearer $CRON_SECRET" http://localhost:3000/api/cron/guarantee
```

To watch it act, backdate an account in the Supabase SQL editor:

```sql
update organizations
set guarantee_started_at = now() - interval '15 days',
    billing_starts_at    = now() - interval '1 day',
    guarantee_status     = 'active';
```

Then run the curl above: with no signed proposal the account moves to `extended`,
the first month is comped, and `billing_starts_at` is pushed out 14 more days (once).
On Vercel this runs daily at 09:00 UTC via `vercel.json`; Vercel Cron sends
`Authorization: Bearer $CRON_SECRET` automatically when that env var is set.

Guarantee states:

| status | meaning |
|---|---|
| `active` | inside the original 14-day window |
| `met` | a proposal was signed inside the window; billing proceeds normally |
| `extended` | window lapsed unmet — first month comped, window pushed out 14 days (once) |
| `comped` | the extended window also lapsed; comp stands, no further extension |

## 6. Deploying

Vercel + Supabase, no other infrastructure:

1. Import this repository into Vercel. The app is at the repository root, so
   leave **Root Directory** alone.
2. Add every variable from `.env.example` in **Settings → Environment Variables**,
   with `NEXT_PUBLIC_APP_URL` set to the real domain (proposal links are built from it).
3. Deploy. `vercel.json` registers the daily guarantee cron.
4. Point the Stripe webhook at `https://<domain>/api/webhooks/stripe`.

## 7. How the code is laid out

```
src/
  app/
    (app)/            signed-in shell: dashboard, estimates, price book, settings
    p/[token]/        public proposal page + PDF route (no login)
    api/              sign, decline, deposit, Stripe webhook, guarantee cron
    onboarding/       trade pick, branding, card capture
  components/         shared UI
  lib/
    db/               typed data-access layer — the only place queries live
    guarantee.ts      pure 14-day guarantee state machine (fully unit-tested)
    money.ts          integer-cent math; no floats touch a price
    pdf.ts            proposal PDF (pdf-lib, no headless browser)
    csv.ts            price-book import/export
    seed/             trade price-book templates + default terms
supabase/
  migrations/         schema + RLS, storage buckets
  seed/               the trade templates as CSVs (generated; keep in sync with
                      `npm run export:templates`)
tests/                vitest suites for the pure logic
```

Design rules the code sticks to:

- **Money is integer cents, end to end.** Line totals round once, then sum, so the
  printed lines always add up to the printed subtotal.
- **RLS is the enforcement point.** Every signed-in query runs as the user; the app
  never hand-filters by `org_id` as its only defense.
- **The public proposal has no anon RLS policy.** `/p/<token>` is served by a
  server-side lookup that returns a fixed, customer-safe projection, so a guessed
  token cannot reach the database API.
- **A signed estimate is locked.** It is the agreement at that point.

## 8. Seams left for later phases

| Phase | Already in place | Still to build |
|---|---|---|
| 2 — AI generation | `job-photos` storage bucket; `estimate_line_items.ai_confidence` + `needs_review` (surfaced as a "Check this one" flag in the builder); `addLineItem` accepts AI-assembled items | photo/voice intake, transcription, multimodal scope extraction to strict JSON, price-book matching, review screen |
| 3 — Follow-ups | `follow_ups` table (channel, step, scheduled_for, status); proposal `sent_at` / `first_viewed_at` / `signed_at` are the triggers and the stop conditions | Twilio + email senders, sequence scheduler, per-org templates |
| 4 — Polish | pipeline stats + win rate, self-serve onboarding, trade templates, PWA manifest | deeper analytics, richer reporting |

Not built on purpose, per the blueprint: scheduling, dispatch, crew management, an
invoicing suite, inventory, accounting, multi-location.
