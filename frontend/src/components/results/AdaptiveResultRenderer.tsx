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
  InlineCitation,
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
// Evidence colours map to theme tokens (Lancet: olive / clay / rose), so they track light+dark.
const LOE_CLR: Record<string, string> = {
  I: "var(--success)",
  II: "var(--warning)",
  III: "var(--text-muted)",
};

const COR_CLR: Record<string, string> = {
  I: "var(--success)",
  IIa: "var(--accent)",
  IIb: "var(--warning)",
  "III-no-benefit": "var(--warning)",
  "III-harm": "var(--danger)",
};

function badgeStyle(color: string) {
  // color-mix so a CSS var() (token) can carry its own tinted bg/border — no hex concatenation.
  return {
    backgroundColor: `color-mix(in srgb, ${color} 15%, transparent)`,
    border: `1px solid color-mix(in srgb, ${color} 36%, transparent)`,
    color,
    fontWeight: 600,
    letterSpacing: "0.01em",
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
          style={badgeStyle(LOE_CLR[loe] ?? "var(--text-muted)")}
          title="Level of Evidence"
        >
          LoE&nbsp;{loe}
        </span>
      )}
      {cor && (
        <span
          className={cls}
          style={badgeStyle(COR_CLR[cor] ?? "var(--text-muted)")}
          title="Class of Recommendation"
        >
          Class&nbsp;{cor}
        </span>
      )}
    </span>
  );
}

