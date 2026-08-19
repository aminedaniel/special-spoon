import { NextResponse } from "next/server";
import type Stripe from "stripe";
import { getStripe, isStripeConfigured } from "@/lib/stripe";
import { createAdminClient } from "@/lib/supabase/admin";
import { requiredEnv } from "@/lib/env";

export const runtime = "nodejs";

/**
 * Stripe webhook. Verifies the signature against the raw body, then records
 * what happened. Everything here is idempotent: Stripe retries, and a deposit
 * must never be recorded twice (payments.stripe_ref is unique).
 */
export async function POST(request: Request) {
  if (!isStripeConfigured()) {
    return NextResponse.json({ error: "Stripe is not configured." }, { status: 503 });
  }

  const signature = request.headers.get("stripe-signature");
  if (!signature) return NextResponse.json({ error: "Missing signature." }, { status: 400 });

  const payload = await request.text();
  let event: Stripe.Event;
  try {
    event = getStripe().webhooks.constructEvent(
      payload,
      signature,
      requiredEnv("STRIPE_WEBHOOK_SECRET"),
    );
  } catch {
    return NextResponse.json({ error: "Invalid signature." }, { status: 400 });
  }

  const admin = createAdminClient();

  switch (event.type) {
    case "checkout.session.completed": {
      const session = event.data.object;
      const orgId = session.metadata?.org_id ?? session.client_reference_id ?? null;
      if (!orgId) break;

      if (session.mode === "subscription") {
        await admin
          .from("organizations")
          .update({
            stripe_customer_id:
              typeof session.customer === "string" ? session.customer : session.customer?.id ?? null,
            stripe_subscription_id:
              typeof session.subscription === "string"
                ? session.subscription
                : session.subscription?.id ?? null,
          })
          .eq("id", orgId);
      }

      if (session.mode === "payment" && session.metadata?.proposal_id) {
        const reference =
          typeof session.payment_intent === "string"
            ? session.payment_intent
            : (session.payment_intent?.id ?? session.id);
        await admin.from("payments").upsert(
          {
            org_id: orgId,
            proposal_id: session.metadata.proposal_id,
            type: "deposit",
            amount_cents: session.amount_total ?? 0,
            currency: session.currency ?? "usd",
            status: session.payment_status === "paid" ? "succeeded" : "pending",
            stripe_ref: reference,
          },
          { onConflict: "stripe_ref" },
        );
      }
      break;
    }

    case "invoice.paid":
    case "invoice.payment_failed": {
      const invoice = event.data.object;
      const orgId = invoice.parent?.subscription_details?.metadata?.org_id ?? null;
      if (!orgId) break;
      await admin.from("payments").upsert(
        {
          org_id: orgId,
          type: "subscription",
          amount_cents: invoice.amount_paid || invoice.amount_due || 0,
          currency: invoice.currency ?? "usd",
          status: event.type === "invoice.paid" ? "succeeded" : "failed",
          stripe_ref: invoice.id,
        },
        { onConflict: "stripe_ref" },
      );
      break;
    }

    default:
      break;
  }

  return NextResponse.json({ received: true });
}
