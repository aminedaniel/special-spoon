"use client";

import { useState, useTransition } from "react";
import { useRouter } from "next/navigation";
import { formatCents } from "@/lib/money";

export function AcceptPanel({
  token,
  brand,
  customerName,
  depositCents,
  signedAt,
  signatureName,
  declinedAt,
}: {
  token: string;
  brand: string;
  customerName: string;
  depositCents: number;
  signedAt: string | null;
  signatureName: string | null;
  declinedAt: string | null;
}) {
  const router = useRouter();
  const [name, setName] = useState(customerName);
  const [agreed, setAgreed] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [pending, startTransition] = useTransition();

  if (signedAt) {
    return (
      <section className="mt-4 rounded-2xl border border-emerald-200 bg-emerald-50 p-5">
        <p className="text-sm font-bold text-emerald-900">Accepted — thank you.</p>
        <p className="mt-1 text-sm text-emerald-800">
          Signed by {signatureName ?? customerName} on{" "}
          {new Date(signedAt).toLocaleString("en-US")}.
        </p>
        {depositCents > 0 && (
          <form method="post" action={`/api/proposals/${token}/deposit`} className="mt-4">
            <button
              type="submit"
              className="min-h-12 w-full rounded-xl px-4 text-sm font-semibold text-white"
              style={{ background: brand }}
            >
              Pay the {formatCents(depositCents)} deposit
            </button>
          </form>
        )}
      </section>
    );
  }

  async function submit(action: "sign" | "decline") {
    setError(null);
    if (action === "sign") {
      if (name.trim().length < 2) return setError("Type your full name to sign.");
      if (!agreed) return setError("Tick the box to accept the scope and price.");
    }

    const response = await fetch(`/api/proposals/${token}/${action}`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ signature_name: name.trim() }),
    });

    if (!response.ok) {
      setError("Something went wrong. Please try again or call us.");
      return;
    }

    const payload = (await response.json()) as { checkout_url?: string };
    if (payload.checkout_url) {
      window.location.href = payload.checkout_url;
      return;
    }
    startTransition(() => router.refresh());
  }

  return (
    <section className="mt-4 rounded-2xl border border-line bg-surface p-5 shadow-sm">
      <h2 className="text-sm font-semibold text-ink">Accept this proposal</h2>
      <p className="mt-1 text-xs text-muted">
        Typing your name below is your electronic signature. We record the time and date.
      </p>

      {declinedAt && (
        <p className="mt-3 rounded-xl bg-gray-100 px-3 py-2 text-xs text-muted">
          You passed on this proposal on {new Date(declinedAt).toLocaleDateString("en-US")}. You can
          still accept it if you have changed your mind.
        </p>
      )}

      <label className="mt-4 block text-sm font-medium text-ink" htmlFor="signature">
        Full name
      </label>
      <input
        id="signature"
        value={name}
        onChange={(event) => setName(event.target.value)}
        className="mt-1 w-full rounded-xl border border-line px-3 py-2.5 text-ink outline-none focus:border-brand"
        autoComplete="name"
      />

      <label className="mt-3 flex items-start gap-2 text-sm text-ink">
        <input
          type="checkbox"
          checked={agreed}
          onChange={(event) => setAgreed(event.target.checked)}
          className="mt-1 h-4 w-4"
        />
        <span>I accept the scope of work, the price, and the terms shown here.</span>
      </label>

      {error && <p className="mt-3 text-sm text-red-600">{error}</p>}

      <button
        type="button"
        disabled={pending}
        onClick={() => submit("sign")}
        className="mt-4 min-h-12 w-full rounded-xl px-4 text-sm font-semibold text-white disabled:opacity-60"
        style={{ background: brand }}
      >
        {depositCents > 0
          ? `Accept and pay ${formatCents(depositCents)} deposit`
          : "Accept proposal"}
      </button>

      <button
        type="button"
        disabled={pending}
        onClick={() => submit("decline")}
        className="mt-2 min-h-11 w-full rounded-xl border border-line px-4 text-sm font-semibold text-muted"
      >
        Not right now
      </button>
    </section>
  );
}
