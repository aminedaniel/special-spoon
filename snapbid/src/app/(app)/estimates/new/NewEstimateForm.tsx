"use client";

import { useActionState } from "react";
import { createEstimateAction, type FormState } from "../actions";
import { SubmitButton } from "@/components/SubmitButton";
import { ErrorText, Field, inputClass } from "@/components/ui";

export function NewEstimateForm({ defaultTaxPercent }: { defaultTaxPercent: string }) {
  const [state, action] = useActionState<FormState, FormData>(createEstimateAction, {});

  return (
    <form action={action} className="space-y-4">
      <ErrorText>{state.error}</ErrorText>
      <Field label="Customer name">
        <input className={inputClass} name="contact_name" autoComplete="name" required />
      </Field>
      <div className="grid gap-4 sm:grid-cols-2">
        <Field label="Phone">
          <input className={inputClass} name="phone" type="tel" />
        </Field>
        <Field label="Email" hint="Where the proposal link goes.">
          <input className={inputClass} name="email" type="email" />
        </Field>
      </div>
      <Field label="Job address">
        <input className={inputClass} name="job_address" />
      </Field>
      <div className="grid gap-4 sm:grid-cols-2">
        <Field label="Job title">
          <input
            className={inputClass}
            name="title"
            placeholder="Roof replacement"
            defaultValue="Roof replacement"
            required
          />
        </Field>
        <Field label="Sales tax %">
          <input
            className={inputClass}
            name="tax_percent"
            inputMode="decimal"
            defaultValue={defaultTaxPercent}
          />
        </Field>
      </div>
      <Field label="Where did this lead come from?" hint="Optional — useful once you compare sources.">
        <input className={inputClass} name="source" placeholder="Angi, referral, Google" />
      </Field>
      <Field label="Internal notes" hint="Never shown to the customer.">
        <textarea className={inputClass} name="notes" rows={3} />
      </Field>
      <SubmitButton className="w-full" pendingLabel="Creating…">
        Start the estimate
      </SubmitButton>
    </form>
  );
}
