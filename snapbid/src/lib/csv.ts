import Papa from "papaparse";
import { parseMoneyToCents } from "@/lib/money";
import type { PriceBookInput } from "@/lib/db/price-book";

export interface CsvParseResult {
  items: PriceBookInput[];
  errors: string[];
}

/** Header aliases, so a contractor's export from anywhere usually just works. */
const HEADERS: Record<keyof PriceBookInput | "ignore", string[]> = {
  name: ["name", "item", "item name", "description of work", "line item", "service"],
  description: ["description", "notes", "detail", "details"],
  category: ["category", "group", "section", "type"],
  unit: ["unit", "uom", "unit of measure", "units"],
  unit_price_cents: ["price", "unit price", "rate", "unit_price", "cost", "amount"],
  ignore: [],
};

function normalize(header: string): string {
  return header.trim().toLowerCase().replace(/[_-]+/g, " ").replace(/\s+/g, " ");
}

function fieldFor(header: string): keyof PriceBookInput | null {
  const normalized = normalize(header);
  for (const [field, aliases] of Object.entries(HEADERS)) {
    if (field === "ignore") continue;
    if (aliases.includes(normalized)) return field as keyof PriceBookInput;
  }
  return null;
}

/**
 * Parses a price-book CSV. Bad rows are reported rather than dropped silently —
 * a contractor whose 200-row import lost 12 lines needs to know which ones.
 */
export function parsePriceBookCsv(text: string): CsvParseResult {
  const parsed = Papa.parse<Record<string, string>>(text.trim(), {
    header: true,
    skipEmptyLines: "greedy",
  });

  const errors: string[] = [];
  const headers = parsed.meta.fields ?? [];
  const mapping = new Map<string, keyof PriceBookInput>();
  for (const header of headers) {
    const field = fieldFor(header);
    if (field) mapping.set(header, field);
  }

  if (![...mapping.values()].includes("name")) {
    return { items: [], errors: ["The CSV needs a 'name' column (or 'item', 'line item')."] };
  }
  if (![...mapping.values()].includes("unit_price_cents")) {
    return { items: [], errors: ["The CSV needs a 'price' column (or 'unit price', 'rate')."] };
  }

  const items: PriceBookInput[] = [];
  parsed.data.forEach((row, index) => {
    const line = index + 2; // header is line 1
    const values: Record<string, string> = {};
    for (const [header, field] of mapping) {
      values[field] = (row[header] ?? "").trim();
    }

    if (!values.name) {
      errors.push(`Line ${line}: missing item name — skipped.`);
      return;
    }
    const cents = parseMoneyToCents(values.unit_price_cents);
    if (cents === null || cents < 0) {
      errors.push(`Line ${line}: "${values.unit_price_cents}" is not a valid price — skipped.`);
      return;
    }

    items.push({
      name: values.name.slice(0, 200),
      description: values.description ? values.description.slice(0, 1000) : null,
      category: values.category ? values.category.slice(0, 80) : "Imported",
      unit: values.unit ? values.unit.slice(0, 20) : "ea",
      unit_price_cents: cents,
    });
  });

  return { items, errors };
}

/** Export of the org's price book, for editing in a spreadsheet. */
export function priceBookToCsv(
  items: { name: string; description: string | null; category: string; unit: string; unit_price_cents: number }[],
): string {
  return Papa.unparse(
    items.map((item) => ({
      name: item.name,
      description: item.description ?? "",
      category: item.category,
      unit: item.unit,
      price: (item.unit_price_cents / 100).toFixed(2),
    })),
  );
}
