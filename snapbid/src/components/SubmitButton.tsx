"use client";

import { useFormStatus } from "react-dom";

type Variant = "primary" | "secondary" | "danger";

const VARIANTS: Record<Variant, string> = {
  primary: "bg-brand text-white hover:bg-blue-800 disabled:bg-blue-300",
  secondary: "border border-line bg-white text-ink hover:bg-gray-50 disabled:text-muted",
  danger: "border border-red-200 bg-white text-red-700 hover:bg-red-50",
};

export function SubmitButton({
  children,
  variant = "primary",
  pendingLabel,
  className = "",
  formAction,
  name,
  value,
}: {
  children: React.ReactNode;
  variant?: Variant;
  pendingLabel?: string;
  className?: string;
  formAction?: (formData: FormData) => void | Promise<void>;
  name?: string;
  value?: string;
}) {
  const { pending } = useFormStatus();
  return (
    <button
      type="submit"
      formAction={formAction}
      name={name}
      value={value}
      disabled={pending}
      className={`inline-flex min-h-11 items-center justify-center gap-2 rounded-xl px-4 py-2.5 text-sm font-semibold transition disabled:cursor-not-allowed ${VARIANTS[variant]} ${className}`}
    >
      {pending && pendingLabel ? pendingLabel : children}
    </button>
  );
}
