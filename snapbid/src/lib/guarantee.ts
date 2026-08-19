/**
 * The 14-day guarantee engine.
 *
 * "Sign one extra job in 14 days or your first month is free" is a product
 * mechanic, not a sales promise: the state below is what billing keys off, so
 * honoring it never depends on anyone remembering to.
 *
 * States
 *   active   — inside the original 14-day window.
 *   met      — a proposal reached `signed` inside the window; billing proceeds
 *              at billing_starts_at as normal.
 *   extended — the original window lapsed unmet: the first month is comped and
 *              the window was pushed out 14 more days (this happens once).
 *   comped   — the extended window also lapsed unmet: the comp stands, there is
 *              no second extension, and billing starts.
 *
 * The window end is always `billing_starts_at`: the account is never charged
 * while the guarantee is running, and extending the window defers the charge.
 */

export const GUARANTEE_WINDOW_DAYS = 14;
const DAY_MS = 24 * 60 * 60 * 1000;

export type GuaranteeStatus = "active" | "met" | "comped" | "extended";

export interface GuaranteeState {
  guarantee_started_at: string | null;
  guarantee_met_at: string | null;
  guarantee_status: GuaranteeStatus;
  billing_starts_at: string | null;
  guarantee_extended_at: string | null;
}

export function addDays(date: Date, days: number): Date {
  return new Date(date.getTime() + days * DAY_MS);
}

/** Field values written when onboarding completes and the clock starts. */
export function startGuarantee(now: Date) {
  return {
    guarantee_started_at: now.toISOString(),
    billing_starts_at: addDays(now, GUARANTEE_WINDOW_DAYS).toISOString(),
    guarantee_status: "active" as const,
    guarantee_met_at: null,
    guarantee_extended_at: null,
  };
}

/** End of the currently running window (the original one, or the extension). */
export function windowEndsAt(state: GuaranteeState): Date | null {
  if (state.billing_starts_at) return new Date(state.billing_starts_at);
  if (state.guarantee_started_at) {
    return addDays(new Date(state.guarantee_started_at), GUARANTEE_WINDOW_DAYS);
  }
  return null;
}

export function isWindowOpen(state: GuaranteeState, now: Date): boolean {
  if (state.guarantee_status === "met" || state.guarantee_status === "comped") return false;
  const end = windowEndsAt(state);
  return end !== null && now.getTime() <= end.getTime();
}

/**
 * Called whenever a proposal is signed. Returns the org patch that marks the
 * guarantee met, or null when the signature does not change anything (window
 * closed, or already met).
 */
export function onProposalSigned(
  state: GuaranteeState,
  signedAt: Date,
): { guarantee_met_at: string; guarantee_status: "met" } | null {
  if (!isWindowOpen(state, signedAt)) return null;
  return { guarantee_met_at: signedAt.toISOString(), guarantee_status: "met" };
}

export type LapseAction =
  | { kind: "none" }
  | {
      kind: "comp_and_extend";
      patch: {
        guarantee_status: "extended";
        billing_starts_at: string;
        guarantee_extended_at: string;
      };
    }
  | { kind: "close_unmet"; patch: { guarantee_status: "comped" } };

/**
 * Daily job logic for one account. `hasSignedProposal` is whether any proposal
 * reached `signed` inside the window that just lapsed.
 */
export function evaluateLapse(
  state: GuaranteeState,
  hasSignedProposal: boolean,
  now: Date,
): LapseAction {
  if (state.guarantee_status === "met" || state.guarantee_status === "comped") {
    return { kind: "none" };
  }
  const end = windowEndsAt(state);
  if (!end || now.getTime() < end.getTime()) return { kind: "none" };

  if (hasSignedProposal) {
    // Signed but never recorded (e.g. a webhook lost the race) — honor it.
    return { kind: "none" };
  }

  if (state.guarantee_status === "active") {
    return {
      kind: "comp_and_extend",
      patch: {
        guarantee_status: "extended",
        billing_starts_at: addDays(end, GUARANTEE_WINDOW_DAYS).toISOString(),
        guarantee_extended_at: now.toISOString(),
      },
    };
  }
  // status === "extended": the one-time extension is spent.
  return { kind: "close_unmet", patch: { guarantee_status: "comped" } };
}

export interface GuaranteeBanner {
  tone: "active" | "success" | "comped";
  headline: string;
  detail: string;
  /** 1-based day within the current window, when one is running. */
  day: number | null;
  totalDays: number;
}

/** What the dashboard banner shows. */
export function guaranteeBanner(state: GuaranteeState, now: Date): GuaranteeBanner | null {
  if (!state.guarantee_started_at) return null;

  if (state.guarantee_status === "met") {
    return {
      tone: "success",
      headline: "Guarantee met — nice work.",
      detail: "You signed a job inside your window. Billing starts as normal.",
      day: null,
      totalDays: GUARANTEE_WINDOW_DAYS,
    };
  }

  const end = windowEndsAt(state);
  if (state.guarantee_status === "comped" || !end || now.getTime() > end.getTime()) {
    return {
      tone: "comped",
      headline: "Your first month is on us.",
      detail: "No job was signed inside the guarantee window, so the first month is comped.",
      day: null,
      totalDays: GUARANTEE_WINDOW_DAYS,
    };
  }

  const windowStart = addDays(end, -GUARANTEE_WINDOW_DAYS);
  const elapsedDays = Math.floor((now.getTime() - windowStart.getTime()) / DAY_MS);
  const day = Math.min(GUARANTEE_WINDOW_DAYS, Math.max(1, elapsedDays + 1));
  const extended = state.guarantee_status === "extended";

  return {
    tone: "active",
    headline: `Day ${day} of ${GUARANTEE_WINDOW_DAYS} — sign 1 job to lock it in`,
    detail: extended
      ? "Your first month is already comped. Sign a job in this extra window and you are set."
      : "Sign one job through SnapBid before the window closes, or your first month is free.",
    day,
    totalDays: GUARANTEE_WINDOW_DAYS,
  };
}
