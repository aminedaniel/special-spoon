import Link from "next/link";
import { requireSession } from "@/lib/db/session";
import { listEstimates, pipelineStats } from "@/lib/db/estimates";
import { Card, Empty, StatusBadge } from "@/components/ui";
import { formatCents } from "@/lib/money";
import type { EstimateStatus } from "@/lib/types";

export const dynamic = "force-dynamic";

const FILTERS: { value: EstimateStatus | "all"; label: string }[] = [
  { value: "all", label: "All" },
  { value: "draft", label: "Draft" },
  { value: "sent", label: "Sent" },
  { value: "viewed", label: "Viewed" },
  { value: "signed", label: "Signed" },
];

export default async function EstimatesPage({
  searchParams,
}: {
  searchParams: Promise<{ status?: string }>;
}) {
  const session = await requireSession();
  const [estimates, { status }] = await Promise.all([
    listEstimates(session.org.id),
    searchParams,
  ]);

  const active = FILTERS.some((filter) => filter.value === status) ? status : "all";
  const visible = active === "all" ? estimates : estimates.filter((row) => row.status === active);
  const stats = pipelineStats(estimates);

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between gap-3">
        <div>
          <h1 className="text-xl font-bold text-ink">Estimates</h1>
          <p className="text-sm text-muted">
            {stats.total} total ·{" "}
            {stats.winRate === null ? "no win rate yet" : `${Math.round(stats.winRate * 100)}% win rate`}
          </p>
        </div>
        <Link
          href="/estimates/new"
          className="inline-flex min-h-11 items-center rounded-xl bg-brand px-4 text-sm font-semibold text-white"
        >
          New
        </Link>
      </div>

      <div className="-mx-4 flex gap-2 overflow-x-auto px-4 pb-1">
        {FILTERS.map((filter) => (
          <Link
            key={filter.value}
            href={filter.value === "all" ? "/estimates" : `/estimates?status=${filter.value}`}
            className={`shrink-0 rounded-full px-3.5 py-1.5 text-sm font-semibold ${
              active === filter.value
                ? "bg-brand text-white"
                : "border border-line bg-white text-muted"
            }`}
          >
            {filter.label}
          </Link>
        ))}
      </div>

      <Card>
        {visible.length === 0 ? (
          <Empty
            title="Nothing here"
            body="Estimates you create show up here with their live status: draft, sent, viewed, signed."
          />
        ) : (
          <ul className="divide-y divide-line">
            {visible.map((estimate) => (
              <li key={estimate.id}>
                <Link
                  href={`/estimates/${estimate.id}`}
                  className="flex items-center justify-between gap-3 px-4 py-3 hover:bg-gray-50"
                >
                  <div className="min-w-0">
                    <p className="truncate text-sm font-semibold text-ink">
                      {estimate.lead.contact_name}
                    </p>
                    <p className="truncate text-xs text-muted">
                      {estimate.title}
                      {estimate.lead.job_address ? ` · ${estimate.lead.job_address}` : ""}
                    </p>
                  </div>
                  <div className="flex shrink-0 flex-col items-end gap-1">
                    <span className="text-sm font-semibold text-ink">
                      {formatCents(estimate.total_cents)}
                    </span>
                    <StatusBadge status={estimate.status} />
                  </div>
                </Link>
              </li>
            ))}
          </ul>
        )}
      </Card>
    </div>
  );
}