// ── Soft markdown normalizer (safety net when LLM ignores formatting rules) ──
function normalizeMd(text: string, preserveProse = false): string {
  if (!text) return text;
  // Convert * bullets to - bullets
  let out = text.replace(/^\* /gm, "- ");
  // Single newlines between non-bullet lines → double newline (paragraph break)
  out = out.replace(/([^\n])\n([^\n\-*#>])/g, "$1\n\n$2");
  // If text is wall-of-prose (many sentences, no bullets/headings), convert to bullets.
  //
  // `preserveProse` switches this OFF. The shredder was written when a long paragraph
  // meant an undifferentiated wall of text, but it fires on ANY paragraph over four
  // sentences and mechanically splits connected clinical reasoning into one-line bullets
  // — client-side, so no backend prompt can beat it. It is a third force (with the
  // static FORMATTING_RULES and the one-source-per-item schema) working against answers
  // that read like a specialist wrote them.
  //
  // Gated on the claim carrying resolved inline citations, which happens only when the
  // backend INLINE_CITATIONS_ENABLED flag is on. Flag off ⇒ no citations ⇒ byte-identical
  // legacy behaviour, with no frontend flag plumbing needed.
  const sentenceCount = (out.match(/\. /g) || []).length;
  const hasBullets = /\n[-*1]/.test(out);
  const hasHeadings = /\n#+/.test(out);
  if (!preserveProse && sentenceCount > 4 && !hasBullets && !hasHeadings) {
    out = out.replace(/([^.!?]+[.!?])\s+/g, "- $1\n");
  }
  return out;
}

// ── Inline citation markers ──────────────────────────────────────────────────
// The backend leaves each resolved citation in the text as a canonical "[REF_3]" and
// ships the resolved article in item.citations. Rewrite those markers into ordinary
// markdown links with a recognisable `cite:N` label, so they flow through ReactMarkdown
// (and its existing link handling) instead of needing a custom AST walk. The `a`
// component below detects the label and renders a superscript.
//
// Any "[REF_N]" without a matching entry in item.citations is dropped rather than shown:
// the backend already strips forged tokens, and this is the same posture at the edge.
function linkifyCitations(text: string, citations: InlineCitation[]): string {
  if (!text) return text;
  const byToken = new Map(citations.map(c => [c.token.toUpperCase(), c]));
  let dropped = false;
  const out = text.replace(/\[\s*REF[\s_]?(\d+)\s*\]/gi, (_m, num: string) => {
    const c = byToken.get(`[REF_${num}]`);
    if (!c) { dropped = true; return ""; }
    const href = safeHttpUrl(c.url) ?? getSourceFallbackUrl(c.source, c.pmid) ?? "";
    const title = (c.title ?? "").replace(/"/g, "'");
    // `<>` is the explicit CommonMark empty-destination form. Writing `( "Title")` instead
    // parses the TITLE as the destination (verified against remark-parse), which would put
    // the article title into the href.
    const dest = href || "<>";
    return `[cite:${c.index}](${dest} "${title}")`;
  });
  // Tidy the gap a dropped marker leaves ("source ." → "source."). Mirrors
  // _tidy_stripped_text in rag_pipeline.py, and is equally conservative about
  // line-leading whitespace so markdown indentation is never disturbed.
  return dropped ? out.replace(/[ \t]+([.,;:!?])/g, "$1") : out;
}

const CITE_LABEL = /^cite:(\d+)$/;

function CitationSup({ index, href, title }: { index: number; href: string; title?: string }) {
  const label = title ? `${index}. ${title}` : `Source ${index}`;
  const cls =
    "text-[10px] align-super leading-none px-[3px] py-[1px] ml-[1px] rounded " +
    "bg-primary/10 text-primary font-medium no-underline";
  // Re-check the destination after the markdown round-trip rather than trusting it — same
  // posture as every other href in this file. Anything not http(s) renders unlinked.
  const safe = safeHttpUrl(href);
  return safe ? (
    <a href={safe} target="_blank" rel="noopener noreferrer" title={label} className={`${cls} hover:bg-primary/20`}>
      {index}
    </a>
  ) : (
    <span title={label} className={cls}>{index}</span>
  );
}

// ── ReactMarkdown components — apply direct Tailwind utilities so bullets and
//    formatting work without @tailwindcss/typography (Tailwind v4 preflight resets
//    ul/ol list-style to none; this re-applies it at the element level).
const mdComponents: React.ComponentProps<typeof ReactMarkdown>["components"] = {
  ul: ({ children }) => <ul className="list-disc pl-5 my-2 space-y-1">{children}</ul>,
  ol: ({ children }) => <ol className="list-decimal pl-5 my-2 space-y-1">{children}</ol>,
  li: ({ children }) => <li className="leading-relaxed pl-1">{children}</li>,
  p:  ({ children }) => <p className="my-2 leading-relaxed">{children}</p>,
  strong: ({ children }) => <strong className="font-semibold">{children}</strong>,
  em: ({ children }) => <em className="italic">{children}</em>,
  h1: ({ children }) => <h1 className="text-base font-semibold mt-4 mb-1">{children}</h1>,
  h2: ({ children }) => <h2 className="text-sm font-semibold mt-3 mb-1">{children}</h2>,
  h3: ({ children }) => <h3 className="text-sm font-medium mt-3 mb-1">{children}</h3>,
  blockquote: ({ children }) => (
    <blockquote className="border-l-4 border-border pl-3 italic my-2 opacity-80">{children}</blockquote>
  ),
  code: ({ children }) => (
    <code className="bg-black/10 dark:bg-white/10 rounded px-1 text-xs font-mono">{children}</code>
  ),
  a: ({ href, children }) => (
    <a href={href} target="_blank" rel="noopener noreferrer" className="text-primary hover:underline">{children}</a>
  ),
  table: ({ children }) => <table className="w-full text-xs border-collapse my-2">{children}</table>,
  th: ({ children }) => <th className="border border-border px-2 py-1 font-semibold text-left">{children}</th>,
  td: ({ children }) => <td className="border border-border px-2 py-1">{children}</td>,
};

// ── URL safety ───────────────────────────────────────────────────────────────
// Model/retrieved content can carry attacker-influenced URLs. React does not
// sanitize href/src, so a `javascript:`/`data:` URL would execute on click.
// Allow only http(s) links; drop everything else.
function safeHttpUrl(u: string | null | undefined): string | null {
  if (!u) return null;
  const t = u.trim();
  return /^https?:\/\//i.test(t) ? t : null;
}

// ── Source-aware fallback URL helper (article-level only — no homepages) ──────
function getSourceFallbackUrl(_source: string | undefined, pmid: string | undefined): string | null {
  if (pmid && /^\d+$/.test(pmid)) return `https://pubmed.ncbi.nlm.nih.gov/${pmid}/`;
  return null;
}

// ── Single claim row ─────────────────────────────────────────────────────────
function ClaimRow({ item, fetchSources }: { item: AdaptiveContentItem; fetchSources?: string[] }) {
  const sourceHref = safeHttpUrl(item.url) ?? getSourceFallbackUrl(item.source, item.pmid);

  const displaySource = item.source?.replace(/^\[SOURCE:\s*/i, "").replace(/\]$/, "") ?? null;

  // Per-claim inline citations (backend INLINE_CITATIONS_ENABLED). When absent, everything
  // below collapses to the previous single-chip behaviour.
  const citations = item.citations ?? [];
  const hasInline = citations.length > 0;
  const bodyMd = hasInline
    ? linkifyCitations(normalizeMd(item.text, true), citations)
    : normalizeMd(item.text);

  // A per-item components map so the `a` renderer can see this claim's citations. Only
  // built when needed, so the shared module-level map stays the fast path.
  const components = React.useMemo(() => {
    if (!hasInline) return mdComponents;
    return {
      ...mdComponents,
      a: ({ href, title, children }: { href?: string; title?: string; children?: React.ReactNode }) => {
        const label = React.Children.toArray(children).join("");
        const m = CITE_LABEL.exec(label);
        if (m) return <CitationSup index={Number(m[1])} href={href ?? ""} title={title} />;
        return (
          <a href={href} target="_blank" rel="noopener noreferrer" className="text-primary hover:underline">
            {children}
          </a>
        );
      },
    };
  }, [hasInline]);

  // Extra sources behind a multi-source claim. _resolve_ref_tokens has populated this
  // since Citation Hardening v3 and the schema has carried it since the citation-integrity
  // fix, but nothing ever rendered it — so a claim citing two articles displayed one.
  const extraSources = item.additional_sources ?? [];

  const badgeAndSource = (
    <>
      <EvidenceBadge loe={item.loe ?? undefined} cor={item.cor ?? undefined} compact />
      {/* Source: always show something so user knows data origin */}
      {displaySource ? (
        sourceHref ? (
          <a href={sourceHref} target="_blank" rel="noopener noreferrer"
             className="text-[10px] text-primary hover:underline max-w-[120px] text-right leading-tight">
            {displaySource}
          </a>
        ) : (
          <span className="text-[10px] text-muted-foreground max-w-[120px] text-right leading-tight">
            {displaySource}
          </span>
        )
      ) : (
        <span className="text-[10px] text-warning max-w-[120px] text-right leading-tight italic" title="Not backed by a fetched article — based on training knowledge">
          Unverified
        </span>
      )}
      {extraSources.length > 0 && (
        <span className="text-[10px] text-muted-foreground text-right leading-tight"
              title={extraSources.map(s => s.title ?? s.source ?? "").filter(Boolean).join(" · ")}>
          +{extraSources.length} more
        </span>
      )}
    </>
  );

  return (
    <div className="py-3 border-b border-border/40 last:border-0">
      <div className="flex gap-2 items-start">
        <div className="flex-1 text-sm" style={{ color: "var(--text-primary)" }}>
          <ReactMarkdown remarkPlugins={[remarkGfm]} components={components}>{bodyMd}</ReactMarkdown>
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
          <div style={{ width: `${(counts.I / total) * 100}%`, background: "var(--success)" }} />
        )}
        {counts.II > 0 && (
          <div style={{ width: `${(counts.II / total) * 100}%`, background: "var(--warning)" }} />
        )}
        {counts.III > 0 && (
          <div style={{ width: `${(counts.III / total) * 100}%`, background: "var(--text-muted)" }} />
        )}
      </div>
      <div className="flex gap-3 shrink-0 font-mono text-[10px]">
        {counts.I > 0 && <span style={{ color: "var(--success)" }}>{counts.I} High</span>}
        {counts.II > 0 && <span style={{ color: "var(--warning)" }}>{counts.II} Mod</span>}
        {counts.III > 0 && <span style={{ color: "var(--text-muted)" }}>{counts.III} Low</span>}
      </div>
    </div>
  );
}

// ── Section semantic colour (A×B hybrid) ────────────────────────────────────
// Maps a section title → { colour token, category tag } by keyword. Unknown titles
// fall back to neutral (returns null → ResultSection renders its default style).
function sectionMeta(title: string): { color: string; tag: string } | null {
  const t = (title || "").toLowerCase();
  const m = (color: string, tag: string) => ({ color: `var(${color})`, tag });
  if (/contraindicat/.test(t)) return m("--sec-contra", "Do not use");
  if (/interaction/.test(t)) return m("--sec-inter", "Watch with");
  if (/(side.?effect|adverse|toxicit|warning|complication|precaution|risk)/.test(t)) return m("--sec-adv", "Caution");
  if (/(dosing|dosage|administ|regimen)/.test(t)) return m("--sec-dose", "How to give");
  if (/(mechanism|pharmacodynam|pharmacolog)/.test(t)) return m("--sec-mech", "Pharmacology");
  if (/(pharmacokinet|special.?population)/.test(t)) return m("--sec-slate", "Detail");
  if (/monitor/.test(t)) return m("--sec-monitor", "Follow-up");
  if (/(technique|procedure|step|surgical|approach)/.test(t)) return m("--sec-proc", "Technique");
  if (/(symptom|presentation|diagnos|sign|staging|pathophys|feature)/.test(t)) return m("--sec-dx", "Recognise");
  if (/(indication|efficacy|benefit|overview|management|treatment|first.?line|therapy)/.test(t)) return m("--sec-ind", "Use it for");
  return null;
}

// ── Section card ─────────────────────────────────────────────────────────────
function SectionCard({ section, index, fetchSources }: { section: AdaptiveSection; index: number; fetchSources?: string[] }) {
  const hasItems =
    Array.isArray(section.content_items) && section.content_items.length > 0;
  const meta = sectionMeta(section.title);

  return (
    <ResultSection title={section.title} id={`sec-${index}`} className="mb-4" accent={meta?.color} tag={meta?.tag}>
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
          <div className="text-sm" style={{ color: "var(--text-primary)" }}>
            <ReactMarkdown remarkPlugins={[remarkGfm]} components={mdComponents}>
              {normalizeMd(String(section.content))}
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
  const fallbackUrl = getSourceFallbackUrl(r.source, r.pmid);
  return (
    <li className="flex items-start gap-1.5 text-xs">
      <span className="text-muted-foreground shrink-0 mt-0.5">{index + 1}.</span>
      <span>
        {safeHttpUrl(r.url) ? (
          <a
            href={safeHttpUrl(r.url)!}
            target="_blank"
            rel="noopener noreferrer"
            className="text-primary dark:text-primary hover:underline"
          >
            {label}
          </a>
        ) : fallbackUrl ? (
          <a
            href={fallbackUrl}
            target="_blank"
            rel="noopener noreferrer"
            className="text-primary dark:text-primary hover:underline"
          >
            {label}
          </a>
        ) : (
          <span className="text-muted-foreground">
            {label}
          </span>
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
              src={safeHttpUrl(img.url) ?? ""}
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
function ComparativeLayout({
  sections,
  fetchSources,
  tables,
}: {
  sections: AdaptiveSection[];
  fetchSources?: string[];
  tables?: Array<{ title: string; headers: string[]; rows: string[][] }>;
}) {
  const filtered = sections.filter(s => (s.content_items?.length ?? 0) > 0 || s.content);
  const titleLower = new Map(filtered.map(s => [s.title.toLowerCase(), s]));

  // Group sections by role
  const profileSections = filtered.filter(s => {
    const t = s.title.toLowerCase();
    return !t.includes("comparison") && !t.includes("interaction") && !t.includes("preference") &&
           !t.includes("evidence") && !t.includes("summary");
  });

  const comparisonSections = filtered.filter(s => {
    const t = s.title.toLowerCase();
    return t.includes("comparison") || t.includes("interaction");
  });

  const guidanceSections = filtered.filter(s => {
    const t = s.title.toLowerCase();
    return t.includes("evidence") || t.includes("preference") || t.includes("positioning");
  });

  return (
    <>
      {/* Drug/Entity Profiles */}
      {profileSections.length > 0 && (
        <div className="space-y-4">
          {profileSections.map((section, i) => (
            <SectionCard key={i} section={section} index={i} fetchSources={fetchSources} />
          ))}
        </div>
      )}

      {/* Comparison Zone */}
      {(comparisonSections.length > 0 || (tables && tables.length > 0)) && (
        <div className="space-y-4">
          <TableRenderer tables={tables} />
          {comparisonSections.map((section, i) => (
            <SectionCard key={i} section={section} index={i} fetchSources={fetchSources} />
          ))}
        </div>
      )}

      {/* Guidance Zone */}
      {guidanceSections.length > 0 && (
        <div className="space-y-4">
          {guidanceSections.map((section, i) => (
            <SectionCard key={i} section={section} index={i} fetchSources={fetchSources} />
          ))}
        </div>
      )}
    </>
  );
}

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
          { label: "sections", value: data.sections?.length ?? 0 },
          { label: "references", value: data.references?.length ?? 0 },
          { label: "depth", value: data.depth },
        ]}
        directAnswer={
          <ReactMarkdown remarkPlugins={[remarkGfm]} components={mdComponents}>
            {normalizeMd(data.bluf.body ?? data.bluf.headline)}
          </ReactMarkdown>
        }
        context={
          <>
            {(data.bluf.key_points?.length ?? 0) > 0 && (
              <ul className="list-disc space-y-1 pl-5">
                {(data.bluf.key_points ?? []).map((point, i) => (
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

      {data.query_type === "comparative" ? (
        // Comparative layout: group sections by role
        <ComparativeLayout sections={data.sections} fetchSources={fetchSources} tables={data.tables} />
      ) : (
        // Standard layout: render all sections
        data.sections
          .filter(s => (s.content_items?.length ?? 0) > 0 || s.content)
          .map((section, i) => (
            <SectionCard key={i} section={section} index={i} fetchSources={fetchSources} />
          ))
      )}

      {!hideEvidenceBar && <EvidenceQualityBar sections={data.sections} />}

      <TableRenderer tables={data.tables} />
      <FlowchartRenderer flowcharts={data.flowcharts} />
      <MedicalImageRenderer images={data.images} />

      <DataSourceBadges sources={fetchSources} />

      {data.references.length > 0 && (
        <ResultSection title="References" eyebrow="Sources" id="references">
          {(() => {
            const cited = data.references.filter((r) => r.used_inline);
            const retrieved = data.references.filter((r) => !r.used_inline);
            return (
              <>
                {cited.length > 0 && (
                  <>
                    <p className="text-[10px] uppercase tracking-wide text-muted-foreground mb-1">Cited in this answer</p>
                    <ul className="space-y-2 mb-3">
                      {cited.map((ref, i) => (
                        <ReferenceRow key={`c-${i}`} ref={ref} index={i} />
                      ))}
                    </ul>
                  </>
                )}
                {retrieved.length > 0 && (
                  <>
                    <p className="text-[10px] uppercase tracking-wide text-muted-foreground mb-1">Additional sources retrieved</p>
                    <ul className="space-y-2">
                      {retrieved.map((ref, i) => (
                        <ReferenceRow key={`r-${i}`} ref={ref} index={cited.length + i} />
                      ))}
                    </ul>
                  </>
                )}
                {cited.length === 0 && retrieved.length === 0 && (
                  <ul className="space-y-2">
                    {data.references.map((ref, i) => (
                      <ReferenceRow key={i} ref={ref} index={i} />
                    ))}
                  </ul>
                )}
              </>
            );
          })()}
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
