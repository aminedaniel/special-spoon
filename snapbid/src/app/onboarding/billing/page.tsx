import Link from "next/link";
import { redirect } from "next/navigation";
import { requireSession } from "@/lib/db/session";
import { startBillingCheckout } from "../actions";
import { SubmitButton } from "@/components/SubmitButton";
import { ErrorText } from "@/components/ui";
import { isStripeConfigured } from "@/lib/stripe";
import { GUARANTEE_WINDOW_DAYS } from "@/lib/guarantee";

export default async function BillingPage({
  searchParams,
}: {
  searchParams: Promise<{ billing?: string }>;
}) {
  const session = await requireSession({ allowOnboarding: true });
  if (session.org.stripe_subscription_id) redirect("/dashboard");
  const { billing } = await searchParams;

  const billingDate = session.org.billing_starts_at
    ? new Date(session.org.billing_starts_at).toLocaleDateString("en-US", {
        month: "long",
        day: "numeric",
      })
    : null;

  async function submit() {
    "use server";
    const result = await startBillingCheckout();
    if (result?.error) throw new Error(result.error);
  }

  return (
    <main className="mx-auto w-full max-w-md px-5 py-10">
      <p className="text-2xl font-black tracking-tight text-brand">SnapBid</p>
      <div className="mt-6 rounded-2xl border border-line bg-surface p-5 shadow-sm">
        <h1 className="text-xl font-bold text-ink">Your {GUARANTEE_WINDOW_DAYS} days start now</h1>
        <p className="mt-2 text-sm text-muted">
          Sign one job through SnapBid in the next {GUARANTEE_WINDOW_DAYS} days or your first month
          is free. We save a card now so nothing interrupts you later —{" "}
          <strong className="font-semibold text-ink">
            you are not charged today{billingDate ? `, and not before ${billingDate}` : ""}
          </strong>
          .
        </p>

        {billing === "cancelled" && (
          <div className="mt-4">
            <ErrorText>Checkout was cancelled. You can add a card any time.</ErrorText>
          </div>
        )}

        {isStripeConfigured() ? (
          <form action={submit} className="mt-5 space-y-3">
            <SubmitButton className="w-full" pendingLabel="Opening Stripe…">
              Save a card
            </SubmitButton>
            <Link
              href="/dashboard"
              className="block text-center text-sm font-semibold text-muted hover:text-ink"
            >
              I&apos;ll do this later
            </Link>
          </form>
        ) : (
          <div className="mt-5 space-y-3">
            <p className="rounded-xl border border-amber-200 bg-amber-50 px-3 py-2 text-sm text-amber-800">
              Stripe is not configured on this deployment, so card capture is skipped. Set
              STRIPE_SECRET_KEY and STRIPE_SUBSCRIPTION_PRICE_ID to enable it.
            </p>
            <Link
              href="/dashboard"
              className="flex min-h-11 items-center justify-center rounded-xl bg-brand px-4 text-sm font-semibold text-white"
            >
              Go to dashboard
            </Link>
          </div>
        )}
      </div>
    </main>
  );
}
