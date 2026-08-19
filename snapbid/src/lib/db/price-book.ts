import { createClient } from "@/lib/supabase/server";
import { createAdminClient } from "@/lib/supabase/admin";
import { PRICE_BOOK_TEMPLATES } from "@/lib/seed/price-books";
import type { PriceBookItem, Trade } from "@/lib/types";

export interface PriceBookInput {
  name: string;
  description?: string | null;
  category: string;
  unit: string;
  unit_price_cents: number;
}

export async function listPriceBookItems(orgId: string): Promise<PriceBookItem[]> {
  const supabase = await createClient();
  const { data, error } = await supabase
    .from("price_book_items")
    .select("*")
    .eq("org_id", orgId)
    .eq("is_active", true)
    .order("category", { ascending: true })
    .order("name", { ascending: true });
  if (error) throw new Error(`Could not load price book: ${error.message}`);
  return (data ?? []) as PriceBookItem[];
}

export async function createPriceBookItem(orgId: string, input: PriceBookInput): Promise<PriceBookItem> {
  const supabase = await createClient();
  const { data, error } = await supabase
    .from("price_book_items")
    .insert({ ...input, org_id: orgId })
    .select()
    .single();
  if (error) throw new Error(`Could not add item: ${error.message}`);
  return data as PriceBookItem;
}

export async function updatePriceBookItem(
  orgId: string,
  itemId: string,
  input: Partial<PriceBookInput>,
): Promise<void> {
  const supabase = await createClient();
  const { error } = await supabase
    .from("price_book_items")
    .update(input)
    .eq("id", itemId)
    .eq("org_id", orgId);
  if (error) throw new Error(`Could not update item: ${error.message}`);
}

/** Soft delete: estimates already referencing the item keep their snapshot. */
export async function archivePriceBookItem(orgId: string, itemId: string): Promise<void> {
  const supabase = await createClient();
  const { error } = await supabase
    .from("price_book_items")
    .update({ is_active: false })
    .eq("id", itemId)
    .eq("org_id", orgId);
  if (error) throw new Error(`Could not remove item: ${error.message}`);
}

export async function bulkInsertPriceBookItems(
  orgId: string,
  items: PriceBookInput[],
  trade?: Trade,
): Promise<number> {
  if (items.length === 0) return 0;
  const supabase = await createClient();
  const { error, count } = await supabase
    .from("price_book_items")
    .insert(items.map((item) => ({ ...item, org_id: orgId, trade: trade ?? null })), { count: "exact" });
  if (error) throw new Error(`Import failed: ${error.message}`);
  return count ?? items.length;
}

/**
 * Seeds a brand-new org's price book from its trade template. Runs with the
 * service role because onboarding calls it before the first page load settles.
 */
export async function seedPriceBookFromTemplate(orgId: string, trade: Trade): Promise<number> {
  const admin = createAdminClient();
  const rows = PRICE_BOOK_TEMPLATES[trade].map((item) => ({
    org_id: orgId,
    name: item.name,
    description: item.description ?? null,
    category: item.category,
    unit: item.unit,
    unit_price_cents: item.unit_price_cents,
    trade,
  }));
  const { error } = await admin.from("price_book_items").insert(rows);
  if (error) throw new Error(`Could not seed price book: ${error.message}`);
  return rows.length;
}

export async function countPriceBookItems(orgId: string): Promise<number> {
  const supabase = await createClient();
  const { count, error } = await supabase
    .from("price_book_items")
    .select("id", { count: "exact", head: true })
    .eq("org_id", orgId)
    .eq("is_active", true);
  if (error) return 0;
  return count ?? 0;
}
