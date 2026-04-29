"use client";

import React, { useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { useRouter } from "next/navigation";
import { Search, ChevronRight } from "lucide-react";
import type {
  AdaptiveResponse,
  AdaptiveSection,
  AdaptiveContentItem,
  AdaptiveReference,
  AdaptiveBLUF,
  AdaptiveImage,
} from "@/lib/types";
import { ResultHero, ResultMetaCard, ResultSection } from "./ResultChrome";
import { FlowchartRenderer } from "./FlowchartRenderer";
import { TableRenderer } from "./TableRenderer";

interface Props {
  data: AdaptiveResponse;
  fetchSources?: string[];
  hideEvidenceBar?: boolean;
  isFallback?: boolean;
  fallbackModel?: string | null;
}

// ── LOE / COR colour maps ────────────────────────────────────────────────────
const LOE_CLR: Record<string, string> = {
  I: "#10b981",
  II: "#3b82f6",
  III: "#64748b",
};

const COR_CLR: Record<string, string> = {
  I: "#10b981",
  IIa: "#06b6d4",
  IIb: "#f59e0b",
  "III-no-benefit": "#f97316",
  "III-harm": "#ef4444",
};

function badgeStyle(color: string) {
  return {
    backgroundColor: color + "2e",
    border: `1px solid ${color}59`,
    color,
  };
}

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
  const cls = compact
    ? "font-mono text-[10px] px-[5px] py-[1px] rounded-[4px]"
    : "font-mono text-xs px-1.5 py-0.5 rounded-[4px]";
  return (
    <span className="inline-flex items-center gap-1 shrink-0">
      {loe && (
        <span
          className={cls}
          style={badgeStyle(LOE_CLR[loe] ?? "#64748b")}
          title="Level of Evidence"
        >
          LoE&nbsp;{loe}
        </span>
      )}
      {cor && (
        <span
          className={cls}
          style={badgeStyle(COR_CLR[cor] ?? "#64748b")}
          title="Class of Recommendation"
        >
          Class&nbsp;{cor}
        </span>
      )}
    </span>
  );
}

// ── Soft markdown normalizer (safety net when LLM ignores formatting rules) ──
function normalizeMd(text: string): string {
  if (!text) return text;
  // Convert * bullets to - bullets
  let out = text.replace(/^\* /gm, "- ");
  // If text is wall-of-prose (many sentences, no bullets/headings), convert to bullets
  const sentenceCount = (out.match(/\. /g) || []).length;
  const hasBullets = /\n[-*1]/.test(out);
  const hasHeadings = /\n#+/.test(out);
  if (sentenceCount > 4 && !hasBullets && !hasHeadings) {
    out = out.replace(/([^.!?]+[.!?])\s+/g, "- $1\n");
  }
  return out;
}

// ── Single claim row ─────────────────────────────────────────────────────────
function ClaimRow({ item, fetchSources }: { item: AdaptiveContentItem; fetchSources?: string[] }) {
  const sourceHref = item.url
    ?? (item.pmid ? `https://pubmed.ncbi.nlm.nih.gov/${item.pmid}/` : null);

  const badgeAndSource = (
    <>
      <EvidenceBadge loe={item.loe ?? undefined} cor={item.cor ?? undefined} compact />
      {/* Source: always show something so user knows data origin */}
      {item.source ? (
        sourceHref ? (
          <a href={sourceHref} target="_blank" rel="noopener noreferrer"
             className="text-[10px] text-blue-400 hover:underline max-w-[120px] text-right leading-tight">
            {item.source}
          </a>
        ) : (
          <span className="text-[10px] text-muted-foreground max-w-[120px] text-right leading-tight">
            {item.source}
          </span>
        )
      ) : (
        <span className="text-[10px] text-muted-foreground/60 max-w-[120px] text-right leading-tight italic">
          {fetchSources?.[0] ?? "Medical database"}
        </span>
      )}
    </>
  );

  return (
    <div className="py-3 border-b border-border/40 last:border-0">
      <div className="flex gap-2 items-start">
        <div className="flex-1 text-sm prose prose-sm max-w-none prose-p:my-2 prose-ul:my-2 prose-ul:list-disc prose-ul:pl-5 prose-li:my-1 prose-li:leading-relaxed prose-table:text-xs prose-strong:font-bold prose-em:italic prose-headings:font-semibold prose-headings:mt-3 prose-blockquote:border-l-4 prose-blockquote:pl-3 prose-blockquote:italic" style={{ color: "var(--text-primary)" }}>
          <ReactMarkdown remarkPlugins={[remarkGfm]}>{normalizeMd(item.text)}</ReactMarkdown>
        </div>
        {/* Badge beside text on sm+ screens */}
        <div className="hidden sm:flex flex-col items-end gap-1 shrink-0 pt-0.5">
          {badgeAndSource}
        </div>
      </div>
      {/* Badge below text on mobile (< sm) */}
      <div className="flex sm:hidden items-center gap-2 mt-1.5 flex-wrap">
        {badgeAndSource}
      </div>
    </div>
  );
}

