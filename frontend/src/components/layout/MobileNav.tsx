"use client";

import Link from "next/link";

export function MobileNav() {
  return (
    <nav className="md:hidden fixed bottom-0 left-0 right-0 bg-surface-alt border-t border-border flex">
      <Link
        href="/"
        className="flex-1 py-3 text-center text-sm min-h-[44px] flex items-center justify-center"
      >
        Home
      </Link>
      <Link
        href="/query"
        className="flex-1 py-3 text-center text-sm min-h-[44px] flex items-center justify-center"
      >
        Query
      </Link>
    </nav>
  );
}
