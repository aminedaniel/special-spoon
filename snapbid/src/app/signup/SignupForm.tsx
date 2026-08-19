"use client";

import Link from "next/link";
import { useActionState } from "react";
import { signupAction } from "./actions";
import type { AuthFormState } from "@/app/login/actions";
import { SubmitButton } from "@/components/SubmitButton";
import { ErrorText, Field, inputClass } from "@/components/ui";

export function SignupForm() {
  const [state, action] = useActionState<AuthFormState, FormData>(signupAction, {});

  if (state.notice) {
    return (
      <div className="space-y-4">
        <p className="rounded-xl border border-emerald-200 bg-emerald-50 px-3 py-2 text-sm text-emerald-800">
          {state.notice}
        </p>
        <Link className="font-semibold text-brand" href="/login">
          Go to sign in
        </Link>
      </div>
    );
  }

  return (
    <form action={action} className="space-y-4">
      <ErrorText>{state.error}</ErrorText>
      <Field label="Business name">
        <input className={inputClass} name="business_name" autoComplete="organization" required />
      </Field>
      <Field label="Your name">
        <input className={inputClass} name="full_name" autoComplete="name" required />
      </Field>
      <Field label="Email">
        <input className={inputClass} type="email" name="email" autoComplete="email" required />
      </Field>
      <Field label="Password" hint="At least 8 characters.">
        <input
          className={inputClass}
          type="password"
          name="password"
          autoComplete="new-password"
          minLength={8}
          required
        />
      </Field>
      <SubmitButton className="w-full" pendingLabel="Creating your account…">
        Create account
      </SubmitButton>
      <p className="text-center text-sm text-muted">
        Already have an account?{" "}
        <Link className="font-semibold text-brand" href="/login">
          Sign in
        </Link>
      </p>
    </form>
  );
}