// ── Evidence quality bar ─────────────────────────────────────────────────────
function EvidenceQualityBar({ sections }: { sections: AdaptiveSection[] }) {
  const counts = { I: 0, II: 0, III: 0 };
  for (const sec of sections) {
    for (const item of sec.content_items ?? []) {
      if (item.loe === "I") counts.I++;
      else if (item.loe === "II") counts.II++;
      else if (item.loe === "III") counts.III++;
    }
  }
  const total = counts.I + counts.II + counts.III;
  if (total === 0) return null;

  return (
    <div className="flex items-center gap-3 px-4 py-2 rounded-xl border border-border/50 bg-surface/60">
      <div className="flex-1 h-[5px] rounded-full overflow-hidden flex">
        {counts.I > 0 && (
          <div style={{ width: `${(counts.I / total) * 100}%`, background: "#10b981" }} />
        )}
        {counts.II > 0 && (
          <div style={{ width: `${(counts.II / total) * 100}%`, background: "#3b82f6" }} />
        )}
        {counts.III > 0 && (
          <div style={{ width: `${(counts.III / total) * 100}%`, background: "#64748b" }} />
        )}
      </div>
      <div className="flex gap-3 shrink-0 font-mono text-[10px]">
        {counts.I > 0 && <span style={{ color: "#10b981" }}>{counts.I} High</span>}
        {counts.II > 0 && <span style={{ color: "#3b82f6" }}>{counts.II} Mod</span>}
        {counts.III > 0 && <span style={{ color: "#64748b" }}>{counts.III} Low</span>}
      </div>
    </div>
  );
}

