import { NextResponse, type NextRequest } from "next/server";
import { getPublicProposal } from "@/lib/db/proposals";
import { createDepositCheckout, isStripeConfigured } from "@/lib/stripe";
import { appUrl } from "@/lib/env";

export const runtime = "nodejs";

/** Form-posted from the proposal page, so it answers with a redirect. */
export async function POST(_request: NextRequest, context: { params: Promise<{ token: string }> }) {
  const { token } = await context.params;
  const data = await getPublicProposal(token);
  if (!data) return NextResponse.json({ error: "Proposal not found." }, { status: 404 });

  if (!isStripeConfigured() || data.proposal.deposit_amount_cents <= 0) {
    return NextResponse.redirect(`${appUrl()}/p/${token}`, { status: 303 });
  }

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

  return NextResponse.redirect(checkoutUrl, { status: 303 });
}
