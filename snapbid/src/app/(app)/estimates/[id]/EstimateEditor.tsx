"use client";

import { useActionState, useMemo, useState } from "react";
import {
  addLineItemAction,
  deleteLineItemAction,
  sendProposalAction,
  updateEstimateAction,
  updateLineItemAction,
  type FormState,
} from "../actions";
import { SubmitButton } from "@/components/SubmitButton";
import { Card, ErrorText, Field, StatusBadge, inputClass } from "@/components/ui";
import { centsToInput, depositFromPercent, formatCents, rateToPercent } from "@/lib/money";
import { UNITS } from "@/lib/seed/price-books";
import type { EstimateDetail, EstimateLineItem, Organization, PriceBookItem } from "@/lib/types";

export function EstimateEditor({
  estimate,
  org,
  priceBook,
  proposalUrl,
}: {
  estimate: EstimateDetail;
  org: Organization;
  priceBook: PriceBookItem[];
  proposalUrl: string | null;
}) {
  const locked = estimate.status === "signed";

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <h1 className="truncate text-xl font-bold text-ink">{estimate.lead.contact_name}</h1>
          <p className="truncate text-sm text-muted">
            {estimate.title}
            {estimate.lead.job_address ? ` · ${estimate.lead.job_address}` : ""}
          </p>
        </div>
        <StatusBadge status={estimate.status} />
      </div>

      {locked && (
        <p className="rounded-2xl border border-emerald-200 bg-emerald-50 px-4 py-3 text-sm text-emerald-800">
          Signed{estimate.proposal?.signed_at
            ? ` on ${new Date(estimate.proposal.signed_at).toLocaleDateString("en-US")}`
            : ""}
          {estimate.proposal?.signature_name ? ` by ${estimate.proposal.signature_name}` : ""}. This
          estimate is locked — it is the agreement now.
        </p>
      )}

      <LineItems estimate={estimate} priceBook={priceBook} locked={locked} />
      <Totals estimate={estimate} />
      <ProposalPanel estimate={estimate} org={org} proposalUrl={proposalUrl} locked={locked} />
      <JobDetails estimate={estimate} locked={locked} />
    </div>
  );
}

function LineItems({
  estimate,
  priceBook,
  locked,
}: {
  estimate: EstimateDetail;
  priceBook: PriceBookItem[];
  locked: boolean;
}) {
  const [addState, addAction] = useActionState<FormState, FormData>(addLineItemAction, {});
  const [mode, setMode] = useState<"book" | "custom">("book");
  const [selectedId, setSelectedId] = useState("");

  const selected = useMemo(
    () => priceBook.find((item) => item.id === selectedId) ?? null,
    [priceBook, selectedId],
  );

  return (
    <Card title={`Line items (${estimate.line_items.length})`}>
      {estimate.line_items.length === 0 ? (
        <p className="px-4 py-6 text-center text-sm text-muted">
          Add items from your price book — the numbers are yours, SnapBid just assembles them.
        </p>
      ) : (
        <ul className="divide-y divide-line">
          {estimate.line_items.map((item) => (
            <li key={item.id} className="p-3">
              <LineItemRow item={item} estimateId={estimate.id} locked={locked} />
            </li>
          ))}
        </ul>
      )}

      {!locked && (
        <div className="border-t border-line p-4">
          <div className="mb-3 flex gap-2">
            {(["book", "custom"] as const).map((option) => (
              <button
                key={option}
                type="button"
                onClick={() => setMode(option)}
                className={`rounded-full px-3.5 py-1.5 text-sm font-semibold ${
                  mode === option ? "bg-brand text-white" : "border border-line bg-white text-muted"
                }`}
              >
                {option === "book" ? "From price book" : "Custom line"}
              </button>
            ))}
          </div>

          <form action={addAction} className="space-y-3">
            <ErrorText>{addState.error}</ErrorText>
            <input type="hidden" name="estimate_id" value={estimate.id} />

            {mode === "book" ? (
              <>
                <input type="hidden" name="price_book_item_id" value={selectedId} />
                <Field label="Item">
                  <select
                    className={inputClass}
                    value={selectedId}
                    onChange={(event) => setSelectedId(event.target.value)}
                    required
                  >
                    <option value="">Choose an item…</option>
                    {groupByCategory(priceBook).map(([category, items]) => (
                      <optgroup key={category} label={category}>
                        {items.map((item) => (
                          <option key={item.id} value={item.id}>
                            {item.name} — {formatCents(item.unit_price_cents)}/{item.unit}
                          </option>
                        ))}
                      </optgroup>
                    ))}
                  </select>
                </Field>
                <div className="grid grid-cols-2 gap-3">
                  <Field label={`Quantity${selected ? ` (${selected.unit})` : ""}`}>
                    <input
                      className={inputClass}
                      name="quantity"
                      inputMode="decimal"
                      defaultValue="1"
                      required
                    />
                  </Field>
                  <Field label="Price override" hint="Leave blank to use the book.">
                    <input
                      className={inputClass}
                      name="unit_price"
                      inputMode="decimal"
                      placeholder={selected ? centsToInput(selected.unit_price_cents) : ""}
                    />
                  </Field>
                </div>
              </>
            ) : (
              <>
                <Field label="Name">
                  <input className={inputClass} name="name" required />
                </Field>
                <Field label="Description">
                  <input className={inputClass} name="description" />
                </Field>
                <div className="grid grid-cols-3 gap-3">
                  <Field label="Qty">
                    <input
                      className={inputClass}
                      name="quantity"
                      inputMode="decimal"
                      defaultValue="1"
                      required
                    />
                  </Field>
                  <Field label="Unit">
                    <select className={inputClass} name="unit" defaultValue="ea">
                      {UNITS.map((unit) => (
                        <option key={unit} value={unit}>
                          {unit}
                        </option>
                      ))}
                    </select>
                  </Field>
                  <Field label="Price">
                    <input className={inputClass} name="unit_price" inputMode="decimal" required />
                  </Field>
                </div>
              </>
            )}

            <SubmitButton className="w-full" pendingLabel="Adding…">
              Add line
            </SubmitButton>
          </form>
        </div>
      )}
    </Card>
  );
}