// ── Section card ─────────────────────────────────────────────────────────────
function SectionCard({ section, index, fetchSources }: { section: AdaptiveSection; index: number; fetchSources?: string[] }) {
  const hasItems =
    Array.isArray(section.content_items) && section.content_items.length > 0;

  return (
    <ResultSection title={section.title} id={`sec-${index}`} className="mb-4">
      <div className="mb-4 flex items-center justify-between gap-2 border-b border-border/70 pb-3">
        <EvidenceBadge loe={section.loe ?? undefined} cor={section.cor ?? undefined} />
      </div>

      {hasItems ? (
        <div className="divide-y divide-border/30">
          {section.content_items.map((item, i) => (
            <ClaimRow key={i} item={item} fetchSources={fetchSources} />
          ))}
        </div>
      ) : section.content ? (
        Array.isArray(section.content) ? (
          <ul className="list-disc list-outside pl-4 space-y-3 text-sm" style={{ color: "var(--text-primary)" }}>
            {(section.content as string[]).map((item, i) => (
              <li key={i}>{item}</li>
            ))}
          </ul>
        ) : (
          <div className="prose prose-sm max-w-none text-sm prose-p:my-2 prose-ul:my-2 prose-ul:list-disc prose-ul:pl-5 prose-li:block prose-li:my-1.5 prose-table:text-xs prose-strong:font-bold prose-em:italic" style={{ color: "var(--text-primary)" }}>
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
          <a
            href={`https://pubmed.ncbi.nlm.nih.gov/?term=${encodeURIComponent(
              [r.title, r.source, r.year?.toString()].filter(Boolean).join(" ")
            )}`}
            target="_blank"
            rel="noopener noreferrer"
            className="text-blue-600 dark:text-blue-400 hover:underline"
          >
            {label}
          </a>
        )}
        {meta && (
          <span className="text-muted-foreground ml-1">({meta})</span>
        )}
      </span>
    </li>
  );
}

// ── LOE/COR glossary ──────────────────────────────────────────────────────────
// ── Data source badges ──────────────────────────────────────────────────────
function DataSourceBadges({ sources }: { sources?: string[] }) {
  if (!sources || sources.length === 0) return null;

  return (
    <ResultSection title="Data Sources" eyebrow="Fetched from">
      <div className="flex flex-wrap gap-2">
        {sources.map((source, i) => (
          <span
            key={i}
            className="rounded-full border border-border bg-surface-alt px-3 py-1 text-xs text-text-muted"
          >
            {source}
          </span>
        ))}
      </div>
    </ResultSection>
  );
}

function EvidenceGlossary() {
  const [open, setOpen] = useState(false);
  return (
    <div className="border border-border rounded-lg overflow-hidden text-xs">
      <button
        onClick={() => setOpen((v) => !v)}
        className="w-full flex items-center justify-between px-4 py-2.5 bg-muted/40 hover:bg-muted/60 transition-colors text-left"
      >
        <span className="font-medium text-foreground">
          Evidence Grading Explained
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

// ── Open-source medical illustrations ────────────────────────────────────────
function MedicalImageRenderer({ images }: { images?: AdaptiveImage[] }) {
  if (!images || images.length === 0) return null;

  return (
    <ResultSection title="Medical Illustrations" eyebrow="Open Source">
      <div className="flex flex-wrap gap-6">
        {images.map((img, i) => (
          <figure key={i} className="max-w-sm w-full">
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img
              src={img.url}
              alt={img.caption ?? "Medical illustration"}
              className="rounded-lg border border-border w-full object-contain max-h-72"
            />
            {img.caption && (
              <figcaption className="text-xs text-muted-foreground mt-1.5 leading-tight">
                {img.caption}
              </figcaption>
            )}
            {(img.license || img.source) && (
              <span className="text-[10px] text-muted-foreground">
                {[img.license, img.source].filter(Boolean).join(" · ")}
              </span>
            )}
          </figure>
        ))}
      </div>
    </ResultSection>
  );
}

// ── Main renderer ────────────────────────────────────────────────────────────
export function AdaptiveResultRenderer({ data, fetchSources, hideEvidenceBar, isFallback, fallbackModel }: Props) {
  const router = useRouter();

  return (
    <div className="space-y-5">
      {isFallback && (
        <div className="inline-flex items-center gap-1.5 rounded-full border border-amber-500/30 bg-amber-500/10 px-3 py-1 text-xs text-amber-400">
          <span className="h-1.5 w-1.5 rounded-full bg-amber-400" />
          Using backup model{fallbackModel ? ` (${fallbackModel.split("/").pop()})` : ""}
        </div>
      )}
      <ResultHero
        eyebrow="Adaptive Answer"
        title={data.bluf.headline}
        subtitle={data.response_focus}
        stats={[
          { label: "sections", value: data.sections.length },
          { label: "references", value: data.references.length },
          { label: "depth", value: data.depth },
        ]}
        directAnswer={
          <ReactMarkdown remarkPlugins={[remarkGfm]} className="prose prose-sm max-w-none prose-p:my-1 prose-ul:my-1 prose-ul:list-disc prose-ul:pl-5 prose-li:my-0.5 prose-strong:font-bold">
            {data.bluf.body ?? data.bluf.headline}
          </ReactMarkdown>
        }
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

      {data.sections
        .filter(s => (s.content_items?.length ?? 0) > 0 || s.content)
        .map((section, i) => (
          <SectionCard key={i} section={section} index={i} fetchSources={fetchSources} />
        ))}

      {!hideEvidenceBar && <EvidenceQualityBar sections={data.sections} />}

      <TableRenderer tables={data.tables} />
      <FlowchartRenderer flowcharts={data.flowcharts} />
      <MedicalImageRenderer images={data.images} />

      <DataSourceBadges sources={fetchSources} />

      {data.references.length > 0 && (
        <ResultSection title="References" eyebrow="Sources" id="references">
          <ul className="space-y-2">
            {data.references.map((ref, i) => (
              <ReferenceRow key={i} ref={ref} index={i} />
            ))}
          </ul>
        </ResultSection>
      )}

      {data.related_topics && data.related_topics.length > 0 && (
        <ResultSection title="Explore Related Queries" eyebrow="Follow-up queries">
          <div className="flex flex-col gap-0.5">
            {data.related_topics.map((topic, i) => (
              <button
                key={i}
                onClick={() => router.push(`/query?q=${encodeURIComponent(topic)}`)}
                className="w-full flex items-center gap-2.5 px-2.5 py-2 rounded-[10px] text-left hover:bg-[var(--bg-elevated)] transition-colors"
              >
                <Search size={13} className="text-[var(--accent)] shrink-0" />
                <span className="flex-1 text-[0.85rem] text-[var(--accent)] underline decoration-blue-500/35 underline-offset-[3px] leading-snug">
                  {topic}
                </span>
                <ChevronRight size={11} className="text-[var(--text-muted)] shrink-0" />
              </button>
            ))}
          </div>
        </ResultSection>
      )}

      <EvidenceGlossary />
    </div>
  );
}
