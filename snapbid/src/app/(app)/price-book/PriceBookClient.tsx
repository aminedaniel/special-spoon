"use client";

import { useActionState, useMemo, useState } from "react";
import {
  addItemAction,
  importCsvAction,
  removeItemAction,
  updateItemAction,
  type PriceBookState,
} from "./actions";
import { SubmitButton } from "@/components/SubmitButton";
import { Card, ErrorText, Field, inputClass } from "@/components/ui";
import { centsToInput, formatCents } from "@/lib/money";
import { UNITS } from "@/lib/seed/price-books";
import type { PriceBookItem } from "@/lib/types";

export function PriceBookClient({ items }: { items: PriceBookItem[] }) {
  const [query, setQuery] = useState("");
  const [addState, addAction] = useActionState<PriceBookState, FormData>(addItemAction, {});
  const [importState, importAction] = useActionState<PriceBookState, FormData>(importCsvAction, {});

  const grouped = useMemo(() => {
    const needle = query.trim().toLowerCase();
    const matches = needle
      ? items.filter(
          (item) =>
            item.name.toLowerCase().includes(needle) ||
            item.category.toLowerCase().includes(needle),
        )
      : items;

    const map = new Map<string, PriceBookItem[]>();
    for (const item of matches) {
      const list = map.get(item.category) ?? [];
      list.push(item);
      map.set(item.category, list);
    }
    return [...map.entries()].sort(([a], [b]) => a.localeCompare(b));
  }, [items, query]);

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-xl font-bold text-ink">Price book</h1>
          <p className="text-sm text-muted">
            {items.length} items. Estimates are assembled from these prices — nothing is invented.
          </p>
        </div>
        <a
          href="/price-book/export"
          className="inline-flex min-h-11 items-center rounded-xl border border-line bg-white px-4 text-sm font-semibold text-ink"
        >
          Export CSV
        </a>
      </div>

      <input
        className={inputClass}
        placeholder="Search items or categories"
        value={query}
        onChange={(event) => setQuery(event.target.value)}
      />

      <Card title="Add an item">
        <form action={addAction} className="space-y-3 p-4">
          <ErrorText>{addState.error}</ErrorText>
          {addState.notice && <p className="text-sm text-emerald-700">{addState.notice}</p>}
          <Field label="Name">
            <input className={inputClass} name="name" required />
          </Field>
          <div className="grid grid-cols-2 gap-3">
            <Field label="Category">
              <input className={inputClass} name="category" placeholder="General" list="pb-categories" />
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
          </div>
          <Field label="Unit price">
            <input className={inputClass} name="price" inputMode="decimal" placeholder="450.00" required />
          </Field>
          <datalist id="pb-categories">
            {[...new Set(items.map((item) => item.category))].map((category) => (
              <option key={category} value={category} />
            ))}
          </datalist>
          <SubmitButton pendingLabel="Adding…">Add item</SubmitButton>
        </form>
      </Card>

      <Card title="Import a CSV">
        <form action={importAction} className="space-y-3 p-4">
          <ErrorText>{importState.error}</ErrorText>
          {importState.notice && <p className="text-sm text-emerald-700">{importState.notice}</p>}
          {importState.warnings?.length ? (
            <ul className="space-y-1 rounded-xl bg-amber-50 p-3 text-xs text-amber-900">
              {importState.warnings.map((warning) => (
                <li key={warning}>{warning}</li>
              ))}
            </ul>
          ) : null}
          <p className="text-sm text-muted">
            Columns: <code>name, category, unit, price</code> (a <code>description</code> column is
            optional). Headers like &quot;item&quot; and &quot;rate&quot; are understood too.
          </p>
          <input className={inputClass} type="file" name="file" accept=".csv,text/csv" required />
          <SubmitButton variant="secondary" pendingLabel="Importing…">
            Import
          </SubmitButton>
        </form>
      </Card>

      {grouped.map(([category, categoryItems]) => (
        <Card key={category} title={category}>
          <ul className="divide-y divide-line">
            {categoryItems.map((item) => (
              <li key={item.id} className="p-3">
                <PriceBookRow item={item} />
              </li>
            ))}
          </ul>
        </Card>
      ))}

      {grouped.length === 0 && (
        <p className="px-4 py-8 text-center text-sm text-muted">Nothing matches “{query}”.</p>
      )}
    </div>
  );
}

function PriceBookRow({ item }: { item: PriceBookItem }) {
  const [editing, setEditing] = useState(false);

  if (!editing) {
    return (
      <div className="flex items-center justify-between gap-3">
        <div className="min-w-0">
          <p className="truncate text-sm font-medium text-ink">{item.name}</p>
          <p className="text-xs text-muted">per {item.unit}</p>
        </div>
        <div className="flex shrink-0 items-center gap-3">
          <span className="text-sm font-semibold text-ink">{formatCents(item.unit_price_cents)}</span>
          <button
            type="button"
            onClick={() => setEditing(true)}
            className="rounded-lg border border-line px-2.5 py-1.5 text-xs font-semibold text-muted hover:text-ink"
          >
            Edit
          </button>
        </div>
      </div>
    );
  }

  return (
    <form action={updateItemAction} className="space-y-2" onSubmit={() => setEditing(false)}>
      <input type="hidden" name="id" value={item.id} />
      <input className={inputClass} name="name" defaultValue={item.name} required />
      <div className="grid grid-cols-2 gap-2">
        <select className={inputClass} name="unit" defaultValue={item.unit}>
          {[...new Set([item.unit, ...UNITS])].map((unit) => (
            <option key={unit} value={unit}>
              {unit}
            </option>
          ))}
        </select>
        <input
          className={inputClass}
          name="price"
          inputMode="decimal"
          defaultValue={centsToInput(item.unit_price_cents)}
          required
        />
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
        <SubmitButton variant="danger" formAction={removeItemAction}>
          Remove
        </SubmitButton>
      </div>
    </form>
  );
}
