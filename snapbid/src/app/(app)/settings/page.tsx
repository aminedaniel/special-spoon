import { requireSession } from "@/lib/db/session";
import { SettingsForm } from "./SettingsForm";
import { Card } from "@/components/ui";
import { GuaranteeBanner } from "@/components/GuaranteeBanner";
import { TRADE_LABELS } from "@/lib/types";

export const dynamic = "force-dynamic";

export default async function SettingsPage() {
  const session = await requireSession();
  const org = session.org;

  return (
    <div className="space-y-5">
      <h1 className="text-xl font-bold text-ink">Settings</h1>
      <GuaranteeBanner org={org} />

      <Card title="Plan & guarantee">
        <dl className="space-y-2 p-4 text-sm">
          <Row label="Trade" value={TRADE_LABELS[org.trade]} />
          <Row
            label="Guarantee"
            value={org.guarantee_status}
          />
          <Row
            label="Billing starts"
            value={
              org.billing_starts_at
                ? new Date(org.billing_starts_at).toLocaleDateString("en-US", {
                    month: "long",
                    day: "numeric",
                    year: "numeric",
                  })
                : "Not started"
            }
          />
          <Row label="Card on file" value={org.stripe_subscription_id ? "Yes" : "Not yet"} />
        </dl>
      </Card>

      <SettingsForm org={org} />
    </div>
  );
}

function Row({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-baseline justify-between gap-4">
      <dt className="text-muted">{label}</dt>
      <dd className="text-right font-medium capitalize text-ink">{value}</dd>
    </div>
  );
}
