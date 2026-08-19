"use server";

import { revalidatePath } from "next/cache";
import { z } from "zod";
import { requireSession } from "@/lib/db/session";
import {
  archivePriceBookItem,
  bulkInsertPriceBookItems,
  createPriceBookItem,
  updatePriceBookItem,
} from "@/lib/db/price-book";
import { parsePriceBookCsv } from "@/lib/csv";
import { parseMoneyToCents } from "@/lib/money";

export interface PriceBookState {
  error?: string;
  notice?: string;
  warnings?: string[];
}

const itemSchema = z.object({
  name: z.string().trim().min(1, "Give the item a name.").max(200),
  description: z.string().trim().max(1000).optional(),
  category: z.string().trim().max(80).optional(),
  unit: z.string().trim().min(1).max(20),
  price: z.string().trim().min(1, "Enter a price."),
});

export async function addItemAction(
  _prev: PriceBookState,
  formData: FormData,
): Promise<PriceBookState> {
  const session = await requireSession();
  const parsed = itemSchema.safeParse({
    name: formData.get("name"),
    description: formData.get("description") ?? undefined,
    category: formData.get("category") ?? undefined,
    unit: formData.get("unit") ?? "ea",
    price: formData.get("price"),
  });
  if (!parsed.success) return { error: parsed.error.issues[0].message };

  const cents = parseMoneyToCents(parsed.data.price);
  if (cents === null || cents < 0) return { error: "That price is not a number." };

  try {
    await createPriceBookItem(session.org.id, {
      name: parsed.data.name,
      description: parsed.data.description || null,
      category: parsed.data.category || "General",
      unit: parsed.data.unit,
      unit_price_cents: cents,
    });
  } catch (error) {
    return { error: error instanceof Error ? error.message : "Could not add the item." };
  }

  revalidatePath("/price-book");
  return { notice: `Added ${parsed.data.name}.` };
}

export async function updateItemAction(formData: FormData): Promise<void> {
  const session = await requireSession();
  const id = String(formData.get("id") ?? "");
  const name = String(formData.get("name") ?? "").trim();
  const unit = String(formData.get("unit") ?? "ea").trim();
  const cents = parseMoneyToCents(String(formData.get("price") ?? ""));
  if (!id || !name || cents === null || cents < 0) return;

  await updatePriceBookItem(session.org.id, id, {
    name,
    unit,
    unit_price_cents: cents,
  });
  revalidatePath("/price-book");
}

export async function removeItemAction(formData: FormData): Promise<void> {
  const session = await requireSession();
  const id = String(formData.get("id") ?? "");
  if (!id) return;
  await archivePriceBookItem(session.org.id, id);
  revalidatePath("/price-book");
}

export async function importCsvAction(
  _prev: PriceBookState,
  formData: FormData,
): Promise<PriceBookState> {
  const session = await requireSession();
  const file = formData.get("file");
  if (!(file instanceof File) || file.size === 0) return { error: "Choose a CSV file to import." };
  if (file.size > 2 * 1024 * 1024) return { error: "That file is larger than 2 MB." };

  const { items, errors } = parsePriceBookCsv(await file.text());
  if (items.length === 0) {
    return { error: errors[0] ?? "No usable rows found in that file." };
  }

  try {
    await bulkInsertPriceBookItems(session.org.id, items, session.org.trade);
  } catch (error) {
    return { error: error instanceof Error ? error.message : "Import failed." };
  }

  revalidatePath("/price-book");
  return {
    notice: `Imported ${items.length} item${items.length === 1 ? "" : "s"}.`,
    warnings: errors.slice(0, 10),
  };
}
