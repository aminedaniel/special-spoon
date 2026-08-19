import { requireSession } from "@/lib/db/session";
import { listPriceBookItems } from "@/lib/db/price-book";
import { PriceBookClient } from "./PriceBookClient";

export const dynamic = "force-dynamic";

export default async function PriceBookPage() {
  const session = await requireSession();
  const items = await listPriceBookItems(session.org.id);
  return <PriceBookClient items={items} />;
}
