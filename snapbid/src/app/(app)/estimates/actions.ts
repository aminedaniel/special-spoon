"use server";

import { redirect } from "next/navigation";
import { revalidatePath } from "next/cache";
import { z } from "zod";
import { requireSession } from "@/lib/db/session";
import {
  addLineItem,
  createEstimate,
  deleteLineItem,
  getEstimate,
  updateEstimateMeta,
  updateLead,
  updateLineItem,
} from "@/lib/db/estimates";
import { listPriceBookItems } from "@/lib/db/price-book";
import { sendProposal } from "@/lib/db/proposals";
import { parseMoneyToCents, parseQuantity, percentToRate } from "@/lib/money";

export interface FormState {
  error?: string;
  notice?: string;
}

const newEstimateSchema = z.object({
  contact_name: z.string().trim().min(2, "Who is this for?"),
  email: z.string().trim().email("Enter a valid email.").optional().or(z.literal("")),
  phone: z.string().trim().max(40).optional().or(z.literal("")),
  job_address: z.string().trim().max(200).optional().or(z.literal("")),
  source: z.string().trim().max(60).optional().or(z.literal("")),
  title: z.string().trim().min(2, "Give the job a title."),
  tax_percent: z.string().optional(),
  notes: z.string().trim().max(2000).optional().or(z.literal("")),
});

export async function createEstimateAction(_prev: FormState, formData: FormData): Promise<FormState> {
  const session = await requireSession();
  const parsed = newEstimateSchema.safeParse({
    contact_name: formData.get("contact_name"),
    email: formData.get("email") ?? "",
    phone: formData.get("phone") ?? "",
    job_address: formData.get("job_address") ?? "",
    source: formData.get("source") ?? "",
    title: formData.get("title"),
    tax_percent: formData.get("tax_percent") ?? "0",
    notes: formData.get("notes") ?? "",
  });
  if (!parsed.success) return { error: parsed.error.issues[0].message };

  const taxRate = percentToRate(parsed.data.tax_percent || "0");
  if (taxRate === null) return { error: "Sales tax must be a percentage between 0 and 100." };

  let estimateId: string;
  try {
    const estimate = await createEstimate(session.org.id, session.userId, {
      lead: {
        contact_name: parsed.data.contact_name,
        email: parsed.data.email || null,
        phone: parsed.data.phone || null,
        job_address: parsed.data.job_address || null,
        source: parsed.data.source || null,
      },
      title: parsed.data.title,
      tax_rate: taxRate,
      notes: parsed.data.notes || null,
    });
    estimateId = estimate.id;
  } catch (error) {
    return { error: error instanceof Error ? error.message : "Could not create the estimate." };
  }

  redirect(`/estimates/${estimateId}`);
}

export async function addLineItemAction(_prev: FormState, formData: FormData): Promise<FormState> {
  const session = await requireSession();
  const estimateId = String(formData.get("estimate_id") ?? "");
  const priceBookItemId = String(formData.get("price_book_item_id") ?? "");
  const quantity = parseQuantity(String(formData.get("quantity") ?? ""));

  if (!estimateId) return { error: "Missing estimate." };
  if (quantity === null || quantity <= 0) return { error: "Enter a quantity greater than zero." };

  try {
    if (priceBookItemId) {
      const items = await listPriceBookItems(session.org.id);
      const item = items.find((candidate) => candidate.id === priceBookItemId);
      if (!item) return { error: "That price-book item is no longer available." };

      // A custom price on this job overrides the book without changing the book.
      const overrideCents = parseMoneyToCents(String(formData.get("unit_price") ?? ""));
      await addLineItem(session.org.id, estimateId, {
        price_book_item_id: item.id,
        name: item.name,
        description: item.description,
        unit: item.unit,
        quantity,
        unit_price_cents: overrideCents ?? item.unit_price_cents,
      });
    } else {
      const name = String(formData.get("name") ?? "").trim();
      const cents = parseMoneyToCents(String(formData.get("unit_price") ?? ""));
      if (!name) return { error: "Give the custom line a name." };
      if (cents === null || cents < 0) return { error: "Enter a valid price." };

      await addLineItem(session.org.id, estimateId, {
        name,
        description: String(formData.get("description") ?? "").trim() || null,
        unit: String(formData.get("unit") ?? "ea").trim() || "ea",
        quantity,
        unit_price_cents: cents,
      });
    }
  } catch (error) {
    return { error: error instanceof Error ? error.message : "Could not add the line item." };
  }

  revalidatePath(`/estimates/${estimateId}`);
  return { notice: "Line added." };
}

