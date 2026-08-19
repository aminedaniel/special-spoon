import { randomBytes } from "node:crypto";
import { createClient } from "@/lib/supabase/server";
import { createAdminClient } from "@/lib/supabase/admin";
import { onProposalSigned } from "@/lib/guarantee";
import { appUrl } from "@/lib/env";
import type {
  Estimate,
  EstimateLineItem,
  Lead,
  Organization,
  Proposal,
} from "@/lib/types";

/** 192 bits of entropy — a proposal link is the only credential a customer has. */
export function generatePublicToken(): string {
  return randomBytes(24).toString("base64url");
}

export function proposalUrl(token: string): string {
  return `${appUrl()}/p/${token}`;
}

export interface CreateProposalInput {
  cover_note?: string | null;
  terms?: string | null;
  deposit_amount_cents: number;
}

/**
 * Creates the proposal for an estimate if it does not exist yet, updates it if
 * it does, and marks the estimate `sent`. Idempotent on the token: re-sending
 * keeps the same customer-facing link.
 */
export async function sendProposal(
  orgId: string,
  estimateId: string,
  input: CreateProposalInput,
): Promise<Proposal> {
  const supabase = await createClient();
  const now = new Date().toISOString();

  const { data: existing } = await supabase
    .from("proposals")
    .select("*")
    .eq("estimate_id", estimateId)
    .eq("org_id", orgId)
    .maybeSingle();

  let proposal: Proposal;
  if (existing) {
    const { data, error } = await supabase
      .from("proposals")
      .update({
        cover_note: input.cover_note ?? null,
        terms: input.terms ?? null,
        deposit_amount_cents: input.deposit_amount_cents,
        sent_at: (existing as Proposal).sent_at ?? now,
      })
      .eq("id", (existing as Proposal).id)
      .select()
      .single();
    if (error) throw new Error(`Could not update the proposal: ${error.message}`);
    proposal = data as Proposal;
  } else {
    const { data, error } = await supabase
      .from("proposals")
      .insert({
        org_id: orgId,
        estimate_id: estimateId,
        public_token: generatePublicToken(),
        cover_note: input.cover_note ?? null,
        terms: input.terms ?? null,
        deposit_amount_cents: input.deposit_amount_cents,
        sent_at: now,
      })
      .select()
      .single();
    if (error) throw new Error(`Could not create the proposal: ${error.message}`);
    proposal = data as Proposal;
  }

  // Never walk a status backwards: a viewed or signed proposal stays where it
  // is. A declined one goes back out — a re-send is a second try at the job.
  const { data: estimate } = await supabase
    .from("estimates")
    .select("status")
    .eq("id", estimateId)
    .eq("org_id", orgId)
    .maybeSingle();
  const status = estimate ? (estimate as Estimate).status : null;
  if (status === "draft" || status === "declined") {
    await supabase.from("estimates").update({ status: "sent" }).eq("id", estimateId).eq("org_id", orgId);
    if (status === "declined") {
      await supabase.from("proposals").update({ declined_at: null }).eq("id", proposal.id);
    }
  }

  return proposal;
}

/** Everything the public proposal page renders. Customer-visible fields only. */
export interface PublicProposal {
  proposal: Pick<
    Proposal,
    | "id"
    | "public_token"
    | "cover_note"
    | "terms"
    | "deposit_amount_cents"
    | "sent_at"
    | "signed_at"
    | "signature_name"
    | "declined_at"
  >;
  estimate: Pick<Estimate, "id" | "title" | "subtotal_cents" | "tax_rate" | "tax_cents" | "total_cents" | "notes" | "created_at">;
  lineItems: Pick<EstimateLineItem, "id" | "name" | "description" | "unit" | "quantity" | "unit_price_cents" | "line_total_cents" | "position">[];
  lead: Pick<Lead, "contact_name" | "job_address" | "email">;
  org: Pick<Organization, "id" | "name" | "logo_url" | "brand_color" | "phone" | "email" | "address" | "stripe_connect_account_id">;
}

/**
 * Token lookup for the public page. Uses the service role deliberately: the
 * proposal tables have no anon RLS policy, so the only way in is through this
 * function, which returns a fixed, customer-safe projection.
 */
