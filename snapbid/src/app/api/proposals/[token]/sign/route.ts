import { NextResponse, type NextRequest } from "next/server";
import { z } from "zod";
import { getPublicProposal, signProposal } from "@/lib/db/proposals";
import { createDepositCheckout, isStripeConfigured } from "@/lib/stripe";
import { appUrl } from "@/lib/env";

export const runtime = "nodejs";

const schema = z.object({ signature_name: z.string().trim().min(2).max(120) });

export async function POST(request: NextRequest, context: { params: Promise<{ token: string }> }) {
  const { token } = await context.params;

  let body: unknown;
  try {
    body = await request.json();
  } catch {
    return NextResponse.json({ error: "Invalid request." }, { status: 400 });
  }

  const parsed = schema.safeParse(body);
  if (!parsed.success) {
    return NextResponse.json({ error: "Type your full name to sign." }, { status: 400 });
  }

  const result = await signProposal(token, {
    signature_name: parsed.data.signature_name,
    ip:
      request.headers.get("x-forwarded-for")?.split(",")[0]?.trim() ??
      request.headers.get("x-real-ip"),
    userAgent: request.headers.get("user-agent"),
  });

  if (!result.ok) {
    return NextResponse.json({ error: result.reason ?? "Could not sign." }, { status: 400 });
  }

  // Signature first, money second: the job is won even if the card step is
  // abandoned.
  const data = await getPublicProposal(token);
  if (data && data.proposal.deposit_amount_cents > 0 && isStripeConfigured()) {
    try {
      const checkoutUrl = await createDepositCheckout({
        orgId: data.org.id,
        orgName: data.org.name,
        proposalId: data.proposal.id,
        proposalToken: token,
        amountCents: data.proposal.deposit_amount_cents,
        jobTitle: data.estimate.title,
        customerEmail: data.lead.email,
        connectAccountId: data.org.stripe_connect_account_id,
        successUrl: `${appUrl()}/p/${token}?deposit=paid`,
        cancelUrl: `${appUrl()}/p/${token}`,
      });
      return NextResponse.json({ ok: true, checkout_url: checkoutUrl });
    } catch {
      // Deposit checkout is best-effort — the signature already landed.
      return NextResponse.json({ ok: true });
    }
  }

  return NextResponse.json({ ok: true, guarantee_met: result.guaranteeMet ?? false });
}
