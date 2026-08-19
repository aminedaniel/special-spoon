import Stripe from "stripe";
import { optionalEnv, requiredEnv } from "@/lib/env";

let cached: Stripe | null = null;

export function isStripeConfigured(): boolean {
  return Boolean(process.env.STRIPE_SECRET_KEY);
}

export function getStripe(): Stripe {
  if (!cached) {
    cached = new Stripe(requiredEnv("STRIPE_SECRET_KEY"), { apiVersion: "2025-08-27.basil" });
  }
  return cached;
}

export function unixSeconds(iso: string | Date): number {
  const date = typeof iso === "string" ? new Date(iso) : iso;
  return Math.floor(date.getTime() / 1000);
}

/**
 * Subscription checkout that collects a card but charges nothing today: the
 * subscription is created with `trial_end = billing_starts_at`, which is how
 * the 14-day guarantee is enforced in billing rather than by hand.
 *
 * Stripe requires a trial end at least 48 hours out, so a very short window
 * (only reachable in testing) falls back to the minimum.
 */
export async function createSubscriptionCheckout(args: {
  orgId: string;
  email: string;
  billingStartsAt: string;
  successUrl: string;
  cancelUrl: string;
  existingCustomerId?: string | null;
}): Promise<string> {
  const stripe = getStripe();
  const minimum = Math.floor(Date.now() / 1000) + 49 * 60 * 60;
  const trialEnd = Math.max(unixSeconds(args.billingStartsAt), minimum);

  const session = await stripe.checkout.sessions.create({
    mode: "subscription",
    line_items: [{ price: requiredEnv("STRIPE_SUBSCRIPTION_PRICE_ID"), quantity: 1 }],
    payment_method_collection: "always",
    ...(args.existingCustomerId
      ? { customer: args.existingCustomerId }
      : { customer_email: args.email, customer_creation: "always" as const }),
    subscription_data: {
      trial_end: trialEnd,
      metadata: { org_id: args.orgId },
    },
    client_reference_id: args.orgId,
    metadata: { org_id: args.orgId, kind: "subscription" },
    success_url: args.successUrl,
    cancel_url: args.cancelUrl,
  });

  if (!session.url) throw new Error("Stripe did not return a checkout URL.");
  return session.url;
}

/**
 * Push the first charge out and — when a comp coupon is configured — make the
 * comped month literal rather than just deferred.
 */
export async function compAndExtendSubscription(args: {
  subscriptionId: string;
  newBillingStartsAt: string;
}): Promise<void> {
  const stripe = getStripe();
  const couponId = optionalEnv("STRIPE_COMP_COUPON_ID");
  await stripe.subscriptions.update(args.subscriptionId, {
    trial_end: unixSeconds(args.newBillingStartsAt),
    proration_behavior: "none",
    ...(couponId ? { discounts: [{ coupon: couponId }] } : {}),
  });
}

/** Deposit checkout on the customer-facing proposal page. */
export async function createDepositCheckout(args: {
  orgId: string;
  orgName: string;
  proposalId: string;
  proposalToken: string;
  amountCents: number;
  jobTitle: string;
  customerEmail: string | null;
  connectAccountId: string | null;
  successUrl: string;
  cancelUrl: string;
}): Promise<string> {
  const stripe = getStripe();
  const session = await stripe.checkout.sessions.create({
    mode: "payment",
    line_items: [
      {
        quantity: 1,
        price_data: {
          currency: "usd",
          unit_amount: args.amountCents,
          product_data: {
            name: `Deposit — ${args.jobTitle}`,
            description: `Deposit toward work by ${args.orgName}`,
          },
        },
      },
    ],
    ...(args.customerEmail ? { customer_email: args.customerEmail } : {}),
    payment_intent_data: {
      metadata: { org_id: args.orgId, proposal_id: args.proposalId, kind: "deposit" },
      // With Stripe Connect configured, the deposit settles into the
      // contractor's own account; otherwise it lands on the platform account
      // and is paid out manually.
      ...(args.connectAccountId
        ? { transfer_data: { destination: args.connectAccountId } }
        : {}),
    },
    metadata: {
      org_id: args.orgId,
      proposal_id: args.proposalId,
      proposal_token: args.proposalToken,
      kind: "deposit",
    },
    success_url: args.successUrl,
    cancel_url: args.cancelUrl,
  });

  if (!session.url) throw new Error("Stripe did not return a checkout URL.");
  return session.url;
}
