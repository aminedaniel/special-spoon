import { requireSession } from "@/lib/db/session";
import { listPriceBookItems } from "@/lib/db/price-book";
import { priceBookToCsv } from "@/lib/csv";

export async function GET() {
  const session = await requireSession();
  const items = await listPriceBookItems(session.org.id);
  const csv = priceBookToCsv(items);

  return new Response(csv, {
    headers: {
      "content-type": "text/csv; charset=utf-8",
      "content-disposition": `attachment; filename="snapbid-price-book.csv"`,
    },
  });
}
