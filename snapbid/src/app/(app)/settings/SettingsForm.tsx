"use client";

import { useActionState } from "react";
import { saveSettings, type SettingsState } from "./actions";
import { SubmitButton } from "@/components/SubmitButton";
import { Card, ErrorText, Field, inputClass } from "@/components/ui";
import type { Organization } from "@/lib/types";
import { rateToPercent } from "@/lib/money";

export function SettingsForm({ org }: { org: Organization }) {
  const [state, action] = useActionState<SettingsState, FormData>(saveSettings, {});

  return (
    <form action={action} className="space-y-5">
      <ErrorText>{state.error}</ErrorText>
      {state.notice && <p className="text-sm text-emerald-700">{state.notice}</p>}

      <Card title="Business">
        <div className="space-y-4 p-4">
          <Field label="Business name">
            <input className={inputClass} name="name" defaultValue={org.name} required />
          </Field>
          <div className="grid gap-4 sm:grid-cols-2">
            <Field label="Phone">
              <input className={inputClass} name="phone" defaultValue={org.phone ?? ""} />
            </Field>
            <Field label="Email">
              <input className={inputClass} name="email" type="email" defaultValue={org.email ?? ""} />
            </Field>
          </div>
          <Field label="Address">
            <input className={inputClass} name="address" defaultValue={org.address ?? ""} />
          </Field>
        </div>
      </Card>

      <Card title="Branding">
        <div className="space-y-4 p-4">
          {org.logo_url && (
            // eslint-disable-next-line @next/next/no-img-element
            <img src={org.logo_url} alt="" className="h-12 w-auto object-contain" />
          )}
          <Field label="Replace logo" hint="PNG, JPG, WEBP or SVG, under 2 MB.">
            <input className={inputClass} type="file" name="logo" accept="image/*" />
          </Field>
          <Field label="Brand color">
            <input
              className="h-12 w-full cursor-pointer rounded-xl border border-line bg-white p-1"
              type="color"
              name="brand_color"
              defaultValue={org.brand_color}
            />
          </Field>
        </div>
      </Card>

      <Card title="Proposal defaults">
        <div className="space-y-4 p-4">
          <div className="grid gap-4 sm:grid-cols-2">
            <Field label="Sales tax %">
              <input
                className={inputClass}
                name="default_tax_rate"
                inputMode="decimal"
                defaultValue={rateToPercent(Number(org.default_tax_rate))}
              />
            </Field>
            <Field label="Deposit %">
              <input
                className={inputClass}
                name="default_deposit_percent"
                inputMode="decimal"
                defaultValue={String(Number(org.default_deposit_percent))}
              />
            </Field>
          </div>
          <Field label="Default terms" hint="Pre-filled on every proposal; editable per job.">
            <textarea
              className={inputClass}
              name="default_terms"
              rows={7}
              defaultValue={org.default_terms ?? ""}
            />
          </Field>
        </div>
      </Card>

      <SubmitButton className="w-full" pendingLabel="Saving…">
        Save settings
      </SubmitButton>
    </form>
  );
}
