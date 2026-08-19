import { NextResponse } from "next/server";
import { getPublicProposal } from "@/lib/db/proposals";
import { generateProposalPdf } from "@/lib/pdf";

export const runtime = "nodejs";

export async function GET(_request: Request, context: { params: Promise<{ token: string }> }) {
  const { token } = await context.params;
  const data = await getPublicProposal(token);
  if (!data) return NextResponse.json({ error: "Not found" }, { status: 404 });

  const bytes = await generateProposalPdf(data);
  const filename = `${data.org.name}-${data.estimate.title}`
    .replace(/[^a-z0-9]+/gi, "-")
    .replace(/^-|-$/g, "")
    .toLowerCase();

  return new NextResponse(Buffer.from(bytes), {
    headers: {
      "content-type": "application/pdf",
      "content-disposition": `inline; filename="${filename || "proposal"}.pdf"`,
      "cache-control": "no-store",
    },
  });
}
