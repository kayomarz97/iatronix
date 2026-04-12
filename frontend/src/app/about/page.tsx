"use client";

import { ExternalLink, Brain, Globe, FileText } from "lucide-react";

const MODES = [
  {
    icon: <Brain size={18} />,
    title: "AI Mode",
    desc: "Fetches live data from OpenFDA, PubMed, RxNorm, DailyMed and uses Claude to format it into a structured, evidence-graded response. Best for comprehensive clinical queries.",
  },
  {
    icon: <Globe size={18} />,
    title: "Web Sources Only",
    desc: "Fetches live data from the same APIs without AI formatting. Returns raw authoritative data. Faster; does not consume LLM tokens.",
  },
  {
    icon: <FileText size={18} />,
    title: "Personal PDFs",
    desc: "Searches only documents you have uploaded via semantic vector search. Answers come exclusively from your indexed PDFs — ideal for institutional guidelines.",
  },
];

const API_SOURCES = [
  {
    name: "Anthropic (Claude)",
    desc: "Powers AI-formatted responses and evidence structuring.",
    url: "https://console.anthropic.com/",
    label: "Get API key",
    note: "Required for AI Mode",
  },
  {
    name: "OpenAI (GPT)",
    desc: "Alternative LLM provider for AI-formatted responses.",
    url: "https://platform.openai.com/api-keys",
    label: "Get API key",
    note: "Optional alternative to Claude",
  },
  {
    name: "NCBI PubMed",
    desc: "Free API for clinical guidelines and systematic reviews. Key raises rate limit to 10 req/s.",
    url: "https://www.ncbi.nlm.nih.gov/account/",
    label: "Create free account",
    note: "Optional — improves search speed",
  },
  {
    name: "OpenFDA",
    desc: "US FDA drug label data, adverse events, recalls. Key raises limit to 1000 req/min.",
    url: "https://open.fda.gov/apis/authentication/",
    label: "Get free API key",
    note: "Optional — improves rate limits",
  },
];

