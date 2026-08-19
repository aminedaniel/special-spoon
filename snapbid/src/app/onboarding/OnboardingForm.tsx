"use client";

import { useActionState, useState } from "react";
import { completeOnboarding, type OnboardingState } from "./actions";
import { SubmitButton } from "@/components/SubmitButton";
import { ErrorText, Field, inputClass } from "@/components/ui";
import { TRADE_LABELS, TRADES, type Trade } from "@/lib/types";
import { PRICE_BOOK_TEMPLATES } from "@/lib/seed/price-books";

const TRADE_BLURB: Record<Trade, string> = {
  roofing: "Squares, tear-off layers, decking, underlayment, flashing, vents, gutters.",
  remodeling: "Demo, framing, cabinetry, counters, tile, fixtures, and labor phases.",
};

export function OnboardingForm({
  defaults,
}: {
  defaults: { name: string; trade: Trade; email: string | null };
}) {
  const [state, action] = useActionState<OnboardingState, FormData>(completeOnboarding, {});
  const [trade, setTrade] = useState<Trade>(defaults.trade);

  return (
    <form action={action} className="space-y-6">
      <ErrorText>{state.error}</ErrorText>

      <fieldset className="space-y-3">
        <legend className="text-sm font-semibold text-ink">1. What do you do?</legend>
        <p className="text-sm text-muted">
          This picks your starting price book and the language on your proposals.
        </p>
        <div className="grid gap-3 sm:grid-cols-2">
          {TRADES.map((option) => (
            <label
              key={option}
              className={`cursor-pointer rounded-2xl border p-4 transition ${
                trade === option
                  ? "border-brand bg-brand-soft ring-2 ring-brand/20"
                  : "border-line bg-white hover:border-gray-300"
              }`}
            >
              <input
                type="radio"
                name="trade"
                value={option}
                className="sr-only"
                checked={trade === option}
                onChange={() => setTrade(option)}
              />
              <span className="block text-sm font-semibold text-ink">{TRADE_LABELS[option]}</span>
              <span className="mt-1 block text-xs text-muted">{TRADE_BLURB[option]}</span>
              <span className="mt-2 block text-xs font-medium text-brand">
                {PRICE_BOOK_TEMPLATES[option].length} line items ready to edit
              </span>
            </label>
          ))}
        </div>
      </fieldset>

      <fieldset className="space-y-4">
        <legend className="text-sm font-semibold text-ink">2. Your branding</legend>
        <Field label="Business name">
          <input className={inputClass} name="name" defaultValue={defaults.name} required />
        </Field>
        <div className="grid gap-4 sm:grid-cols-2">
          <Field label="Phone">
            <input className={inputClass} name="phone" type="tel" placeholder="(555) 555-0134" />
          </Field>
          <Field label="Business email">
            <input
              className={inputClass}
              name="email"
              type="email"
              defaultValue={defaults.email ?? ""}
            />
          </Field>
        </div>
        <Field label="Address" hint="Shown in the proposal header.">
          <input className={inputClass} name="address" />
        </Field>
        <div className="grid gap-4 sm:grid-cols-2">
          <Field label="Logo" hint="PNG, JPG, WEBP or SVG, under 2 MB.">
            <input className={inputClass} name="logo" type="file" accept="image/*" />
          </Field>
          <Field label="Brand color">
            <input
              className="h-12 w-full cursor-pointer rounded-xl border border-line bg-white p-1"
              name="brand_color"
              type="color"
              defaultValue="#1d4ed8"
            />
          </Field>
        </div>
      </fieldset>

      <fieldset className="space-y-4">
        <legend className="text-sm font-semibold text-ink">3. Defaults</legend>
        <div className="grid gap-4 sm:grid-cols-2">
          <Field label="Sales tax %" hint="Applied to new estimates; editable per job.">
            <input
              className={inputClass}
              name="default_tax_rate"
              inputMode="decimal"
              defaultValue="0"
            />
          </Field>
          <Field label="Deposit %" hint="Pre-filled on every proposal.">
            <input
              className={inputClass}
              name="default_deposit_percent"
              inputMode="decimal"
              defaultValue="25"
            />
          </Field>
        </div>
      </fieldset>

      <SubmitButton className="w-full" pendingLabel="Setting up your workspace…">
        Finish setup
      </SubmitButton>
    </form>
  );
}
