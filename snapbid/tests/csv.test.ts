import { describe, expect, it } from "vitest";
import { parsePriceBookCsv, priceBookToCsv } from "@/lib/csv";

describe("parsePriceBookCsv", () => {
  it("reads a well-formed price book", () => {
    const { items, errors } = parsePriceBookCsv(
      ["name,category,unit,price", "Ridge vent,Ventilation,lf,18.00", "Drip edge,Flashing,lf,4.50"].join("\n"),
    );
    expect(errors).toEqual([]);
    expect(items).toEqual([
      { name: "Ridge vent", description: null, category: "Ventilation", unit: "lf", unit_price_cents: 1800 },
      { name: "Drip edge", description: null, category: "Flashing", unit: "lf", unit_price_cents: 450 },
    ]);
  });

  it("accepts the column names contractors actually export", () => {
    const { items } = parsePriceBookCsv(["Item,Rate,UOM", "Tear-off,$120.00,square"].join("\n"));
    expect(items[0]).toMatchObject({ name: "Tear-off", unit_price_cents: 12000, unit: "square" });
  });

  it("reports bad rows instead of dropping them silently", () => {
    const { items, errors } = parsePriceBookCsv(
      ["name,price", "Good item,10", ",25", "No price,call us"].join("\n"),
    );
    expect(items).toHaveLength(1);
    expect(errors).toHaveLength(2);
    expect(errors[0]).toContain("Line 3");
    expect(errors[1]).toContain("Line 4");
  });

  it("refuses a file with no usable columns", () => {
    const { items, errors } = parsePriceBookCsv("foo,bar\n1,2");
    expect(items).toEqual([]);
    expect(errors[0]).toContain("name");
  });

  it("defaults category and unit when they are absent", () => {
    const { items } = parsePriceBookCsv("name,price\nMystery,99");
    expect(items[0].category).toBe("Imported");
    expect(items[0].unit).toBe("ea");
  });
});

describe("priceBookToCsv", () => {
  it("round-trips through the parser", () => {
    const csv = priceBookToCsv([
      { name: "Ridge vent", description: "Cut and install", category: "Ventilation", unit: "lf", unit_price_cents: 1800 },
    ]);
    const { items } = parsePriceBookCsv(csv);
    expect(items[0]).toEqual({
      name: "Ridge vent",
      description: "Cut and install",
      category: "Ventilation",
      unit: "lf",
      unit_price_cents: 1800,
    });
  });
});
