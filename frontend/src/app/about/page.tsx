"use client";

import { ExternalLink } from "lucide-react";
import { QueryFlowDiagram } from "@/components/about/QueryFlowDiagram";

const HALLUCINATION_PREVENTION = [
  {
    label: "Evidence grounding",
    desc: "The LLM is instructed to anchor claims to fetched article text and cite each claim. If retrieval fails or times out, the system allows guarded fallback generation and surfaces warnings so unsupported claims are treated cautiously.",
  },
  {
    label: "Fail-closed design",
    desc: "If retrieved evidence is insufficient, the pipeline stops and returns a DegradedResponse instead of proceeding to generation. A clear 'not enough data' message is safer than a confident wrong answer.",
  },
  {
    label: "Citation validation",
    desc: "Every section cites specific source indices. The formatter verifies citations exist in the fetched data. Unsupported claims cannot earn a high LOE rating.",
  },
  {
    label: "LOE/COR consistency enforcement",
    desc: "Levels of evidence are assigned by source type at a structural level — not inferred by the model. An expert opinion cannot be upgraded to LOE I regardless of how the LLM phrases the claim.",
  },
  {
    label: "Query-focused retrieval",
    desc: "PubMed is searched using the standardized query term, not freeform prose. MeSH-matched results are more likely to be on-topic than semantic similarity alone. Date-sorted results prioritize recent guidelines over older studies.",
  },
];

const DATA_SOURCES = [
  { name: "FDA OpenFDA", url: "https://open.fda.gov/", desc: "Drug labels, adverse events, recalls" },
  { name: "PubMed / NCBI", url: "https://pubmed.ncbi.nlm.nih.gov/", desc: "Guidelines, RCTs, systematic reviews" },
  { name: "ClinicalTrials.gov", url: "https://clinicaltrials.gov/", desc: "Registered & completed trial summaries" },
  { name: "PMC Open Access", url: "https://www.ncbi.nlm.nih.gov/pmc/", desc: "Full-text articles & StatPearls monographs" },
  { name: "Unpaywall", url: "https://unpaywall.org/", desc: "Free legal PDFs for open-access articles" },
  { name: "RxNorm", url: "https://www.nlm.nih.gov/research/umls/rxnorm/", desc: "Drug names & interaction data" },
  { name: "ChEMBL", url: "https://www.ebi.ac.uk/chembl/", desc: "Drug mechanism & pharmacology" },
  { name: "DailyMed", url: "https://dailymed.nlm.nih.gov/dailymed/", desc: "FDA-approved prescribing information" },
  { name: "Semantic Scholar", url: "https://www.semanticscholar.org/", desc: "Paper metadata & citation counts" },
  { name: "MedlinePlus", url: "https://medlineplus.gov/", desc: "Drug & disease patient-facing summaries" },
  { name: "NICE", url: "https://www.nice.org.uk/", desc: "UK clinical practice guidelines" },
];

