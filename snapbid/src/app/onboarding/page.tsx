import { redirect } from "next/navigation";
import { OnboardingForm } from "./OnboardingForm";
import { requireSession } from "@/lib/db/session";

export default async function OnboardingPage() {
  const session = await requireSession({ allowOnboarding: true });
  if (session.org.onboarding_completed_at) redirect("/dashboard");

  return (
    <main className="mx-auto w-full max-w-2xl px-5 py-8">
      <p className="text-2xl font-black tracking-tight text-brand">SnapBid</p>
      <h1 className="mt-6 text-xl font-bold text-ink">Set up your workspace</h1>
      <p className="mt-1 text-sm text-muted">
        Two minutes now, and your first proposal takes five.
      </p>
      <div className="mt-6 rounded-2xl border border-line bg-surface p-5 shadow-sm">
        <OnboardingForm
          defaults={{
            name: session.org.name,
            trade: session.org.trade,
            email: session.org.email ?? session.email,
          }}
        />
      </div>
    </main>
  );
}
