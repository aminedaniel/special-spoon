import { describe, expect, it } from "vitest";
import {
  GUARANTEE_WINDOW_DAYS,
  addDays,
  evaluateLapse,
  guaranteeBanner,
  isWindowOpen,
  onProposalSigned,
  startGuarantee,
  windowEndsAt,
  type GuaranteeState,
} from "@/lib/guarantee";

const START = new Date("2026-03-01T12:00:00Z");

function stateAt(now: Date): GuaranteeState {
  return { ...startGuarantee(now), guarantee_extended_at: null };
}

describe("startGuarantee", () => {
  it("opens a 14-day window and defers billing to its end", () => {
    const state = stateAt(START);
    expect(state.guarantee_status).toBe("active");
    expect(state.guarantee_started_at).toBe(START.toISOString());
    expect(state.billing_starts_at).toBe(addDays(START, GUARANTEE_WINDOW_DAYS).toISOString());
    expect(windowEndsAt(state)?.toISOString()).toBe(state.billing_starts_at);
  });
});

describe("signing inside the window", () => {
  it("marks the guarantee met", () => {
    const state = stateAt(START);
    const signedAt = addDays(START, 6);
    const patch = onProposalSigned(state, signedAt);
    expect(patch).toEqual({ guarantee_met_at: signedAt.toISOString(), guarantee_status: "met" });
  });

  it("counts a signature on the last minute of day 14", () => {
    const state = stateAt(START);
    const signedAt = new Date(addDays(START, GUARANTEE_WINDOW_DAYS).getTime() - 1000);
    expect(onProposalSigned(state, signedAt)).not.toBeNull();
  });

  it("does nothing after the window closes", () => {
    const state = stateAt(START);
    expect(onProposalSigned(state, addDays(START, 15))).toBeNull();
    expect(isWindowOpen(state, addDays(START, 15))).toBe(false);
  });

  it("does nothing once already met", () => {
    const state: GuaranteeState = { ...stateAt(START), guarantee_status: "met" };
    expect(onProposalSigned(state, addDays(START, 2))).toBeNull();
  });
});

describe("the daily lapse sweep", () => {
  it("leaves a running window alone", () => {
    expect(evaluateLapse(stateAt(START), false, addDays(START, 5))).toEqual({ kind: "none" });
  });

  it("comps the first month and extends once when nothing was signed", () => {
    const now = addDays(START, GUARANTEE_WINDOW_DAYS);
    const action = evaluateLapse(stateAt(START), false, now);
    expect(action.kind).toBe("comp_and_extend");
    if (action.kind !== "comp_and_extend") throw new Error("wrong branch");
    expect(action.patch.guarantee_status).toBe("extended");
    expect(action.patch.billing_starts_at).toBe(addDays(START, 28).toISOString());
  });

  it("does not comp an account that signed a job", () => {
    const now = addDays(START, GUARANTEE_WINDOW_DAYS);
    expect(evaluateLapse(stateAt(START), true, now)).toEqual({ kind: "none" });
  });

  it("does not extend a second time", () => {
    const extended: GuaranteeState = {
      guarantee_started_at: START.toISOString(),
      guarantee_met_at: null,
      guarantee_status: "extended",
      billing_starts_at: addDays(START, 28).toISOString(),
      guarantee_extended_at: addDays(START, 14).toISOString(),
    };
    const action = evaluateLapse(extended, false, addDays(START, 28));
    expect(action).toEqual({ kind: "close_unmet", patch: { guarantee_status: "comped" } });
  });

  it("is a no-op on terminal states", () => {
    const met: GuaranteeState = { ...stateAt(START), guarantee_status: "met" };
    const comped: GuaranteeState = { ...stateAt(START), guarantee_status: "comped" };
    expect(evaluateLapse(met, false, addDays(START, 30))).toEqual({ kind: "none" });
    expect(evaluateLapse(comped, false, addDays(START, 30))).toEqual({ kind: "none" });
  });

  it("survives an account whose window never started", () => {
    const blank: GuaranteeState = {
      guarantee_started_at: null,
      guarantee_met_at: null,
      guarantee_status: "active",
      billing_starts_at: null,
      guarantee_extended_at: null,
    };
    expect(evaluateLapse(blank, false, START)).toEqual({ kind: "none" });
    expect(guaranteeBanner(blank, START)).toBeNull();
  });
});

describe("the dashboard banner", () => {
  it("counts the day the owner is on", () => {
    const state = stateAt(START);
    expect(guaranteeBanner(state, START)?.day).toBe(1);
    expect(guaranteeBanner(state, addDays(START, 5))?.day).toBe(6);
    expect(guaranteeBanner(state, addDays(START, 13))?.day).toBe(14);
  });

  it("celebrates a met guarantee", () => {
    const state: GuaranteeState = { ...stateAt(START), guarantee_status: "met" };
    expect(guaranteeBanner(state, addDays(START, 20))?.tone).toBe("success");
  });

  it("says the month is comped once the window has passed", () => {
    const banner = guaranteeBanner(stateAt(START), addDays(START, 20));
    expect(banner?.tone).toBe("comped");
  });

  it("keeps counting through the extended window", () => {
    const extended: GuaranteeState = {
      guarantee_started_at: START.toISOString(),
      guarantee_met_at: null,
      guarantee_status: "extended",
      billing_starts_at: addDays(START, 28).toISOString(),
      guarantee_extended_at: addDays(START, 14).toISOString(),
    };
    const banner = guaranteeBanner(extended, addDays(START, 16));
    expect(banner?.tone).toBe("active");
    expect(banner?.day).toBe(3);
  });
});