const LESSONS = [
  {
    title: "Quantity vs. quality is a harder trade-off than it looks",
    desc: "Fetching more sources always sounds better on paper. In practice, a noisy PubMed result set with 20 weakly-relevant abstracts produces worse LLM output than 5 high-quality ones. We built evidence scoring precisely because raw retrieval count is a bad proxy for answer quality. More data causes the model to hedge, bury the key point, or invent a consensus that doesn't exist in the sources.",
  },
  {
    title: "Medical research is behind paywalls — and that matters",
    desc: "Most impactful RCTs and meta-analyses are published in journals that don't offer open access. PubMed gives titles and abstracts; the actual trial data is paywalled. Unpaywall helps for open-access articles, but institutional guideline PDFs — NICE, ACC/AHA, ESC — are not consistently machine-readable. This means a query about a rare disease or a recent trial update will frequently hit the evidence quality floor and return a DegradedResponse, not because the answer doesn't exist, but because it exists behind a paywall.",
  },
  {
    title: "LLMs are good editors, not good researchers",
    desc: "The pipeline treats the LLM purely as a formatter. Give it structured evidence and a schema to fill, and it produces clean, graded, citable output. Ask it to 'find information about X' without grounded sources and it will confabulate confidently. The fail-closed evidence gate exists because we learned early that the model will fill gaps with plausible-sounding but unsourced content if you let it.",
  },
  {
    title: "Not every question is a clinical question",
    desc: "Early on the pipeline would dutifully search PubMed for anything typed into it, including questions with no drug, disease, symptom, or procedure in them. That wastes retrieval and invites confidently-worded answers to questions the literature can't speak to. A scope guard now runs first: if no medical entities are extracted, the app declines honestly and never searches — a plain 'this isn't a clinical question' is safer and more useful than a padded non-answer.",
  },
  {
    title: "A feature can be live and still do nothing",
    desc: "We shipped a new retrieval fallback meant to rescue thin result sets — code merged, unit tests green, feature 'live'. It also did nothing. It sat behind an early return with such a low trigger bar that the escalation path it guarded almost never ran on the queries it was built for. The helper worked perfectly in isolation; the feature never fired in practice. The lesson: test that a feature actually triggers on its target case, not just that its internals return the right value when you call them directly.",
  },
  {
    title: "One run can lie; three runs tell the truth",
    desc: "Live PubMed does not return identical results run to run — ranking and availability shift with load. A single before/after comparison once showed a dramatic 'rescue': the new path looked like it doubled the evidence found. Re-running it, the effect was network noise, not the change. Taking the median of three runs collapsed the improvement to roughly nothing. The lesson: any metric measured against a noisy external system has to be sampled more than once before a delta is trustworthy.",
  },
  {
    title: "The right amount of evidence is a dial, not a maximum",
    desc: "It is tempting to treat retrieval as 'more is better' and keep widening the net. We raised a relevance threshold to pull in more articles and answer quality got worse, not better — the extra results were mostly off-topic and dragged the model toward hedging and false consensus. A tighter setting produced cleaner, more decisive answers. The lesson: retrieval breadth is a precision/recall trade-off to tune for the task, not a number to maximise.",
  },
  {
    title: "A size budget is not a count cap",
    desc: "One clinical search returned over 4,000 citations and crashed the response. The citation list was built from every fetched article with no count limit, and a broad query had pulled in thousands of unique papers (PubMed + Semantic Scholar + textbooks). The internal cap only measured characters, so title-only entries slipped through uncounted. The fix caps the list by count — every source the answer actually cites is kept, and the retrieved-but-uncited extras are limited. The lesson: bound what the user sees by count, not just by size.",
  },
  {
    title: "Relevance needs a floor, not just a ranking",
    desc: "Asked 'does paracetamol cause fever', the app once surfaced an unrelated post-operative arthroplasty fever guideline — it matched the word 'fever' and scored well on study quality, and nothing dropped it, because ranking only reorders. The fix adds a relevance floor that drops articles which never mention the drug, plus adverse-effect query framing so a causation question retrieves 'drug-induced' evidence rather than 'drug used to treat' evidence. Chosen by testing every combination and measuring off-topic rate: together they cut off-topic results sharply and kept more of the right ones.",
  },
];

const API_SOURCES = [
  {
    name: "Cerebras (GPT-OSS 120B)",
    desc: "Default AI provider — powers evidence formatting, query classification, and section generation.",
    url: "https://cloud.cerebras.ai",
    label: "Get API key",
    note: "Default",
  },
  {
    name: "Anthropic (Claude)",
    desc: "Alternative AI provider for users who prefer Claude. Required for Waves (medical image analysis via Claude vision).",
    url: "https://console.anthropic.com/",
    label: "Get API key",
    note: "Optional · Required for Waves",
  },
];

