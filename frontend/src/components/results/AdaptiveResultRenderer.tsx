"use client";

import React, { useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { useRouter } from "next/navigation";
import type {
  AdaptiveResponse,
  AdaptiveSection,
  AdaptiveContentItem,
  AdaptiveReference,
  AdaptiveBLUF,
} from "@/lib/types";
import { ResultHero, ResultMetaCard, ResultSection } from "./ResultChrome";

interface Props {
  data: AdaptiveResponse;
}

// ── LOE / COR colour maps ────────────────────────────────────────────────────
const LOE_STYLE: Record<string, string> = {
  I: "bg-emerald-100 dark:bg-emerald-900 text-emerald-700 dark:text-emerald-300",
  II: "bg-blue-100 dark:bg-blue-900 text-blue-700 dark:text-blue-300",
  III: "bg-slate-100 dark:bg-slate-700 text-slate-600 dark:text-slate-300",
};

const COR_STYLE: Record<string, string> = {
  I: "bg-emerald-100 dark:bg-emerald-900 text-emerald-700 dark:text-emerald-300",
  IIa: "bg-teal-100 dark:bg-teal-900 text-teal-700 dark:text-teal-300",
  IIb: "bg-amber-100 dark:bg-amber-900 text-amber-700 dark:text-amber-300",
  "III-no-benefit":
    "bg-orange-100 dark:bg-orange-900 text-orange-700 dark:text-orange-300",
  "III-harm": "bg-red-100 dark:bg-red-900 text-red-700 dark:text-red-300",
};

function EvidenceBadge({
  loe,
  cor,
  compact = false,
}: {
  loe?: string;
  cor?: string;
  compact?: boolean;
}) {
  if (!loe && !cor) return null;
  const size = compact ? "text-[10px] px-1 py-0" : "text-xs px-1.5 py-0.5";
  return (
    <span className="inline-flex items-center gap-1 shrink-0">
      {loe && (
        <span
          className={`${size} rounded font-medium ${LOE_STYLE[loe] ?? "bg-muted text-muted-foreground"}`}
          title="Level of Evidence"
        >
          LoE&nbsp;{loe}
        </span>
      )}
      {cor && (
        <span
          className={`${size} rounded font-medium ${COR_STYLE[cor] ?? "bg-muted text-muted-foreground"}`}
          title="Class of Recommendation"
        >
          Class&nbsp;{cor}
        </span>
      )}
    </span>
  );
}

// ── Single claim row ─────────────────────────────────────────────────────────
function ClaimRow({ item }: { item: AdaptiveContentItem }) {
  return (
    <div className="flex gap-2 items-start py-1.5 border-b border-border/40 last:border-0">
      <div className="flex-1 text-sm text-foreground prose prose-sm dark:prose-invert max-w-none prose-p:my-1 prose-ul:my-1 prose-li:my-0.5 prose-table:text-xs">
        <ReactMarkdown remarkPlugins={[remarkGfm]}>{item.text}</ReactMarkdown>
      </div>
      <div className="flex flex-col items-end gap-1 shrink-0 pt-0.5">
        <EvidenceBadge loe={item.loe ?? undefined} cor={item.cor ?? undefined} compact />
        {item.source && (
          <span className="text-[10px] text-muted-foreground max-w-[120px] text-right leading-tight">
            {item.source}
          </span>
        )}
      </div>
    </div>
  );
}

// ── Section card ─────────────────────────────────────────────────────────────
function SectionCard({ section }: { section: AdaptiveSection }) {
  const hasItems =
    Array.isArray(section.content_items) && section.content_items.length > 0;

  return (
    <ResultSection title={section.title} className="mb-4">
      <div className="mb-4 flex items-center justify-between gap-2 border-b border-border/70 pb-3">
        <EvidenceBadge loe={section.loe ?? undefined} cor={section.cor ?? undefined} />
      </div>

      {hasItems ? (
        <div className="divide-y divide-border/30">
          {section.content_items.map((item, i) => (
            <ClaimRow key={i} item={item} />
          ))}
        </div>
      ) : section.content ? (
        Array.isArray(section.content) ? (
          <ul className="list-disc list-inside space-y-1 text-sm text-muted-foreground">
            {(section.content as string[]).map((item, i) => (
              <li key={i}>{item}</li>
            ))}
          </ul>
        ) : (
          <div className="prose prose-sm max-w-none text-sm text-foreground dark:prose-invert prose-p:my-1 prose-ul:my-1 prose-table:text-xs">
            <ReactMarkdown remarkPlugins={[remarkGfm]}>
              {String(section.content)}
            </ReactMarkdown>
          </div>
        )
      ) : null}
    </ResultSection>
  );
}

function ReferenceRow({ ref: r, index }: { ref: AdaptiveReference; index: number }) {
  const label = r.title || r.source || `Reference ${index + 1}`;
  const meta = [r.source, r.year].filter(Boolean).join(", ");
  return (
    <li className="flex items-start gap-1.5 text-xs">
      <span className="text-muted-foreground shrink-0 mt-0.5">{index + 1}.</span>
      <span>
        {r.url ? (
          <a
            href={r.url}
            target="_blank"
            rel="noopener noreferrer"
            className="text-blue-600 dark:text-blue-400 hover:underline"
          >
            {label}
          </a>
        ) : r.pmid ? (
          <a
            href={`https://pubmed.ncbi.nlm.nih.gov/${r.pmid}/`}
            target="_blank"
            rel="noopener noreferrer"
            className="text-blue-600 dark:text-blue-400 hover:underline"
          >
            {label}
          </a>
        ) : (
          <span className="text-foreground">{label}</span>
        )}
        {meta && (
          <span className="text-muted-foreground ml-1">({meta})</span>
        )}
      </span>
    </li>
  );
}

// ── LOE/COR glossary ──────────────────────────────────────────────────────────
function EvidenceGlossary() {
  const [open, setOpen] = useState(false);
  return (
    <div className="border border-border rounded-lg overflow-hidden text-xs">
      <button
        onClick={() => setOpen((v) => !v)}
        className="w-full flex items-center justify-between px-4 py-2.5 bg-muted/40 hover:bg-muted/60 transition-colors text-left"
      >
        <span className="font-medium text-foreground">
          Evidence Grading Explained (ACC/AHA Framework)
        </span>
        <span className="text-muted-foreground">{open ? "▲" : "▼"}</span>
      </button>
      {open && (
        <div className="px-4 py-3 space-y-3">
          <div>
            <p className="font-medium text-foreground mb-1">
              Level of Evidence (LoE)
            </p>
            <table className="w-full border-collapse">
              <tbody>
                {[
                  ["I", "RCTs, meta-analyses of RCTs — highest quality evidence"],
                  ["II", "Well-designed observational studies (cohort, case-control)"],
                  ["III", "Expert opinion, case reports, consensus — lowest quality"],
                ].map(([lv, desc]) => (
                  <tr key={lv} className="border-b border-border/30 last:border-0">
                    <td className="py-1 pr-3 font-medium text-foreground w-10">
                      LoE {lv}
                    </td>
                    <td className="py-1 text-muted-foreground">{desc}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <div>
            <p className="font-medium text-foreground mb-1">
              Class of Recommendation (COR)
            </p>
            <table className="w-full border-collapse">
              <tbody>
                {[
                  ["I", "Strong benefit — should be performed"],
                  ["IIa", "Moderate benefit — reasonable to perform"],
                  ["IIb", "Weak benefit — may be considered"],
                  ["III-no-benefit", "No benefit — not recommended"],
                  ["III-harm", "Harmful — contraindicated"],
                ].map(([cls, desc]) => (
                  <tr key={cls} className="border-b border-border/30 last:border-0">
                    <td className="py-1 pr-3 font-medium text-foreground w-32 whitespace-nowrap">
                      Class {cls}
                    </td>
                    <td className="py-1 text-muted-foreground">{desc}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  );
}

// ── Main renderer ────────────────────────────────────────────────────────────
export function AdaptiveResultRenderer({ data }: Props) {
  const router = useRouter();

  return (
    <div className="space-y-5">
      <ResultHero
        eyebrow="Adaptive Answer"
        title={data.bluf.headline}
        subtitle={data.response_focus}
        stats={[
          { label: "sections", value: data.sections.length },
          { label: "references", value: data.references.length },
          { label: "depth", value: data.depth },
        ]}
        directAnswer={data.bluf.body ?? data.bluf.headline}
        context={
          <>
            {data.bluf.key_points.length > 0 && (
              <ul className="list-disc space-y-1 pl-5">
                {data.bluf.key_points.map((point, i) => (
                  <li key={i}>{point}</li>
                ))}
              </ul>
            )}
            {data.bluf.caveats.length > 0 && (
              <div className="mt-3 flex flex-wrap gap-2">
                {data.bluf.caveats.map((caveat, i) => (
                  <span
                    key={i}
                    className="rounded-full border border-rose-500/20 bg-rose-500/10 px-3 py-1.5 text-xs text-rose-200"
                  >
                    {caveat}
                  </span>
                ))}
              </div>
            )}
          </>
        }
      />

      {data.sections.map((section, i) => (
        <SectionCard key={i} section={section} />
      ))}

      {data.references.length > 0 && (
        <ResultSection title="References" eyebrow="Sources">
          <ul className="space-y-2">
            {data.references.map((ref, i) => (
              <ReferenceRow key={i} ref={ref} index={i} />
            ))}
          </ul>
        </ResultSection>
      )}

      {data.related_topics && data.related_topics.length > 0 && (
        <ResultSection title="Explore Related Topics" eyebrow="Follow-up queries">
          <div className="flex flex-wrap gap-2">
            {data.related_topics.map((topic, i) => (
              <button
                key={i}
                onClick={() =>
                  router.push(`/query?q=${encodeURIComponent(topic)}`)
                }
                className="rounded-full border border-border bg-background px-3 py-1.5 text-xs text-foreground transition-colors hover:bg-muted"
              >
                {topic}
              </button>
            ))}
          </div>
        </ResultSection>
      )}

      <EvidenceGlossary />
    </div>
  );
}
