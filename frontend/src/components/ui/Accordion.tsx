"use client";

import { useState, type ReactNode } from "react";

interface AccordionProps {
  title: string;
  children: ReactNode;
  defaultOpen?: boolean;
  count?: number;
}

export function Accordion({
  title,
  children,
  defaultOpen = false,
  count,
}: AccordionProps) {
  const [open, setOpen] = useState(defaultOpen);

  return (
    <div className="overflow-hidden rounded-2xl border border-border/80 bg-surface/90 shadow-[0_12px_30px_rgba(2,8,23,0.08)]">
      <button
        onClick={() => setOpen(!open)}
        className="flex min-h-[48px] w-full items-center justify-between bg-surface-alt/80 px-4 py-3 text-left transition-colors hover:bg-surface-hover"
      >
        <span className="text-sm font-medium">
          {title}
          {count !== undefined && (
            <span className="ml-2 text-text-muted">({count})</span>
          )}
        </span>
        <span className="text-text-muted">{open ? "−" : "+"}</span>
      </button>
      {open && <div className="border-t border-border/70 px-4 py-4">{children}</div>}
    </div>
  );
}
