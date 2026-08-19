import { createClient } from "@/lib/supabase/server";
import { computeTotals, lineTotalCents } from "@/lib/money";
import type {
  Estimate,
  EstimateDetail,
  EstimateLineItem,
  EstimateStatus,
  Lead,
  Proposal,
} from "@/lib/types";

export interface LeadInput {
  contact_name: string;
  email?: string | null;
  phone?: string | null;
  job_address?: string | null;
  source?: string | null;
  notes?: string | null;
}

export interface LineItemInput {
  price_book_item_id?: string | null;
  name: string;
  description?: string | null;
  unit: string;
  quantity: number;
  unit_price_cents: number;
  /** Phase 2 seam: AI-assembled items arrive flagged for review. */
  ai_confidence?: number | null;
  needs_review?: boolean;
}

export interface EstimateListRow extends Estimate {
  lead: Pick<Lead, "id" | "contact_name" | "job_address">;
  proposal: Pick<Proposal, "public_token" | "sent_at" | "viewed_at" | "signed_at"> | null;
}

export async function listEstimates(orgId: string): Promise<EstimateListRow[]> {
  const supabase = await createClient();
  const { data, error } = await supabase
    .from("estimates")
    .select(
      "*, lead:leads(id, contact_name, job_address), proposal:proposals(public_token, sent_at, viewed_at, signed_at)",
    )
    .eq("org_id", orgId)
    .order("created_at", { ascending: false });
  if (error) throw new Error(`Could not load estimates: ${error.message}`);
  return (data ?? []).map((row) => {
    const { proposal, ...rest } = row as Omit<EstimateListRow, "proposal"> & {
      proposal: EstimateListRow["proposal"] | EstimateListRow["proposal"][] | null;
    };
    return {
      ...rest,
      proposal: Array.isArray(proposal) ? (proposal[0] ?? null) : proposal,
    } as EstimateListRow;
  });
}

export async function getEstimate(orgId: string, estimateId: string): Promise<EstimateDetail | null> {
  const supabase = await createClient();
  const { data, error } = await supabase
    .from("estimates")
    .select("*, lead:leads(*), line_items:estimate_line_items(*), proposal:proposals(*)")
    .eq("org_id", orgId)
    .eq("id", estimateId)
    .maybeSingle();
  if (error) throw new Error(`Could not load estimate: ${error.message}`);
  if (!data) return null;

  const row = data as Omit<EstimateDetail, "proposal"> & {
    proposal: Proposal | Proposal[] | null;
    line_items: EstimateLineItem[];
  };
  const proposal = Array.isArray(row.proposal) ? (row.proposal[0] ?? null) : row.proposal;
  return {
    ...row,
    proposal,
    line_items: [...(row.line_items ?? [])].sort((a, b) => a.position - b.position),
  } as EstimateDetail;
}

export async function createLead(orgId: string, input: LeadInput): Promise<Lead> {
  const supabase = await createClient();
  const { data, error } = await supabase
    .from("leads")
    .insert({ ...input, org_id: orgId })
    .select()
    .single();
  if (error) throw new Error(`Could not save the customer: ${error.message}`);
  return data as Lead;
}

export async function createEstimate(
  orgId: string,
  userId: string,
  args: { lead: LeadInput; title: string; tax_rate: number; notes?: string | null },
): Promise<Estimate> {
  const supabase = await createClient();
  const lead = await createLead(orgId, args.lead);
  const { data, error } = await supabase
    .from("estimates")
    .insert({
      org_id: orgId,
      lead_id: lead.id,
      title: args.title,
      tax_rate: args.tax_rate,
      notes: args.notes ?? null,
      created_by: userId,
    })
    .select()
    .single();
  if (error) throw new Error(`Could not create the estimate: ${error.message}`);
  return data as Estimate;
}

export async function updateEstimateMeta(
  orgId: string,
  estimateId: string,
  patch: { title?: string; tax_rate?: number; notes?: string | null },
): Promise<void> {
  const supabase = await createClient();
  const { error } = await supabase
    .from("estimates")
    .update(patch)
    .eq("id", estimateId)
    .eq("org_id", orgId);
  if (error) throw new Error(`Could not update the estimate: ${error.message}`);
  if (patch.tax_rate !== undefined) await recalculateTotals(orgId, estimateId);
}

export async function updateLead(orgId: string, leadId: string, patch: Partial<LeadInput>): Promise<void> {
  const supabase = await createClient();
  const { error } = await supabase.from("leads").update(patch).eq("id", leadId).eq("org_id", orgId);
  if (error) throw new Error(`Could not update the customer: ${error.message}`);
}

