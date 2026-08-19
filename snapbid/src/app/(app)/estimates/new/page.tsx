import { requireSession } from "@/lib/db/session";
import { NewEstimateForm } from "./NewEstimateForm";
import { Card } from "@/components/ui";
import { rateToPercent } from "@/lib/money";

export default async function NewEstimatePage() {
  const session = await requireSession();
  return (
    <div className="space-y-4">
      <h1 className="text-xl font-bold text-ink">New estimate</h1>
      <Card>
        <div className="p-4">
          <NewEstimateForm defaultTaxPercent={rateToPercent(Number(session.org.default_tax_rate))} />
        </div>
      </Card>
    </div>
  );
}
