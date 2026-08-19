import { readFileSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";
import { templateCsv } from "../scripts/export-templates";
import { parsePriceBookCsv } from "@/lib/csv";
import { PRICE_BOOK_TEMPLATES } from "@/lib/seed/price-books";
import type { Trade } from "@/lib/types";

const TRADES: Trade[] = ["roofing", "remodeling"];

describe("price-book templates", () => {
  it.each(TRADES)("%s template is a usable price book", (trade) => {
    const items = PRICE_BOOK_TEMPLATES[trade];
    expect(items.length).toBeGreaterThan(20);
    for (const item of items) {
      expect(item.name.trim()).not.toBe("");
      expect(item.unit_price_cents).toBeGreaterThan(0);
      expect(Number.isInteger(item.unit_price_cents)).toBe(true);
    }
    // Duplicate names would make the estimate builder's picker ambiguous.
    expect(new Set(items.map((item) => item.name)).size).toBe(items.length);
  });

  it.each(TRADES)("%s seed CSV is in sync with the template", (trade) => {
    const path = join(process.cwd(), "supabase", "seed", `${trade}-price-book.csv`);
    const onDisk = readFileSync(path, "utf8").trimEnd();
    expect(onDisk).toBe(templateCsv(trade).trimEnd());
  });

  it.each(TRADES)("%s seed CSV re-imports cleanly", (trade) => {
    const path = join(process.cwd(), "supabase", "seed", `${trade}-price-book.csv`);
    const { items, errors } = parsePriceBookCsv(readFileSync(path, "utf8"));
    expect(errors).toEqual([]);
    expect(items).toHaveLength(PRICE_BOOK_TEMPLATES[trade].length);
  });
});
