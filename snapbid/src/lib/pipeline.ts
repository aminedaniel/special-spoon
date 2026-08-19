import type { Estimate } from "@/lib/types";

export interface PipelineStats {
  draft: number;
  sent: number;
  viewed: number;
  signed: number;
  declined: number;
  total: number;
  /** Signed ÷ (everything that left the building). */
  winRate: number | null;
  signedValueCents: number;
  outstandingValueCents: number;
}

export function pipelineStats(rows: Pick<Estimate, "status" | "total_cents">[]): PipelineStats {
  const counts = { draft: 0, sent: 0, viewed: 0, signed: 0, declined: 0 };
  let signedValueCents = 0;
  let outstandingValueCents = 0;

  for (const row of rows) {
    counts[row.status] += 1;
    if (row.status === "signed") signedValueCents += row.total_cents;
    if (row.status === "sent" || row.status === "viewed") outstandingValueCents += row.total_cents;
  }

  const decided = counts.sent + counts.viewed + counts.signed + counts.declined;
  return {
    ...counts,
    total: rows.length,
    winRate: decided > 0 ? counts.signed / decided : null,
    signedValueCents,
    outstandingValueCents,
  };
}
