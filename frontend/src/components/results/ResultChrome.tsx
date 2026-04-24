"use client";

import type { ReactNode } from "react";

interface ResultHeroProps {
  eyebrow: string;
  title: string;
  subtitle?: string | null;
  stats?: Array<{ label: string; value: string | number }>;
  directAnswer?: ReactNode;
  context?: ReactNode;
}

export function ResultHero({
  eyebrow,
  title,
  subtitle,
  stats = [],
  directAnswer,
  context,
}: ResultHeroProps) {
  return (
    <div className="relative overflow-hidden rounded-[28px] border border-border/80 bg-[linear-gradient(135deg,rgba(15,23,42,0.98),rgba(30,41,59,0.95)_55%,rgba(37,99,235,0.18))] p-5 shadow-[0_24px_70px_rgba(2,8,23,0.32)]">
      <div className="pointer-events-none absolute inset-0 bg-[radial-gradient(circle_at_top_right,rgba(96,165,250,0.2),transparent_35%),radial-gradient(circle_at_bottom_left,rgba(16,185,129,0.12),transparent_28%)]" />
      <div className="relative space-y-4">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div className="space-y-1">
            <p className="text-[11px] font-semibold uppercase tracking-[0.22em] text-sky-300/80">
              {eyebrow}
            </p>
            <h2 className="text-2xl font-semibold tracking-tight text-white sm:text-[2rem]">
              {title}
            </h2>
            {subtitle && (
              <p className="max-w-3xl text-sm leading-7 text-slate-300">
                {subtitle}
              </p>
            )}
          </div>

          {stats.length > 0 && (
            <div className="flex flex-wrap gap-2">
              {stats.map((stat) => (
                <ResultStatPill
                  key={`${stat.label}-${stat.value}`}
                  label={stat.label}
                  value={stat.value}
                />
              ))}
            </div>
          )}
        </div>

        {directAnswer && (
          <div className="rounded-2xl border border-white/10 bg-white/6 px-4 py-4 backdrop-blur-sm">
            <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-slate-300">
              Direct Answer
            </p>
            <div className="mt-2 text-sm leading-7 text-slate-50">{directAnswer}</div>
          </div>
        )}

        {context && (
          <div className="rounded-2xl border border-white/8 bg-black/10 px-4 py-3 backdrop-blur-sm">
            <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-slate-400">
              More Context
            </p>
            <div className="mt-2 text-sm leading-7 text-slate-300">{context}</div>
          </div>
        )}
      </div>
    </div>
  );
}

export function ResultSection({
  title,
  eyebrow,
  children,
  className = "",
  id,
}: {
  title: string;
  eyebrow?: string;
  children: ReactNode;
  className?: string;
  id?: string;
}) {
  return (
    <section
      id={id}
      className={`rounded-[24px] border border-border/80 bg-surface/90 p-5 shadow-[0_16px_40px_rgba(2,8,23,0.12)] backdrop-blur-sm ${className}`}
    >
      {eyebrow && (
        <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-text-muted">
          {eyebrow}
        </p>
      )}
      <h3 className="mt-1 text-lg font-semibold tracking-tight text-text">
        {title}
      </h3>
      <div className="mt-4">{children}</div>
    </section>
  );
}

export function ResultStatPill({
  label,
  value,
}: {
  label: string;
  value: string | number;
}) {
  return (
    <div className="rounded-full border border-white/10 bg-white/6 px-3 py-1.5 text-xs text-slate-300 backdrop-blur-sm">
      <span className="font-semibold text-white">{value}</span> {label}
    </div>
  );
}

export function ResultChipRow({
  label,
  items,
  tone = "default",
}: {
  label: string;
  items: string[];
  tone?: "default" | "accent";
}) {
  if (items.length === 0) return null;

  const toneClass =
    tone === "accent"
      ? "border-sky-500/20 bg-sky-500/10 text-sky-200"
      : "border-border/70 bg-background/70 text-text-secondary";

  return (
    <div className="space-y-2">
      <p className="text-xs font-medium uppercase tracking-[0.18em] text-text-muted">
        {label}
      </p>
      <div className="flex flex-wrap gap-2">
        {items.map((item) => (
          <span
            key={item}
            className={`rounded-full border px-3 py-1.5 text-xs ${toneClass}`}
          >
            {item}
          </span>
        ))}
      </div>
    </div>
  );
}

export function ResultMetaCard({
  children,
  className = "",
}: {
  children: ReactNode;
  className?: string;
}) {
  return (
    <div
      className={`rounded-2xl border border-border/70 bg-background/70 px-4 py-3 ${className}`}
    >
      {children}
    </div>
  );
}
