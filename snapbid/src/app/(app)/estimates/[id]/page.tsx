import { notFound } from "next/navigation";
import { requireSession } from "@/lib/db/session";
import { getEstimate } from "@/lib/db/estimates";
import { listPriceBookItems } from "@/lib/db/price-book";
import { proposalUrl } from "@/lib/db/proposals";
import { EstimateEditor } from "./EstimateEditor";

export const dynamic = "force-dynamic";

export default async function EstimatePage({ params }: { params: Promise<{ id: string }> }) {
  const session = await requireSession();
  const { id } = await params;

  const [estimate, priceBook] = await Promise.all([
    getEstimate(session.org.id, id),
    listPriceBookItems(session.org.id),
  ]);
  if (!estimate) notFound();

  return (
    <EstimateEditor
      estimate={estimate}
      org={session.org}
      priceBook={priceBook}
      proposalUrl={estimate.proposal ? proposalUrl(estimate.proposal.public_token) : null}
    />
  );
}