export async function updateLineItemAction(formData: FormData): Promise<void> {
  const session = await requireSession();
  const estimateId = String(formData.get("estimate_id") ?? "");
  const lineItemId = String(formData.get("line_item_id") ?? "");
  const quantity = parseQuantity(String(formData.get("quantity") ?? ""));
  const cents = parseMoneyToCents(String(formData.get("unit_price") ?? ""));
  if (!estimateId || !lineItemId || quantity === null || quantity <= 0 || cents === null) return;

  await updateLineItem(session.org.id, estimateId, lineItemId, {
    quantity,
    unit_price_cents: cents,
  });
  revalidatePath(`/estimates/${estimateId}`);
}

export async function deleteLineItemAction(formData: FormData): Promise<void> {
  const session = await requireSession();
  const estimateId = String(formData.get("estimate_id") ?? "");
  const lineItemId = String(formData.get("line_item_id") ?? "");
  if (!estimateId || !lineItemId) return;

  await deleteLineItem(session.org.id, estimateId, lineItemId);
  revalidatePath(`/estimates/${estimateId}`);
}

export async function updateEstimateAction(_prev: FormState, formData: FormData): Promise<FormState> {
  const session = await requireSession();
  const estimateId = String(formData.get("estimate_id") ?? "");
  const leadId = String(formData.get("lead_id") ?? "");
  const title = String(formData.get("title") ?? "").trim();
  const taxRate = percentToRate(String(formData.get("tax_percent") ?? "0"));
  if (!estimateId || !title) return { error: "Give the job a title." };
  if (taxRate === null) return { error: "Sales tax must be a percentage between 0 and 100." };

  try {
    await updateEstimateMeta(session.org.id, estimateId, {
      title,
      tax_rate: taxRate,
      notes: String(formData.get("notes") ?? "").trim() || null,
    });
    if (leadId) {
      await updateLead(session.org.id, leadId, {
        contact_name: String(formData.get("contact_name") ?? "").trim(),
        email: String(formData.get("email") ?? "").trim() || null,
        phone: String(formData.get("phone") ?? "").trim() || null,
        job_address: String(formData.get("job_address") ?? "").trim() || null,
      });
    }
  } catch (error) {
    return { error: error instanceof Error ? error.message : "Could not save." };
  }

  revalidatePath(`/estimates/${estimateId}`);
  return { notice: "Saved." };
}

export async function sendProposalAction(_prev: FormState, formData: FormData): Promise<FormState> {
  const session = await requireSession();
  const estimateId = String(formData.get("estimate_id") ?? "");
  if (!estimateId) return { error: "Missing estimate." };

  const estimate = await getEstimate(session.org.id, estimateId);
  if (!estimate) return { error: "Estimate not found." };
  if (estimate.line_items.length === 0) {
    return { error: "Add at least one line item before sending." };
  }
  if (estimate.status === "signed") {
    return { error: "This estimate has been signed — it cannot be changed." };
  }

  const depositCents = parseMoneyToCents(String(formData.get("deposit") ?? "0")) ?? 0;
  if (depositCents < 0 || depositCents > estimate.total_cents) {
    return { error: "The deposit has to be between zero and the job total." };
  }

  try {
    await sendProposal(session.org.id, estimateId, {
      cover_note: String(formData.get("cover_note") ?? "").trim() || null,
      terms: String(formData.get("terms") ?? "").trim() || null,
      deposit_amount_cents: depositCents,
    });
  } catch (error) {
    return { error: error instanceof Error ? error.message : "Could not send the proposal." };
  }

  revalidatePath(`/estimates/${estimateId}`);
  return { notice: "Proposal is live. Send the link to your customer." };
}
