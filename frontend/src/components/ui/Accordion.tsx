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
    <div className="border border-border rounded-lg overflow-hidden">
      <button
        onClick={() => setOpen(!open)}
        className="w-full px-4 py-3 flex items-center justify-between bg-surface-alt hover:bg-surface-hover transition-colors text-left min-h-[44px]"
      >
        <span className="font-medium text-sm">
          {title}
          {count !== undefined && (
            <span className="ml-2 text-text-muted">({count})</span>
          )}
        </span>
        <span className="text-text-muted">{open ? "−" : "+"}</span>
      </button>
      {open && <div className="px-4 py-3 border-t border-border">{children}</div>}
    </div>
  );
}