const HOW_IT_WORKS = [
  { step: "1", title: "You type a query", desc: "Ask about a drug, disease, procedure, or evidence review in plain clinical language." },
  { step: "2", title: "Query is classified", desc: "Regex pattern scoring instantly classifies the query. For ambiguous phrasing (confidence < 85%), a lightweight Haiku call resolves the type — so any medical question routes correctly, not just pre-enumerated patterns." },
  { step: "3", title: "Data is fetched", desc: "Relevant data is pulled in parallel from OpenFDA, PubMed, PMC/StatPearls, RxNorm, DailyMed, MedlinePlus, and your uploaded PDFs — zero AI tokens at this stage." },
  { step: "4", title: "LLM structures the response", desc: "The adaptive pipeline analyses what you actually need, then formats the fetched data into evidence-graded sections (LOE I–III, Class I–IIb) with approved citations. A Bottom Line Up Front (BLUF) banner is generated at the top — scaled to data richness: headline only for simple lookups; headline + summary + action bullets + safety caveats for complex queries." },
  { step: "5", title: "Validation & safety checks", desc: "Citations are verified against approved sources (NICE, AHA/ACC, ESC, FDA, WHO). Safety warnings are applied. Results are cached for 30 days." },
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
          An evidence-based medical reference platform that combines real-time data from
          authoritative APIs with AI formatting to deliver structured, citable clinical answers.
        </p>
      </div>

      {/* How it works */}
      <section>
        <h2 style={sectionHeading}>How it works</h2>
        <div style={{ display: "flex", flexDirection: "column", gap: "0.75rem" }}>
          {HOW_IT_WORKS.map((item) => (
            <div key={item.step} style={{ display: "flex", gap: "1rem", padding: "0.875rem 1rem", background: "var(--bg-surface)", border: "1px solid var(--border)", borderRadius: "var(--radius-md)" }}>
              <div style={{ width: 28, height: 28, borderRadius: "50%", background: "var(--accent-glow)", border: "1px solid rgba(59,130,246,0.3)", display: "flex", alignItems: "center", justifyContent: "center", flexShrink: 0, fontWeight: 700, fontSize: "0.8rem", color: "var(--accent)" }}>
                {item.step}
              </div>
              <div>
                <p style={{ margin: "0 0 0.2rem", fontWeight: 600, fontSize: "0.9rem", color: "var(--text-primary)" }}>{item.title}</p>
                <p style={{ margin: 0, fontSize: "0.825rem", color: "var(--text-secondary)", lineHeight: 1.55 }}>{item.desc}</p>
              </div>
            </div>
          ))}
        </div>
      </section>

      {/* BLUF / Response format */}
      <section>
        <h2 style={sectionHeading}>Response Format</h2>
        <p style={{ margin: "0 0 1rem", fontSize: "0.875rem", color: "var(--text-secondary)" }}>
          Adaptive responses open with a <strong style={{ color: "var(--text-primary)" }}>Bottom Line Up Front (BLUF)</strong> — the most important clinical takeaway, right at the top.
          The BLUF scales to how much data was found:
        </p>
        <div style={{ display: "flex", flexDirection: "column", gap: "0.5rem" }}>
          {[
            { label: "Headline", desc: "Always shown — single most important clinical sentence." },
            { label: "Summary", desc: "2–6 sentence elaboration. Included when sufficient data is available." },
            { label: "Key action points", desc: "Bulleted list with specific doses, thresholds, and timelines. Included for data-rich responses." },
            { label: "Caveats", desc: "Safety warnings highlighted separately. Omitted when there are none." },
          ].map((row) => (
            <div key={row.label} style={{ display: "flex", gap: "0.75rem", padding: "0.75rem 1rem", background: "var(--bg-surface)", border: "1px solid var(--border)", borderRadius: "var(--radius-md)" }}>
              <span style={{ fontWeight: 600, fontSize: "0.825rem", color: "var(--accent)", minWidth: 130, flexShrink: 0 }}>{row.label}</span>
              <span style={{ fontSize: "0.825rem", color: "var(--text-secondary)", lineHeight: 1.5 }}>{row.desc}</span>
            </div>
          ))}
        </div>
        <p style={{ margin: "0.875rem 0 0", fontSize: "0.8rem", color: "var(--text-muted)" }}>
          Below the BLUF, the response is broken into evidence-graded section cards — each claim carries a Level of Evidence (I–III) and Class of Recommendation (I–IIb) badge.
        </p>
      </section>

      {/* Search Modes (explanation only — toggle is in Settings) */}
      <section>
        <h2 style={sectionHeading}>Search Modes</h2>
        <p style={{ margin: "0 0 1rem", fontSize: "0.875rem", color: "var(--text-secondary)" }}>
          Iatronix supports three search modes. Change your active mode in{" "}
          <a href="/settings" style={{ color: "var(--accent)" }}>Settings → Search Mode</a>.
        </p>
        <div style={{ display: "flex", flexDirection: "column", gap: "0.625rem" }}>
          {MODES.map((m) => (
            <div key={m.title} style={{ display: "flex", alignItems: "flex-start", gap: "1rem", padding: "0.875rem 1rem", background: "var(--bg-surface)", border: "1px solid var(--border)", borderRadius: "var(--radius-md)" }}>
              <span style={{ color: "var(--accent)", flexShrink: 0, marginTop: 2 }}>{m.icon}</span>
              <div>
                <p style={{ margin: "0 0 0.2rem", fontWeight: 600, fontSize: "0.9rem", color: "var(--text-primary)" }}>{m.title}</p>
                <p style={{ margin: 0, fontSize: "0.825rem", color: "var(--text-secondary)", lineHeight: 1.55 }}>{m.desc}</p>
              </div>
            </div>
          ))}
        </div>
      </section>

      {/* API Keys */}
      <section>
        <h2 style={sectionHeading}>API Keys</h2>
        <p style={{ margin: "0 0 1rem", fontSize: "0.875rem", color: "var(--text-secondary)" }}>
          Iatronix uses your own API keys (BYOK — Bring Your Own Key). Keys are encrypted and never shared.
          Add them in <a href="/settings" style={{ color: "var(--accent)" }}>Settings → LLM API Key</a>.
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

      {/* Data sources */}
      <section>
        <h2 style={sectionHeading}>Data Sources</h2>
        <p style={{ margin: "0 0 1rem", fontSize: "0.875rem", color: "var(--text-secondary)" }}>
          All data is fetched in real time from these authoritative sources before any AI processing:
        </p>
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(200px, 1fr))", gap: "0.5rem" }}>
          {[
            { name: "OpenFDA", url: "https://open.fda.gov/", desc: "Drug labels & adverse events" },
            { name: "PubMed / PMC", url: "https://pubmed.ncbi.nlm.nih.gov/", desc: "Guidelines, RCTs & StatPearls monographs" },
            { name: "RxNorm", url: "https://www.nlm.nih.gov/research/umls/rxnorm/", desc: "Drug names & interactions" },
            { name: "DailyMed", url: "https://dailymed.nlm.nih.gov/", desc: "Full prescribing information" },
            { name: "MedlinePlus", url: "https://medlineplus.gov/", desc: "Drug & disease summaries" },
            { name: "Semantic Scholar", url: "https://www.semanticscholar.org/", desc: "Medical literature search" },
          ].map((src) => (
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

    </div>
  );
}

const sectionHeading: React.CSSProperties = {
  fontSize: "1.1rem", fontWeight: 700,
  color: "var(--text-primary)", margin: "0 0 0.875rem",
};