function LineItemRow({
  item,
  estimateId,
  locked,
}: {
  item: EstimateLineItem;
  estimateId: string;
  locked: boolean;
}) {
  const [editing, setEditing] = useState(false);

  if (locked || !editing) {
    return (
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <p className="text-sm font-medium text-ink">{item.name}</p>
          <p className="text-xs text-muted">
            {Number(item.quantity)} {item.unit} × {formatCents(item.unit_price_cents)}
          </p>
          {item.needs_review && (
            <span className="mt-1 inline-block rounded-full bg-amber-100 px-2 py-0.5 text-[11px] font-semibold text-amber-800">
              Check this one
            </span>
          )}
        </div>
        <div className="flex shrink-0 items-center gap-3">
          <span className="text-sm font-semibold text-ink">{formatCents(item.line_total_cents)}</span>
          {!locked && (
            <button
              type="button"
              onClick={() => setEditing(true)}
              className="rounded-lg border border-line px-2.5 py-1.5 text-xs font-semibold text-muted hover:text-ink"
            >
              Edit
            </button>
          )}
        </div>
      </div>
    );
  }

  return (
    <form action={updateLineItemAction} className="space-y-2" onSubmit={() => setEditing(false)}>
      <input type="hidden" name="estimate_id" value={estimateId} />
      <input type="hidden" name="line_item_id" value={item.id} />
      <p className="text-sm font-medium text-ink">{item.name}</p>
      <div className="grid grid-cols-2 gap-2">
        <Field label="Qty">
          <input
            className={inputClass}
            name="quantity"
            inputMode="decimal"
            defaultValue={String(Number(item.quantity))}
            required
          />
        </Field>
        <Field label="Unit price">
          <input
            className={inputClass}
            name="unit_price"
            inputMode="decimal"
            defaultValue={centsToInput(item.unit_price_cents)}
            required
          />
        </Field>
      </div>
      <div className="flex flex-wrap gap-2">
        <SubmitButton pendingLabel="Saving…">Save</SubmitButton>
        <button
          type="button"
          onClick={() => setEditing(false)}
          className="min-h-11 rounded-xl border border-line px-4 text-sm font-semibold text-muted"
        >
          Cancel
        </button>
        <SubmitButton variant="danger" formAction={deleteLineItemAction}>
          Remove
        </SubmitButton>
      </div>
    </form>
  );
}

