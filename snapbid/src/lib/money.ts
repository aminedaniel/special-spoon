/**
 * Money helpers. Every amount in SnapBid is an integer number of cents —
 * never a float — so totals are exact and reproducible on the proposal, the
 * PDF, and the Stripe charge alike.
 */

/** Round half-away-from-zero (what people expect on an invoice). */
function roundHalfUp(value: number): number {
  return value < 0 ? -Math.round(-value) : Math.round(value);
}

/**
 * Parse user/CSV input into cents. Accepts "1234.5", "$1,234.50". Returns null
 * when unparseable.
 *
 * Strings are converted digit by digit rather than by multiplying a float:
 * `1.005 * 100` is 100.49999999999999 in IEEE-754, which would quietly shave a
 * cent off a typed price.
 */
export function parseMoneyToCents(input: string | number | null | undefined): number | null {
  if (input === null || input === undefined) return null;

  if (typeof input === "number") {
    if (!Number.isFinite(input)) return null;
    // toFixed first, so the float's stored value is nudged back to what the
    // author of the number meant before it is rounded to cents.
    return roundHalfUp(Number((input * 100).toFixed(6)));
  }

  const cleaned = input.trim().replace(/[$,\s]/g, "");
  const match = /^(-)?(\d*)(?:\.(\d*))?$/.exec(cleaned);
  if (!match || (match[2] === "" && !match[3])) return null;

  const [, sign, whole, fraction = ""] = match;
  const padded = `${fraction}00`.slice(0, 3);
  const cents = Number(whole || "0") * 100 + Number(padded.slice(0, 2));
  const rounded = Number(padded[2]) >= 5 ? cents + 1 : cents;
  if (!Number.isFinite(rounded)) return null;
  return sign ? -rounded : rounded;
}

/** Parse a quantity ("3", "3.5", "1,200"). Returns null when unparseable. */
export function parseQuantity(input: string | number | null | undefined): number | null {
  if (input === null || input === undefined) return null;
  if (typeof input === "number") return Number.isFinite(input) ? input : null;
  const cleaned = input.trim().replace(/[,\s]/g, "");
  if (cleaned === "" || !/^\d*(\.\d+)?$/.test(cleaned)) return null;
  const value = Number(cleaned);
  return Number.isFinite(value) ? value : null;
}

/** Format cents as "$1,234.50". */
export function formatCents(cents: number, currency = "USD"): string {
  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency,
    minimumFractionDigits: 2,
  }).format(cents / 100);
}

/** Format cents as a bare editable value: "1234.50". */
export function centsToInput(cents: number): string {
  return (cents / 100).toFixed(2);
}

export function lineTotalCents(quantity: number, unitPriceCents: number): number {
  return roundHalfUp(quantity * unitPriceCents);
}

export interface TotalsInput {
  quantity: number;
  unit_price_cents: number;
}

export interface Totals {
  subtotal_cents: number;
  tax_cents: number;
  total_cents: number;
}

/**
 * Subtotal is the sum of per-line totals (each rounded once), so the printed
 * line items always add up to the printed subtotal.
 */
export function computeTotals(items: TotalsInput[], taxRate: number): Totals {
  const subtotal_cents = items.reduce(
    (sum, item) => sum + lineTotalCents(item.quantity, item.unit_price_cents),
    0,
  );
  const rate = Number.isFinite(taxRate) && taxRate > 0 ? taxRate : 0;
  const tax_cents = roundHalfUp(subtotal_cents * rate);
  return { subtotal_cents, tax_cents, total_cents: subtotal_cents + tax_cents };
}

/** Deposit derived from a percentage of the total, clamped to the total. */
export function depositFromPercent(totalCents: number, percent: number): number {
  if (!Number.isFinite(percent) || percent <= 0) return 0;
  return Math.min(totalCents, roundHalfUp((totalCents * percent) / 100));
}

/** "8.75" (percent, as typed) -> 0.0875 (rate, as stored). */
export function percentToRate(percent: string | number): number | null {
  const value = typeof percent === "number" ? percent : Number(String(percent).trim().replace(/%/g, ""));
  if (!Number.isFinite(value) || value < 0 || value > 100) return null;
  return Math.round(value * 10000) / 1000000;
}

export function rateToPercent(rate: number): string {
  return (rate * 100).toFixed(4).replace(/\.?0+$/, "");
}
