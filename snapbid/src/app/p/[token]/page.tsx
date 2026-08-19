import { notFound } from "next/navigation";
import type { Metadata } from "next";
import { getPublicProposal, recordProposalView } from "@/lib/db/proposals";
import { getSession } from "@/lib/db/session";
import { formatCents } from "@/lib/money";
import { AcceptPanel } from "./AcceptPanel";

export const dynamic = "force-dynamic";

export async function generateMetadata({
  params,
}: {
  params: Promise<{ token: string }>;
}): Promise<Metadata> {
  const { token } = await params;
  const data = await getPublicProposal(token);
  if (!data) return { title: "Proposal" };
  return {
    title: `${data.estimate.title} — ${data.org.name}`,
    description: `Proposal from ${data.org.name} for ${data.lead.contact_name}.`,
    robots: { index: false, follow: false },
  };
}

export default async function ProposalPage({
  params,
  searchParams,
}: {
  params: Promise<{ token: string }>;
  searchParams: Promise<{ deposit?: string }>;
}) {
  const [{ token }, { deposit }] = await Promise.all([params, searchParams]);
  const data = await getPublicProposal(token);
  if (!data) notFound();

  // "Viewed" is the signal the contractor acts on, so it has to mean the
  // customer opened it — the contractor previewing their own proposal does not
  // count.
  const session = await getSession();
  if (session?.org.id !== data.org.id) {
    await recordProposalView(token);
  }

  const { org, estimate, lineItems, lead, proposal } = data;
  const brand = /^#[0-9a-fA-F]{6}$/.test(org.brand_color) ? org.brand_color : "#1d4ed8";

  return (
    <main className="mx-auto w-full max-w-2xl px-4 pb-16 pt-6">
      <div className="h-2 w-full rounded-full" style={{ background: brand }} />

      {deposit === "paid" && (
        <p className="mt-4 rounded-2xl border border-emerald-200 bg-emerald-50 px-4 py-3 text-sm text-emerald-800">
          Deposit received — thank you. {org.name} will be in touch to schedule the work.
        </p>
      )}

      <header className="mt-6 flex items-start justify-between gap-4">
        <div className="min-w-0">
          {org.logo_url ? (
            // eslint-disable-next-line @next/next/no-img-element
            <img src={org.logo_url} alt={org.name} className="mb-3 h-12 w-auto object-contain" />
          ) : null}
          <p className="text-lg font-bold text-ink">{org.name}</p>
          <p className="text-xs text-muted">
            {[org.phone, org.email, org.address].filter(Boolean).join(" · ")}
          </p>
        </div>
        <div className="shrink-0 text-right">
          <p className="text-xs font-bold uppercase tracking-wide" style={{ color: brand }}>
            Proposal
          </p>
          <p className="text-xs text-muted">
            {new Date(proposal.sent_at ?? estimate.created_at).toLocaleDateString("en-US", {
              month: "long",
              day: "numeric",
              year: "numeric",
            })}
          </p>
        </div>
      </header>

      <section className="mt-6 rounded-2xl border border-line bg-surface p-5 shadow-sm">
        <p className="text-xs font-semibold uppercase tracking-wide text-muted">Prepared for</p>
        <p className="mt-1 text-base font-bold text-ink">{lead.contact_name}</p>
        {lead.job_address && <p className="text-sm text-muted">{lead.job_address}</p>}
        <h1 className="mt-4 text-xl font-bold text-ink">{estimate.title}</h1>
        {proposal.cover_note && (
          <p className="mt-3 whitespace-pre-line text-sm leading-relaxed text-ink">
            {proposal.cover_note}
          </p>
        )}
      </section>

      <section className="mt-4 rounded-2xl border border-line bg-surface shadow-sm">
        <h2 className="border-b border-line px-5 py-3 text-sm font-semibold text-ink">
          Scope of work
        </h2>
        <ul className="divide-y divide-line">
          {lineItems.map((item) => (
            <li key={item.id} className="flex items-start justify-between gap-4 px-5 py-3">
              <div className="min-w-0">
                <p className="text-sm font-medium text-ink">{item.name}</p>
                {item.description && <p className="text-xs text-muted">{item.description}</p>}
                <p className="mt-0.5 text-xs text-muted">
                  {Number(item.quantity)} {item.unit} × {formatCents(item.unit_price_cents)}
                </p>
              </div>
              <span className="shrink-0 text-sm font-semibold text-ink">
                {formatCents(item.line_total_cents)}
              </span>
            </li>
          ))}
        </ul>

        <dl className="space-y-2 border-t border-line px-5 py-4 text-sm">
          <div className="flex justify-between">
            <dt className="text-muted">Subtotal</dt>
            <dd className="font-medium text-ink">{formatCents(estimate.subtotal_cents)}</dd>
          </div>
          {estimate.tax_cents > 0 && (
            <div className="flex justify-between">
              <dt className="text-muted">Tax</dt>
              <dd className="font-medium text-ink">{formatCents(estimate.tax_cents)}</dd>
            </div>
          )}
          <div className="flex items-baseline justify-between border-t border-line pt-2">
            <dt className="text-base font-bold text-ink">Total</dt>
            <dd className="text-xl font-bold" style={{ color: brand }}>
              {formatCents(estimate.total_cents)}
            </dd>
          </div>
          {proposal.deposit_amount_cents > 0 && (
            <div className="flex justify-between">
              <dt className="text-muted">Deposit due on acceptance</dt>
              <dd className="font-medium text-ink">{formatCents(proposal.deposit_amount_cents)}</dd>
            </div>
          )}
        </dl>
      </section>

      <AcceptPanel
        token={proposal.public_token}
        brand={brand}
        customerName={lead.contact_name}
        depositCents={proposal.deposit_amount_cents}
        signedAt={proposal.signed_at}
        signatureName={proposal.signature_name}
        declinedAt={proposal.declined_at}
      />

      {proposal.terms && (
        <section className="mt-4 rounded-2xl border border-line bg-surface p-5 shadow-sm">
          <h2 className="text-sm font-semibold text-ink">Terms</h2>
          <p className="mt-2 whitespace-pre-line text-xs leading-relaxed text-muted">
            {proposal.terms}
          </p>
        </section>
      )}

      <footer className="mt-6 flex items-center justify-between gap-3 text-xs text-muted">
        <a href={`/p/${proposal.public_token}/pdf`} className="font-semibold" style={{ color: brand }}>
          Download PDF
        </a>
        <span>Questions? Call {org.phone ?? org.name}.</span>
      </footer>
    </main>
  );
}