function Totals({ estimate }: { estimate: EstimateDetail }) {
  return (
    <Card>
      <dl className="space-y-2 p-4 text-sm">
        <Row label="Subtotal" value={formatCents(estimate.subtotal_cents)} />
        {estimate.tax_cents > 0 && (
          <Row
            label={`Tax (${rateToPercent(Number(estimate.tax_rate))}%)`}
            value={formatCents(estimate.tax_cents)}
          />
        )}
        <div className="flex items-baseline justify-between border-t border-line pt-2">
          <dt className="text-base font-bold text-ink">Total</dt>
          <dd className="text-xl font-bold text-brand">{formatCents(estimate.total_cents)}</dd>
        </div>
      </dl>
    </Card>
  );
}

function Row({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-baseline justify-between">
      <dt className="text-muted">{label}</dt>
      <dd className="font-medium text-ink">{value}</dd>
    </div>
  );
}

function ProposalPanel({
  estimate,
  org,
  proposalUrl,
  locked,
}: {
  estimate: EstimateDetail;
  org: Organization;
  proposalUrl: string | null;
  locked: boolean;
}) {
  const [state, action] = useActionState<FormState, FormData>(sendProposalAction, {});
  const proposal = estimate.proposal;
  const suggestedDeposit =
    proposal?.deposit_amount_cents ??
    depositFromPercent(estimate.total_cents, Number(org.default_deposit_percent));

  return (
    <Card title={proposal ? "Proposal" : "Send the proposal"}>
      <div className="space-y-4 p-4">
        {proposalUrl && (
          <div className="space-y-2 rounded-xl bg-brand-soft p-3">
            <p className="text-xs font-semibold uppercase tracking-wide text-brand">
              Customer link
            </p>
            <CopyLink url={proposalUrl} />
            <div className="flex flex-wrap gap-2 pt-1">
              <a
                href={proposalUrl}
                target="_blank"
                rel="noreferrer"
                className="rounded-lg border border-brand/30 bg-white px-3 py-1.5 text-xs font-semibold text-brand"
              >
                Preview
              </a>
              <a
                href={`${proposalUrl}/pdf`}
                className="rounded-lg border border-brand/30 bg-white px-3 py-1.5 text-xs font-semibold text-brand"
              >
                Download PDF
              </a>
              {estimate.lead.email && (
                <a
                  href={emailLink(estimate, org, proposalUrl)}
                  className="rounded-lg border border-brand/30 bg-white px-3 py-1.5 text-xs font-semibold text-brand"
                >
                  Email it
                </a>
              )}
            </div>
            <p className="pt-1 text-xs text-brand/80">
              {proposal?.signed_at
                ? `Signed ${new Date(proposal.signed_at).toLocaleString("en-US")}`
                : proposal?.first_viewed_at
                  ? `Viewed ${proposal.view_count} time${proposal.view_count === 1 ? "" : "s"} · last ${new Date(
                      proposal.viewed_at ?? proposal.first_viewed_at,
                    ).toLocaleString("en-US")}`
                  : "Not opened yet."}
            </p>
          </div>
        )}

        {!locked && (
          <form action={action} className="space-y-3">
            <ErrorText>{state.error}</ErrorText>
            {state.notice && <p className="text-sm text-emerald-700">{state.notice}</p>}
            <input type="hidden" name="estimate_id" value={estimate.id} />
            <Field label="Cover note" hint="Two lines in your voice beats a wall of text.">
              <textarea
                className={inputClass}
                name="cover_note"
                rows={3}
                defaultValue={
                  proposal?.cover_note ??
                  `Thanks for having us out, ${estimate.lead.contact_name.split(" ")[0]}. Here is exactly what we would do and what it costs. Questions any time — ${org.phone ?? "give us a call"}.`
                }
              />
            </Field>
            <Field label="Deposit requested" hint="Collected by card on the proposal page.">
              <input
                className={inputClass}
                name="deposit"
                inputMode="decimal"
                defaultValue={centsToInput(suggestedDeposit)}
              />
            </Field>
            <Field label="Terms">
              <textarea
                className={inputClass}
                name="terms"
                rows={5}
                defaultValue={proposal?.terms ?? org.default_terms ?? ""}
              />
            </Field>
            <SubmitButton className="w-full" pendingLabel="Publishing…">
              {proposal ? "Update proposal" : "Create proposal link"}
            </SubmitButton>
          </form>
        )}
      </div>
    </Card>
  );
}

