/**
 * Writes the trade price-book templates out as CSVs contractors can open in a
 * spreadsheet. The TypeScript templates are the source of truth; run
 * `npm run export:templates` after editing them.
 */
import { writeFileSync } from "node:fs";
import { join } from "node:path";
import { priceBookToCsv } from "../src/lib/csv";
import { PRICE_BOOK_TEMPLATES } from "../src/lib/seed/price-books";
import type { Trade } from "../src/lib/types";

export function templateCsv(trade: Trade): string {
  return priceBookToCsv(
    PRICE_BOOK_TEMPLATES[trade].map((item) => ({
      name: item.name,
      description: item.description ?? null,
      category: item.category,
      unit: item.unit,
      unit_price_cents: item.unit_price_cents,
    })),
  );
}

if (process.argv[1]?.endsWith("export-templates.ts")) {
  for (const trade of ["roofing", "remodeling"] as Trade[]) {
    const path = join(process.cwd(), "supabase", "seed", `${trade}-price-book.csv`);
    writeFileSync(path, `${templateCsv(trade)}\n`);
    console.log(`wrote ${path}`);
  }
}
