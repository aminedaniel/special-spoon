import { NextResponse, type NextRequest } from "next/server";
import { declineProposal } from "@/lib/db/proposals";

export const runtime = "nodejs";

export async function POST(_request: NextRequest, context: { params: Promise<{ token: string }> }) {
  const { token } = await context.params;
  const ok = await declineProposal(token);
  if (!ok) return NextResponse.json({ error: "Could not update the proposal." }, { status: 400 });
  return NextResponse.json({ ok: true });
}
