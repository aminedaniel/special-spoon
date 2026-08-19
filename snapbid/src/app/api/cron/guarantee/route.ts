import { NextResponse, type NextRequest } from "next/server";
import { createAdminClient } from "@/lib/supabase/admin";
import { evaluateLapse, windowEndsAt, type GuaranteeState } from "@/lib/guarantee";
import { compAndExtendSubscription, isStripeConfigured } from "@/lib/stripe";
import { optionalEnv } from "@/lib/env";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

interface OrgRow extends GuaranteeState {
  id: string;
  name: string;
  stripe_subscription_id: string | null;
}

/**
 * Daily guarantee sweep. Any account whose window has lapsed without a signed
 * proposal gets its first month comped and the window extended once — without
 * anyone at SnapBid having to remember.
 *
 * Wired up in vercel.json; run it locally with
 *   curl -H "Authorization: Bearer $CRON_SECRET" localhost:3000/api/cron/guarantee
 */
async function handle(request: NextRequest) {
  const secret = optionalEnv("CRON_SECRET");
  if (!secret) {
    return NextResponse.json({ error: "CRON_SECRET is not configured." }, { status: 503 });
  }
  const provided =
    request.headers.get("authorization")?.replace(/^Bearer\s+/i, "") ??
    request.nextUrl.searchParams.get("secret");
  if (provided !== secret) {
    return NextResponse.json({ error: "Unauthorized." }, { status: 401 });
  }

  const admin = createAdminClient();
  const now = new Date();

  const { data, error } = await admin
    .from("organizations")
    .select(
      "id, name, stripe_subscription_id, guarantee_started_at, guarantee_met_at, guarantee_status, billing_starts_at, guarantee_extended_at",
    )
    .in("guarantee_status", ["active", "extended"])
    .lte("billing_starts_at", now.toISOString());

  if (error) {
    return NextResponse.json({ error: error.message }, { status: 500 });
  }

  const results: { org_id: string; action: string }[] = [];

  for (const row of (data ?? []) as OrgRow[]) {
    const end = windowEndsAt(row);
    if (!end) continue;

    // "Signed inside the window" is the whole test — check it against the
    // proposals themselves rather than trusting a flag.
    const { count } = await admin
      .from("proposals")
      .select("id", { count: "exact", head: true })
      .eq("org_id", row.id)
      .not("signed_at", "is", null)
      .lte("signed_at", end.toISOString());

    const action = evaluateLapse(row, (count ?? 0) > 0, now);

    if (action.kind === "none") {
      // A signature we somehow missed still counts.
      if ((count ?? 0) > 0 && row.guarantee_status !== "met") {
        await admin
          .from("organizations")
          .update({ guarantee_status: "met", guarantee_met_at: row.guarantee_met_at ?? now.toISOString() })
          .eq("id", row.id);
        results.push({ org_id: row.id, action: "met" });
      }
      continue;
    }

    await admin.from("organizations").update(action.patch).eq("id", row.id);

    if (action.kind === "comp_and_extend" && row.stripe_subscription_id && isStripeConfigured()) {
      try {
        await compAndExtendSubscription({
          subscriptionId: row.stripe_subscription_id,
          newBillingStartsAt: action.patch.billing_starts_at,
        });
      } catch (stripeError) {
        // The database is the source of truth for the guarantee; a Stripe
        // hiccup must not lose the comp.
        console.error(`Stripe trial extension failed for org ${row.id}`, stripeError);
      }
    }

    results.push({ org_id: row.id, action: action.kind });
  }

  return NextResponse.json({ checked: data?.length ?? 0, results });
}

export const GET = handle;
export const POST = handle;