export async function addLineItem(
  orgId: string,
  estimateId: string,
  input: LineItemInput,
): Promise<EstimateLineItem> {
  const supabase = await createClient();
  await assertEstimateEditable(orgId, estimateId);

  const { data: existing } = await supabase
    .from("estimate_line_items")
    .select("position")
    .eq("estimate_id", estimateId)
    .order("position", { ascending: false })
    .limit(1);
  const position = ((existing?.[0]?.position as number | undefined) ?? -1) + 1;

  const { data, error } = await supabase
    .from("estimate_line_items")
    .insert({
      estimate_id: estimateId,
      price_book_item_id: input.price_book_item_id ?? null,
      name: input.name,
      description: input.description ?? null,
      unit: input.unit,
      quantity: input.quantity,
      unit_price_cents: input.unit_price_cents,
      line_total_cents: lineTotalCents(input.quantity, input.unit_price_cents),
      position,
      ai_confidence: input.ai_confidence ?? null,
      needs_review: input.needs_review ?? false,
    })
    .select()
    .single();
  if (error) throw new Error(`Could not add the line item: ${error.message}`);

  await recalculateTotals(orgId, estimateId);
  return data as EstimateLineItem;
}

export async function updateLineItem(
  orgId: string,
  estimateId: string,
  lineItemId: string,
  patch: { quantity?: number; unit_price_cents?: number; name?: string; description?: string | null },
): Promise<void> {
  const supabase = await createClient();
  await assertEstimateEditable(orgId, estimateId);

  const { data: current, error: readError } = await supabase
    .from("estimate_line_items")
    .select("*")
    .eq("id", lineItemId)
    .eq("estimate_id", estimateId)
    .maybeSingle();
  if (readError || !current) throw new Error("Line item not found.");

  const row = current as EstimateLineItem;
  const quantity = patch.quantity ?? row.quantity;
  const unitPrice = patch.unit_price_cents ?? row.unit_price_cents;

  const { error } = await supabase
    .from("estimate_line_items")
    .update({
      ...patch,
      quantity,
      unit_price_cents: unitPrice,
      line_total_cents: lineTotalCents(quantity, unitPrice),
      needs_review: false,
    })
    .eq("id", lineItemId)
    .eq("estimate_id", estimateId);
  if (error) throw new Error(`Could not update the line item: ${error.message}`);

  await recalculateTotals(orgId, estimateId);
}

export async function deleteLineItem(orgId: string, estimateId: string, lineItemId: string): Promise<void> {
  const supabase = await createClient();
  await assertEstimateEditable(orgId, estimateId);
  const { error } = await supabase
    .from("estimate_line_items")
    .delete()
    .eq("id", lineItemId)
    .eq("estimate_id", estimateId);
  if (error) throw new Error(`Could not remove the line item: ${error.message}`);
  await recalculateTotals(orgId, estimateId);
}

/** Single place totals are written, so the stored numbers always match the lines. */
export async function recalculateTotals(orgId: string, estimateId: string): Promise<void> {
  const supabase = await createClient();
  const { data: estimate, error: estimateError } = await supabase
    .from("estimates")
    .select("tax_rate")
    .eq("id", estimateId)
    .eq("org_id", orgId)
    .maybeSingle();
  if (estimateError || !estimate) throw new Error("Estimate not found.");

  const { data: items } = await supabase
    .from("estimate_line_items")
    .select("quantity, unit_price_cents")
    .eq("estimate_id", estimateId);

  const totals = computeTotals((items ?? []) as { quantity: number; unit_price_cents: number }[], Number(
    (estimate as { tax_rate: number }).tax_rate,
  ));

  const { error } = await supabase
    .from("estimates")
    .update(totals)
    .eq("id", estimateId)
    .eq("org_id", orgId);
  if (error) throw new Error(`Could not recalculate totals: ${error.message}`);
}

export async function setEstimateStatus(
  orgId: string,
  estimateId: string,
  status: EstimateStatus,
): Promise<void> {
  const supabase = await createClient();
  const { error } = await supabase
    .from("estimates")
    .update({ status })
    .eq("id", estimateId)
    .eq("org_id", orgId);
  if (error) throw new Error(`Could not update status: ${error.message}`);
}

/** A signed estimate is a contract — it stops being editable. */
async function assertEstimateEditable(orgId: string, estimateId: string): Promise<void> {
  const supabase = await createClient();
  const { data } = await supabase
    .from("estimates")
    .select("status")
    .eq("id", estimateId)
    .eq("org_id", orgId)
    .maybeSingle();
  if (!data) throw new Error("Estimate not found.");
  if ((data as { status: EstimateStatus }).status === "signed") {
    throw new Error("This estimate has been signed and can no longer be edited.");
  }
}

export { pipelineStats, type PipelineStats } from "@/lib/pipeline";
