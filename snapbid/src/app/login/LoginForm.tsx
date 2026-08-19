"use client";

import Link from "next/link";
import { useActionState } from "react";
import { loginAction, type AuthFormState } from "./actions";
import { SubmitButton } from "@/components/SubmitButton";
import { ErrorText, Field, inputClass } from "@/components/ui";

export function LoginForm({ next }: { next: string }) {
  const [state, action] = useActionState<AuthFormState, FormData>(loginAction, {});

  return (
    <form action={action} className="space-y-4">
      <input type="hidden" name="next" value={next} />
      <ErrorText>{state.error}</ErrorText>
      <Field label="Email">
        <input className={inputClass} type="email" name="email" autoComplete="email" required />
      </Field>
      <Field label="Password">
        <input
          className={inputClass}
          type="password"
          name="password"
          autoComplete="current-password"
          required
        />
      </Field>
      <SubmitButton className="w-full" pendingLabel="Signing in…">
        Sign in
      </SubmitButton>
      <p className="text-center text-sm text-muted">
        New here?{" "}
        <Link className="font-semibold text-brand" href="/signup">
          Create an account
        </Link>
      </p>
    </form>
  );
}