export async function getPublicProposal(token: string): Promise<PublicProposal | null> {
  const admin = createAdminClient();
  const { data, error } = await admin
    .from("proposals")
    .select(
      `id, public_token, cover_note, terms, deposit_amount_cents, sent_at, signed_at, signature_name, declined_at,
       estimate:estimates(id, title, subtotal_cents, tax_rate, tax_cents, total_cents, notes, created_at,
         lead:leads(contact_name, job_address, email),
         line_items:estimate_line_items(id, name, description, unit, quantity, unit_price_cents, line_total_cents, position)),
       org:organizations(id, name, logo_url, brand_color, phone, email, address, stripe_connect_account_id)`,
    )
    .eq("public_token", token)
    .maybeSingle();

  if (error || !data) return null;

  const row = data as unknown as {
    estimate: (PublicProposal["estimate"] & {
      lead: PublicProposal["lead"] | PublicProposal["lead"][];
      line_items: PublicProposal["lineItems"];
    }) | null;
    org: PublicProposal["org"] | PublicProposal["org"][] | null;
  } & PublicProposal["proposal"];

  const estimate = Array.isArray(row.estimate) ? row.estimate[0] : row.estimate;
  const org = Array.isArray(row.org) ? row.org[0] : row.org;
  if (!estimate || !org) return null;
  const lead = Array.isArray(estimate.lead) ? estimate.lead[0] : estimate.lead;

  return {
    // Listed field by field on purpose: this projection is what a customer
    // sees, so adding a column to `proposals` must never leak it by default.
    proposal: {
      id: row.id,
      public_token: row.public_token,
      cover_note: row.cover_note,
      terms: row.terms,
      deposit_amount_cents: row.deposit_amount_cents,
      sent_at: row.sent_at,
      signed_at: row.signed_at,
      signature_name: row.signature_name,
      declined_at: row.declined_at,
    },
    estimate: {
      id: estimate.id,
      title: estimate.title,
      subtotal_cents: estimate.subtotal_cents,
      tax_rate: estimate.tax_rate,
      tax_cents: estimate.tax_cents,
      total_cents: estimate.total_cents,
      notes: estimate.notes,
      created_at: estimate.created_at,
    },
    lineItems: [...(estimate.line_items ?? [])].sort((a, b) => a.position - b.position),
    lead,
    org,
  };
}

/** First view flips the estimate to `viewed`; later views only bump counters. */
export async function recordProposalView(token: string): Promise<void> {
  const admin = createAdminClient();
  const now = new Date().toISOString();

  const { data } = await admin
    .from("proposals")
    .select("id, estimate_id, org_id, first_viewed_at, view_count, signed_at")
    .eq("public_token", token)
    .maybeSingle();
  if (!data) return;

  const proposal = data as Pick<
    Proposal,
    "id" | "estimate_id" | "org_id" | "first_viewed_at" | "view_count" | "signed_at"
  >;

  await admin
    .from("proposals")
    .update({
      viewed_at: now,
      first_viewed_at: proposal.first_viewed_at ?? now,
      view_count: proposal.view_count + 1,
    })
    .eq("id", proposal.id);

  if (!proposal.signed_at) {
    await admin
      .from("estimates")
      .update({ status: "viewed" })
      .eq("id", proposal.estimate_id)
      .eq("status", "sent");
  }
}

export interface SignatureInput {
  signature_name: string;
  ip: string | null;
  userAgent: string | null;
}

export interface SignResult {
  ok: boolean;
  reason?: string;
  guaranteeMet?: boolean;
}

/**
 * Accepts a proposal: timestamps the signature, moves the estimate to `signed`,
 * and — the point of the whole guarantee mechanic — flips the org's guarantee
 * to `met` when the signature lands inside the window.
 */
export async function signProposal(token: string, input: SignatureInput): Promise<SignResult> {
  const admin = createAdminClient();
  const signedAt = new Date();

  const { data } = await admin
    .from("proposals")
    .select("id, org_id, estimate_id, signed_at, declined_at")
    .eq("public_token", token)
    .maybeSingle();
  if (!data) return { ok: false, reason: "Proposal not found." };

  const proposal = data as Pick<Proposal, "id" | "org_id" | "estimate_id" | "signed_at" | "declined_at">;
  if (proposal.signed_at) return { ok: true, reason: "Already signed." };

  const { error } = await admin
    .from("proposals")
    .update({
      signed_at: signedAt.toISOString(),
      signature_name: input.signature_name,
      signature_ip: input.ip,
      signature_user_agent: input.userAgent,
      declined_at: null,
    })
    .eq("id", proposal.id)
    .is("signed_at", null);
  if (error) return { ok: false, reason: "Could not record the signature." };

  await admin.from("estimates").update({ status: "signed" }).eq("id", proposal.estimate_id);

  const { data: orgRow } = await admin
    .from("organizations")
    .select("guarantee_started_at, guarantee_met_at, guarantee_status, billing_starts_at, guarantee_extended_at")
    .eq("id", proposal.org_id)
    .maybeSingle();

  let guaranteeMet = false;
  if (orgRow) {
    const patch = onProposalSigned(orgRow as Parameters<typeof onProposalSigned>[0], signedAt);
    if (patch) {
      await admin.from("organizations").update(patch).eq("id", proposal.org_id);
      guaranteeMet = true;
    }
  }

  return { ok: true, guaranteeMet };
}

export async function declineProposal(token: string): Promise<boolean> {
  const admin = createAdminClient();
  const { data } = await admin
    .from("proposals")
    .select("id, estimate_id, signed_at")
    .eq("public_token", token)
    .maybeSingle();
  if (!data) return false;
  const proposal = data as Pick<Proposal, "id" | "estimate_id" | "signed_at">;
  if (proposal.signed_at) return false;

  await admin.from("proposals").update({ declined_at: new Date().toISOString() }).eq("id", proposal.id);
  await admin.from("estimates").update({ status: "declined" }).eq("id", proposal.estimate_id);
  return true;
}