export default function AboutPage() {
  return (
    <div style={{ maxWidth: 720, margin: "0 auto", padding: "2.5rem 1.25rem 4rem", display: "flex", flexDirection: "column", gap: "3rem" }}>

      {/* Header */}
      <div>
        <h1 style={{ fontSize: "2rem", fontWeight: 800, color: "var(--text-primary)", margin: "0 0 0.5rem" }}>
          About Iatronix
        </h1>
        <p style={{ color: "var(--text-secondary)", fontSize: "1rem", margin: 0, lineHeight: 1.6 }}>
          Iatronix is an evidence-based clinical reference built for medical professionals.
          It searches real-time data from FDA, PubMed, NICE, and your own documents, formats them with AI, and grades every claim by the evidence behind it.
          Your API key. Your data. Your control.
        </p>
        <p style={{ color: "var(--text-muted)", fontSize: "0.875rem", margin: "0.75rem 0 0", lineHeight: 1.6 }}>
          Started in March 2026 as a personal side project by{" "}
          <a href="https://kayomarz.com" target="_blank" rel="noopener noreferrer"
             style={{ color: "var(--accent)", textDecoration: "underline" }}>
            Kayomarz
          </a>{" "}
          — built for his own clinical use and made public. More at{" "}
          <a href="https://kayomarz.com" target="_blank" rel="noopener noreferrer"
             style={{ color: "var(--accent)", textDecoration: "underline" }}>
            kayomarz.com
          </a>.
        </p>
      </div>

      {/* Search Pipeline — visual flow */}
      <section>
        <h2 style={sectionHeading}>How a search works</h2>
        <p style={{ margin: "0 0 1.5rem", fontSize: "0.875rem", color: "var(--text-secondary)" }}>
          Every question follows the same path: it is understood, branched to the right strategy,
          searched across trusted sources in parallel, merged into one evidence set, grounded to real
          citations, then written and delivered. No AI token is spent until real evidence has been
          retrieved and quality-checked.
        </p>
        <QueryFlowDiagram />
      </section>

      {/* Hallucination prevention */}
      <section>
        <h2 style={sectionHeading}>How hallucinations are prevented</h2>
        <p style={{ margin: "0 0 1rem", fontSize: "0.875rem", color: "var(--text-secondary)" }}>
          The pipeline is designed so the LLM cannot invent clinical facts. Five mechanisms enforce this:
        </p>
        <div style={{ display: "flex", flexDirection: "column", gap: "0.5rem" }}>
          {HALLUCINATION_PREVENTION.map((row) => (
            <div key={row.label} style={{ display: "flex", gap: "0.75rem", padding: "0.875rem 1rem", background: "var(--bg-surface)", border: "1px solid var(--border)", borderRadius: "var(--radius-md)" }}>
              <span style={{ fontWeight: 600, fontSize: "0.825rem", color: "var(--accent)", minWidth: 170, flexShrink: 0 }}>{row.label}</span>
              <span style={{ fontSize: "0.825rem", color: "var(--text-secondary)", lineHeight: 1.55 }}>{row.desc}</span>
            </div>
          ))}
        </div>
      </section>

      {/* Evidence grading */}
      <section>
        <h2 style={sectionHeading}>Evidence grading</h2>
        <p style={{ margin: "0 0 1rem", fontSize: "0.875rem", color: "var(--text-secondary)" }}>
          Every claim is assigned a Level of Evidence and Class of Recommendation based on its source type — not inferred from phrasing:
        </p>
        <div style={{ display: "flex", flexDirection: "column", gap: "0.5rem" }}>
          {[
            { label: "LOE I", desc: "Randomized controlled trial (RCT). The gold standard for causal evidence." },
            { label: "LOE II", desc: "Prospective cohort study, systematic review of observational data, or major guideline consensus." },
            { label: "LOE III", desc: "Case reports, cross-sectional studies, or expert opinion. Used when no higher evidence exists." },
            { label: "COR I", desc: "Strong benefit — should be done. Supported by LOE I evidence." },
            { label: "COR IIa", desc: "Moderate benefit — reasonable to do. Supported by LOE II or consistent LOE III." },
            { label: "COR IIb", desc: "Weak benefit — may consider. Conflicting or limited evidence." },
            { label: "COR III", desc: "No benefit or harmful — should not be done." },
          ].map((row) => (
            <div key={row.label} style={{ display: "flex", gap: "0.75rem", padding: "0.75rem 1rem", background: "var(--bg-surface)", border: "1px solid var(--border)", borderRadius: "var(--radius-md)" }}>
              <span style={{ fontWeight: 700, fontSize: "0.825rem", color: "var(--accent)", minWidth: 60, flexShrink: 0 }}>{row.label}</span>
              <span style={{ fontSize: "0.825rem", color: "var(--text-secondary)", lineHeight: 1.5 }}>{row.desc}</span>
            </div>
          ))}
        </div>
      </section>

      {/* Data Sources */}
      <section>
        <h2 style={sectionHeading}>Data sources</h2>
        <p style={{ margin: "0 0 1rem", fontSize: "0.875rem", color: "var(--text-secondary)" }}>
          All data is fetched in real time from these authoritative sources before any AI processing:
        </p>
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(200px, 1fr))", gap: "0.5rem" }}>
          {DATA_SOURCES.map((src) => (
            <a
              key={src.name}
              href={src.url}
              target="_blank"
              rel="noopener noreferrer"
              style={{ display: "flex", flexDirection: "column", gap: "0.2rem", padding: "0.75rem", background: "var(--bg-surface)", border: "1px solid var(--border)", borderRadius: "var(--radius-md)", textDecoration: "none", transition: "border-color var(--transition)" }}
              onMouseOver={(e) => (e.currentTarget.style.borderColor = "var(--accent)")}
              onMouseOut={(e) => (e.currentTarget.style.borderColor = "var(--border)")}
            >
              <span style={{ fontWeight: 600, fontSize: "0.875rem", color: "var(--accent)", display: "flex", alignItems: "center", gap: "0.3rem" }}>
                {src.name} <ExternalLink size={11} />
              </span>
              <span style={{ fontSize: "0.775rem", color: "var(--text-muted)" }}>{src.desc}</span>
            </a>
          ))}
        </div>
      </section>

      {/* Lessons learnt */}
      <section>
        <h2 style={sectionHeading}>Lessons learnt building this</h2>
        <div style={{ display: "flex", flexDirection: "column", gap: "0.75rem" }}>
          {LESSONS.map((l) => (
            <div key={l.title} style={{ padding: "0.875rem 1rem", background: "var(--bg-surface)", border: "1px solid var(--border)", borderRadius: "var(--radius-md)" }}>
              <p style={{ margin: "0 0 0.35rem", fontWeight: 600, fontSize: "0.9rem", color: "var(--text-primary)" }}>{l.title}</p>
              <p style={{ margin: 0, fontSize: "0.825rem", color: "var(--text-secondary)", lineHeight: 1.6 }}>{l.desc}</p>
            </div>
          ))}
        </div>
        <a
          href="/lessons"
          style={{ display: "inline-flex", alignItems: "center", gap: "0.4rem", marginTop: "0.85rem", fontSize: "0.875rem", fontWeight: 600, color: "var(--primary)" }}
        >
          Read the full Engineering Journal &rarr;
        </a>
      </section>

      {/* BYOK */}
      <section>
        <h2 style={sectionHeading}>BYOK — Your Key, Your Data</h2>
        <p style={{ margin: "0 0 1rem", fontSize: "0.875rem", color: "var(--text-secondary)" }}>
          All LLM calls use <strong style={{ color: "var(--text-primary)" }}>your own API key</strong>. Nothing is sent to Iatronix servers for generation.
          Keys are encrypted at rest and in transit. Switch providers anytime from Settings.
        </p>
        <div style={{ display: "flex", flexDirection: "column", gap: "0.625rem" }}>
          {API_SOURCES.map((src) => (
            <div key={src.name} style={{ padding: "0.875rem 1rem", background: "var(--bg-surface)", border: "1px solid var(--border)", borderRadius: "var(--radius-md)" }}>
              <div style={{ display: "flex", alignItems: "flex-start", justifyContent: "space-between", gap: "1rem", flexWrap: "wrap" }}>
                <div style={{ flex: 1 }}>
                  <p style={{ margin: "0 0 0.2rem", fontWeight: 600, fontSize: "0.875rem", color: "var(--text-primary)" }}>
                    {src.name}
                    <span style={{ marginLeft: "0.5rem", fontSize: "0.75rem", color: "var(--text-muted)", fontWeight: 400 }}>{src.note}</span>
                  </p>
                  <p style={{ margin: 0, fontSize: "0.8rem", color: "var(--text-secondary)", lineHeight: 1.5 }}>{src.desc}</p>
                </div>
                <a
                  href={src.url}
                  target="_blank"
                  rel="noopener noreferrer"
                  style={{ display: "inline-flex", alignItems: "center", gap: "0.3rem", padding: "6px 12px", background: "var(--bg-elevated)", border: "1px solid var(--border)", borderRadius: "var(--radius-md)", fontSize: "0.8rem", color: "var(--accent)", fontWeight: 500, textDecoration: "none", whiteSpace: "nowrap", flexShrink: 0, transition: "background var(--transition)" }}
                  onMouseOver={(e) => (e.currentTarget.style.background = "var(--bg-hover)")}
                  onMouseOut={(e) => (e.currentTarget.style.background = "var(--bg-elevated)")}
                >
                  {src.label}
                  <ExternalLink size={12} />
                </a>
              </div>
            </div>
          ))}
        </div>
      </section>

    </div>
  );
}

const sectionHeading: React.CSSProperties = {
  fontSize: "1.1rem", fontWeight: 700,
  color: "var(--text-primary)", margin: "0 0 0.875rem",
};
