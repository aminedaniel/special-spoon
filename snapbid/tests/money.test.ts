import { describe, expect, it } from "vitest";
import {
  computeTotals,
  depositFromPercent,
  formatCents,
  lineTotalCents,
  parseMoneyToCents,
  parseQuantity,
  percentToRate,
  rateToPercent,
} from "@/lib/money";

describe("parseMoneyToCents", () => {
  it("parses plain and formatted dollars", () => {
    expect(parseMoneyToCents("450")).toBe(45000);
    expect(parseMoneyToCents("450.75")).toBe(45075);
    expect(parseMoneyToCents("$1,234.56")).toBe(123456);
    expect(parseMoneyToCents(" 12.5 ")).toBe(1250);
  });

  it("rejects junk instead of guessing", () => {
    expect(parseMoneyToCents("call for pricing")).toBeNull();
    expect(parseMoneyToCents("")).toBeNull();
    expect(parseMoneyToCents(undefined)).toBeNull();
    expect(parseMoneyToCents("12.34.56")).toBeNull();
  });

  it("does not lose a cent to float error", () => {
    expect(parseMoneyToCents("1.005")).toBe(101);
    expect(parseMoneyToCents(0.29)).toBe(29);
    expect(parseMoneyToCents(1.1)).toBe(110);
  });
});

describe("parseQuantity", () => {
  it("accepts fractional quantities", () => {
    expect(parseQuantity("3.5")).toBe(3.5);
    expect(parseQuantity("1,200")).toBe(1200);
    expect(parseQuantity("abc")).toBeNull();
  });
});

describe("totals", () => {
  it("rounds each line once, then sums", () => {
    expect(lineTotalCents(3.5, 45000)).toBe(157500);
    expect(lineTotalCents(0.333, 10000)).toBe(3330);
  });

  it("computes subtotal, tax and total", () => {
    const totals = computeTotals(
      [
        { quantity: 2, unit_price_cents: 45000 },
        { quantity: 3.5, unit_price_cents: 12000 },
      ],
      0.0875,
    );
    expect(totals.subtotal_cents).toBe(132000);
    expect(totals.tax_cents).toBe(11550);
    expect(totals.total_cents).toBe(143550);
  });

  it("treats a missing or negative rate as no tax", () => {
    const totals = computeTotals([{ quantity: 1, unit_price_cents: 1000 }], Number.NaN);
    expect(totals.tax_cents).toBe(0);
    expect(totals.total_cents).toBe(1000);
  });

  it("keeps printed lines adding up to the printed subtotal", () => {
    const items = [
      { quantity: 1.005, unit_price_cents: 333 },
      { quantity: 2.5, unit_price_cents: 777 },
    ];
    const totals = computeTotals(items, 0);
    const printed = items.reduce((sum, i) => sum + lineTotalCents(i.quantity, i.unit_price_cents), 0);
    expect(totals.subtotal_cents).toBe(printed);
  });
});

describe("deposit", () => {
  it("takes a percentage of the total", () => {
    expect(depositFromPercent(143550, 25)).toBe(35888);
    expect(depositFromPercent(100000, 0)).toBe(0);
  });

  it("never exceeds the total", () => {
    expect(depositFromPercent(100000, 250)).toBe(100000);
  });
});

describe("tax rate round-trip", () => {
  it("converts percent to rate and back", () => {
    expect(percentToRate("8.75")).toBe(0.0875);
    expect(percentToRate("0")).toBe(0);
    expect(percentToRate("101")).toBeNull();
    expect(percentToRate("-1")).toBeNull();
    expect(rateToPercent(0.0875)).toBe("8.75");
    expect(rateToPercent(0)).toBe("0");
  });
});

describe("formatCents", () => {
  it("formats US currency", () => {
    expect(formatCents(143550)).toBe("$1,435.50");
    expect(formatCents(0)).toBe("$0.00");
  });
});

describe("money parser edge cases", () => {
  it("handles leading-dot, trailing-dot and negative values", () => {
    expect(parseMoneyToCents(".50")).toBe(50);
    expect(parseMoneyToCents("12.")).toBe(1200);
    expect(parseMoneyToCents("-25.50")).toBe(-2550);
    expect(parseMoneyToCents(".")).toBeNull();
  });

  it("rounds sub-cent input half up", () => {
    expect(parseMoneyToCents("0.004")).toBe(0);
    expect(parseMoneyToCents("0.005")).toBe(1);
    expect(parseMoneyToCents("9.999")).toBe(1000);
  });
});
