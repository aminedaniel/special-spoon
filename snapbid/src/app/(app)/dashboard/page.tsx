import Link from "next/link";
import { requireSession } from "@/lib/db/session";
import { listEstimates, pipelineStats } from "@/lib/db/estimates";
import { countPriceBookItems } from "@/lib/db/price-book";
import { GuaranteeBanner } from "@/components/GuaranteeBanner";
import { Card, Empty, StatusBadge } from "@/components/ui";
import { formatCents } from "@/lib/money";

export const dynamic = "force-dynamic";

export default async function DashboardPage({
  searchParams,
}: {
  searchParams: Promise<{ billing?: string }>;
}) {
  const session = await requireSession();
  const [estimates, priceBookCount, { billing }] = await Promise.all([
    listEstimates(session.org.id),
    countPriceBookItems(session.org.id),
    searchParams,
  ]);

  const stats = pipelineStats(estimates);
  const recent = estimates.slice(0, 6);

  return (
    <div className="space-y-5">
      {billing === "saved" && (
        <p className="rounded-2xl border border-emerald-200 bg-emerald-50 px-4 py-3 text-sm text-emerald-800">
          Card saved. You are not charged until your guarantee window closes.
        </p>
      )}

      <GuaranteeBanner org={session.org} />

      <div className="flex items-center justify-between gap-3">
        <div>
          <h1 className="text-xl font-bold text-ink">Pipeline</h1>
          <p className="text-sm text-muted">{priceBookCount} price-book items ready.</p>
        </div>
        <Link
          href="/estimates/new"
          className="inline-flex min-h-11 items-center rounded-xl bg-brand px-4 text-sm font-semibold text-white"
        >
          New estimate
        </Link>
      </div>

      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        <Stat label="Draft" value={stats.draft} />
        <Stat label="Sent" value={stats.sent} />
        <Stat label="Viewed" value={stats.viewed} />
        <Stat label="Signed" value={stats.signed} tone="brand" />
      </div>

      <div className="grid gap-3 sm:grid-cols-3">
        <Stat
          label="Win rate"
          value={stats.winRate === null ? "—" : `${Math.round(stats.winRate * 100)}%`}
          hint="Signed ÷ proposals sent"
        />
        <Stat label="Signed value" value={formatCents(stats.signedValueCents)} />
        <Stat label="Out for signature" value={formatCents(stats.outstandingValueCents)} />
      </div>

      <Card
        title="Recent estimates"
        action={
          <Link href="/estimates" className="text-sm font-semibold text-brand">
            See all
          </Link>
        }
      >
        {recent.length === 0 ? (
          <Empty
            title="No estimates yet"
            body="Create your first estimate, send the proposal, and the guarantee clock takes care of itself."
            action={
              <Link
                href="/estimates/new"
                className="inline-flex min-h-11 items-center rounded-xl bg-brand px-4 text-sm font-semibold text-white"
              >
                New estimate
              </Link>
            }
          />
        ) : (
          <ul className="divide-y divide-line">
            {recent.map((estimate) => (
              <li key={estimate.id}>
                <Link
                  href={`/estimates/${estimate.id}`}
                  className="flex items-center justify-between gap-3 px-4 py-3 hover:bg-gray-50"
                >
                  <div className="min-w-0">
                    <p className="truncate text-sm font-semibold text-ink">
                      {estimate.lead.contact_name}
                    </p>
                    <p className="truncate text-xs text-muted">{estimate.title}</p>
                  </div>
                  <div className="flex shrink-0 items-center gap-3">
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

function Stat({
  label,
  value,
  hint,
  tone,
}: {
  label: string;
  value: string | number;
  hint?: string;
  tone?: "brand";
}) {
  return (
    <div className="rounded-2xl border border-line bg-surface px-4 py-3 shadow-sm">
      <p className="text-xs font-semibold uppercase tracking-wide text-muted">{label}</p>
      <p className={`mt-1 text-xl font-bold ${tone === "brand" ? "text-brand" : "text-ink"}`}>
        {value}
      </p>
      {hint && <p className="text-xs text-muted">{hint}</p>}
    </div>
  );
}
