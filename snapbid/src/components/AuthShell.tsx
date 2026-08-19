import type { ReactNode } from "react";

export function AuthShell({
  title,
  subtitle,
  children,
}: {
  title: string;
  subtitle: string;
  children: ReactNode;
}) {
  return (
    <main className="mx-auto flex min-h-dvh w-full max-w-md flex-col justify-center px-5 py-10">
      <div className="mb-6">
        <p className="text-2xl font-black tracking-tight text-brand">SnapBid</p>
        <h1 className="mt-6 text-xl font-bold text-ink">{title}</h1>
        <p className="mt-1 text-sm text-muted">{subtitle}</p>
      </div>
      <div className="rounded-2xl border border-line bg-surface p-5 shadow-sm">{children}</div>
    </main>
  );
}
