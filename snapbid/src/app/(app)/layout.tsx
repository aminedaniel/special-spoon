import Link from "next/link";
import { requireSession } from "@/lib/db/session";
import { NavLinks } from "@/components/NavLinks";

export default async function AppLayout({ children }: { children: React.ReactNode }) {
  const session = await requireSession();

  return (
    <div className="min-h-dvh pb-20 md:pb-0">
      <header className="sticky top-0 z-20 border-b border-line bg-surface/95 backdrop-blur">
        <div className="mx-auto flex w-full max-w-5xl items-center justify-between gap-3 px-4 py-3">
          <Link href="/dashboard" className="flex items-center gap-2">
            <span className="text-lg font-black tracking-tight text-brand">SnapBid</span>
          </Link>
          <div className="flex items-center gap-3">
            <span className="hidden max-w-40 truncate text-sm font-medium text-muted sm:block">
              {session.org.name}
            </span>
            <form action="/auth/signout" method="post">
              <button
                type="submit"
                className="rounded-lg border border-line px-3 py-1.5 text-sm font-semibold text-muted hover:text-ink"
              >
                Sign out
              </button>
            </form>
          </div>
        </div>
        <nav className="mx-auto hidden w-full max-w-5xl gap-1 px-2 pb-2 md:flex">
          <NavLinks variant="top" />
        </nav>
      </header>

      <main className="mx-auto w-full max-w-5xl px-4 py-5">{children}</main>

      <nav className="fixed inset-x-0 bottom-0 z-20 border-t border-line bg-surface md:hidden">
        <div className="mx-auto flex w-full max-w-5xl">
          <NavLinks variant="bottom" />
        </div>
      </nav>
    </div>
  );
}
