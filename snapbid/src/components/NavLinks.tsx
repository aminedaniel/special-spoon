"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

const LINKS = [
  { href: "/dashboard", label: "Dashboard" },
  { href: "/estimates", label: "Estimates" },
  { href: "/price-book", label: "Price book" },
  { href: "/settings", label: "Settings" },
];

export function NavLinks({ variant }: { variant: "top" | "bottom" }) {
  const pathname = usePathname();

  return (
    <>
      {LINKS.map((link) => {
        const active = pathname === link.href || pathname.startsWith(`${link.href}/`);
        if (variant === "bottom") {
          return (
            <Link
              key={link.href}
              href={link.href}
              className={`flex flex-1 flex-col items-center gap-0.5 py-2.5 text-xs font-semibold ${
                active ? "text-brand" : "text-muted"
              }`}
            >
              <span
                className={`h-1 w-8 rounded-full ${active ? "bg-brand" : "bg-transparent"}`}
                aria-hidden
              />
              {link.label}
            </Link>
          );
        }
        return (
          <Link
            key={link.href}
            href={link.href}
            className={`rounded-lg px-3 py-1.5 text-sm font-semibold ${
              active ? "bg-brand-soft text-brand" : "text-muted hover:text-ink"
            }`}
          >
            {link.label}
          </Link>
        );
      })}
    </>
  );
}
