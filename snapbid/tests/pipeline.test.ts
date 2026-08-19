import { describe, expect, it } from "vitest";
import { pipelineStats } from "@/lib/pipeline";

describe("pipelineStats", () => {
  it("counts by status and values the pipeline", () => {
    const stats = pipelineStats([
      { status: "draft", total_cents: 100000 },
      { status: "sent", total_cents: 200000 },
      { status: "viewed", total_cents: 300000 },
      { status: "signed", total_cents: 400000 },
      { status: "declined", total_cents: 500000 },
    ]);
    expect(stats.draft).toBe(1);
    expect(stats.total).toBe(5);
    expect(stats.signedValueCents).toBe(400000);
    expect(stats.outstandingValueCents).toBe(500000);
  });

  it("measures win rate against proposals that actually went out", () => {
    const stats = pipelineStats([
      { status: "draft", total_cents: 1 },
      { status: "signed", total_cents: 1 },
      { status: "declined", total_cents: 1 },
    ]);
    expect(stats.winRate).toBe(0.5);
  });

  it("has no win rate before anything is sent", () => {
    expect(pipelineStats([{ status: "draft", total_cents: 1 }]).winRate).toBeNull();
    expect(pipelineStats([]).winRate).toBeNull();
  });
});