function JobDetails({ estimate, locked }: { estimate: EstimateDetail; locked: boolean }) {
  const [state, action] = useActionState<FormState, FormData>(updateEstimateAction, {});
  const [open, setOpen] = useState(false);

  return (
    <Card
      title="Job & customer"
      action={
        <button
          type="button"
          onClick={() => setOpen((value) => !value)}
          className="text-sm font-semibold text-brand"
        >
          {open ? "Close" : "Edit"}
        </button>
      }
    >
      {!open ? (
        <dl className="space-y-1 p-4 text-sm">
          <Row label="Customer" value={estimate.lead.contact_name} />
          {estimate.lead.phone && <Row label="Phone" value={estimate.lead.phone} />}
          {estimate.lead.email && <Row label="Email" value={estimate.lead.email} />}
          {estimate.lead.job_address && <Row label="Address" value={estimate.lead.job_address} />}
          <Row label="Tax" value={`${rateToPercent(Number(estimate.tax_rate))}%`} />
        </dl>
      ) : (
        <form action={action} className="space-y-3 p-4">
          <ErrorText>{state.error}</ErrorText>
          {state.notice && <p className="text-sm text-emerald-700">{state.notice}</p>}
          <input type="hidden" name="estimate_id" value={estimate.id} />
          <input type="hidden" name="lead_id" value={estimate.lead.id} />
          <Field label="Job title">
            <input className={inputClass} name="title" defaultValue={estimate.title} required />
          </Field>
          <Field label="Customer name">
            <input
              className={inputClass}
              name="contact_name"
              defaultValue={estimate.lead.contact_name}
              required
            />
          </Field>
          <div className="grid gap-3 sm:grid-cols-2">
            <Field label="Phone">
              <input className={inputClass} name="phone" defaultValue={estimate.lead.phone ?? ""} />
            </Field>
            <Field label="Email">
              <input className={inputClass} name="email" defaultValue={estimate.lead.email ?? ""} />
            </Field>
          </div>
          <Field label="Job address">
            <input
              className={inputClass}
              name="job_address"
              defaultValue={estimate.lead.job_address ?? ""}
            />
          </Field>
          <Field label="Sales tax %">
            <input
              className={inputClass}
              name="tax_percent"
              inputMode="decimal"
              defaultValue={rateToPercent(Number(estimate.tax_rate))}
              disabled={locked}
            />
          </Field>
          <Field label="Internal notes">
            <textarea className={inputClass} name="notes" rows={3} defaultValue={estimate.notes ?? ""} />
          </Field>
          <SubmitButton pendingLabel="Saving…">Save</SubmitButton>
        </form>
      )}
    </Card>
  );
}

function CopyLink({ url }: { url: string }) {
  const [copied, setCopied] = useState(false);

  return (
    <div className="flex items-center gap-2">
      <input
        readOnly
        value={url}
        onFocus={(event) => event.currentTarget.select()}
        className="min-w-0 flex-1 rounded-lg border border-brand/20 bg-white px-2.5 py-2 text-xs text-ink"
      />
      <button
        type="button"
        onClick={async () => {
          try {
            await navigator.clipboard.writeText(url);
            setCopied(true);
            setTimeout(() => setCopied(false), 2000);
          } catch {
            setCopied(false);
          }
        }}
        className="shrink-0 rounded-lg bg-brand px-3 py-2 text-xs font-semibold text-white"
      >
        {copied ? "Copied" : "Copy"}
      </button>
    </div>
  );
}

function emailLink(estimate: EstimateDetail, org: Organization, url: string): string {
  const subject = `${estimate.title} — proposal from ${org.name}`;
  const body = `Hi ${estimate.lead.contact_name.split(" ")[0]},\n\nHere is your proposal: ${url}\n\nYou can review it, ask questions, and accept it right from that page.\n\n— ${org.name}`;
  return `mailto:${estimate.lead.email}?subject=${encodeURIComponent(subject)}&body=${encodeURIComponent(body)}`;
}

function groupByCategory(items: PriceBookItem[]): [string, PriceBookItem[]][] {
  const map = new Map<string, PriceBookItem[]>();
  for (const item of items) {
    const list = map.get(item.category) ?? [];
    list.push(item);
    map.set(item.category, list);
  }
  return [...map.entries()].sort(([a], [b]) => a.localeCompare(b));
}
