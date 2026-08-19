import { guaranteeBanner, type GuaranteeState } from "@/lib/guarantee";

const TONES = {
  active: "border-brand/30 bg-brand-soft text-brand",
  success: "border-emerald-200 bg-emerald-50 text-emerald-800",
  comped: "border-amber-200 bg-amber-50 text-amber-900",
} as const;

const BARS = {
  active: "bg-brand",
  success: "bg-emerald-600",
  comped: "bg-amber-500",
} as const;

export function GuaranteeBanner({ org }: { org: GuaranteeState }) {
  const banner = guaranteeBanner(org, new Date());
  if (!banner) return null;

  const progress = banner.day ? (banner.day / banner.totalDays) * 100 : 100;

  return (
    <div className={`rounded-2xl border px-4 py-3 ${TONES[banner.tone]}`}>
      <p className="text-sm font-bold">{banner.headline}</p>
      <p className="mt-0.5 text-xs opacity-90">{banner.detail}</p>
      <div className="mt-2 h-1.5 w-full overflow-hidden rounded-full bg-white/60">
        <div
          className={`h-full rounded-full ${BARS[banner.tone]}`}
          style={{ width: `${progress}%` }}
        />
      </div>
    </div>
  );
}
