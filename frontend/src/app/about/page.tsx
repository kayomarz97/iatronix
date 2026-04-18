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

const HOW_IT_WORKS = [
  { step: "1", title: "Query rewriting", desc: "Fixes typos, expands abbreviations, standardizes terminology (e.g., HTN → hypertension) to maximize API search accuracy." },
  { step: "2", title: "Classification", desc: "Regex pattern scoring instantly classifies the query (drug, disease, procedure, evidence, comparative). For ambiguous phrasing, a lightweight LLM call resolves the type." },
  { step: "3", title: "Parallel data fetch", desc: "Relevant data is pulled in parallel from FDA, PubMed (guidelines + RCTs), PMC full text, Unpaywall free PDFs, RxNorm, MedlinePlus, NICE, and your uploaded PDFs — zero AI tokens at this stage." },
  { step: "4", title: "Adaptive AI formatting", desc: "The adaptive pipeline analyses what you need, then formats fetched data into evidence-graded sections (LOE I–III, COR I–IIb) with approved citations. BLUF banner scales to data richness." },
  { step: "5", title: "Evidence grading & safety", desc: "Each claim is assigned LOE and COR based on its source. RCT-backed guidelines earn LOE I; unsourced claims are capped at LOE III. Citations are verified. Results are cached." },
];

const DATA_SOURCES = [
  { name: "FDA OpenFDA", url: "https://open.fda.gov/", desc: "Drug labels, adverse events, recalls" },
  { name: "PubMed", url: "https://pubmed.ncbi.nlm.nih.gov/", desc: "Guidelines, RCTs, systematic reviews" },
  { name: "PMC Open Access", url: "https://www.ncbi.nlm.nih.gov/pmc/", desc: "Full-text articles & StatPearls monographs" },
  { name: "Unpaywall", url: "https://unpaywall.org/", desc: "Free legal PDFs for open-access articles" },
  { name: "RxNorm", url: "https://www.nlm.nih.gov/research/umls/rxnorm/", desc: "Drug names & interactions" },
  { name: "MedlinePlus", url: "https://medlineplus.gov/", desc: "Drug & disease patient summaries" },
  { name: "NICE", url: "https://www.nice.org.uk/", desc: "UK clinical practice guidelines" },
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
    name: "Voyage AI (embeddings)",
    desc: "Free embeddings API for Anthropic users (Anthropic has no embeddings). 200M tokens/month free tier.",
    url: "https://www.voyageai.com",
    label: "Create free account",
    note: "Optional, for Anthropic users only",
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
          Query real-time data from FDA, PubMed, NICE, and your own documents — formatted with AI, graded by evidence.
          Your API key. Your data. Your control.
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

      {/* BYOK section */}
      <section>
        <h2 style={sectionHeading}>BYOK — Your Key, Your Data</h2>
        <p style={{ margin: "0 0 1rem", fontSize: "0.875rem", color: "var(--text-secondary)" }}>
          All LLM calls use <strong style={{ color: "var(--text-primary)" }}>your own API key</strong>. Nothing is sent to Iatronix servers for generation.
          Supported providers: Anthropic (Claude), OpenAI (GPT), Google Gemini, OpenRouter.
        </p>
        <div style={{ display: "flex", flexDirection: "column", gap: "0.5rem" }}>
          {[
            { label: "Encrypted storage", desc: "API keys are encrypted at rest and in transit. Only you can use your key." },
            { label: "No vendor lock-in", desc: "Switch providers anytime from Settings — your data is not locked in." },
            { label: "Privacy by design", desc: "FDA data, PubMed articles, and your PDFs flow through your own LLM. No third-party processing." },
          ].map((row) => (
            <div key={row.label} style={{ display: "flex", gap: "0.75rem", padding: "0.75rem 1rem", background: "var(--bg-surface)", border: "1px solid var(--border)", borderRadius: "var(--radius-md)" }}>
              <span style={{ fontWeight: 600, fontSize: "0.825rem", color: "var(--accent)", minWidth: 130, flexShrink: 0 }}>{row.label}</span>
              <span style={{ fontSize: "0.825rem", color: "var(--text-secondary)", lineHeight: 1.5 }}>{row.desc}</span>
            </div>
          ))}
        </div>
      </section>

      {/* Response Format */}
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
      </section>

      {/* Data Sources */}
      <section>
        <h2 style={sectionHeading}>Data Sources</h2>
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

      {/* PDF Vector Search */}
      <section>
        <h2 style={sectionHeading}>PDF Vector Search</h2>
        <p style={{ margin: "0 0 1rem", fontSize: "0.875rem", color: "var(--text-secondary)" }}>
          Upload your own medical PDFs and search them semantically. Each query is embedded using your chosen provider's embeddings API.
        </p>
        <div style={{ display: "flex", flexDirection: "column", gap: "0.5rem" }}>
          {[
            { label: "Your embeddings key", desc: "OpenAI, Google, or Voyage AI. Select your provider in Settings." },
            { label: "Anthropic users", desc: "Anthropic has no embeddings API. Get a free Voyage AI key (200M tokens/month) to enable PDF search." },
            { label: "Encrypted storage", desc: "Uploaded PDFs are stored securely in Supabase pgvector. Only you can search them." },
          ].map((row) => (
            <div key={row.label} style={{ display: "flex", gap: "0.75rem", padding: "0.75rem 1rem", background: "var(--bg-surface)", border: "1px solid var(--border)", borderRadius: "var(--radius-md)" }}>
              <span style={{ fontWeight: 600, fontSize: "0.825rem", color: "var(--accent)", minWidth: 130, flexShrink: 0 }}>{row.label}</span>
              <span style={{ fontSize: "0.825rem", color: "var(--text-secondary)", lineHeight: 1.5 }}>{row.desc}</span>
            </div>
          ))}
        </div>
      </section>

      {/* Evidence Grading */}
      <section>
        <h2 style={sectionHeading}>Evidence Grading</h2>
        <p style={{ margin: "0 0 1rem", fontSize: "0.875rem", color: "var(--text-secondary)" }}>
          Every claim is assigned a Level of Evidence and Class of Recommendation:
        </p>
        <div style={{ display: "flex", flexDirection: "column", gap: "0.5rem" }}>
          {[
            {
              label: "Level of Evidence (LOE)",
              desc: "I = Randomized controlled trial (RCT). II = Prospective cohort / guideline consensus. III = Case reports / expert opinion.",
            },
            {
              label: "Class of Recommendation (COR)",
              desc: "I = Strong benefit (should be done). IIa = Moderate benefit (reasonable). IIb = Weak benefit (may consider). III = No benefit or harmful.",
            },
          ].map((row) => (
            <div key={row.label} style={{ display: "flex", gap: "0.75rem", padding: "0.75rem 1rem", background: "var(--bg-surface)", border: "1px solid var(--border)", borderRadius: "var(--radius-md)" }}>
              <span style={{ fontWeight: 600, fontSize: "0.825rem", color: "var(--accent)", minWidth: 180, flexShrink: 0 }}>{row.label}</span>
              <span style={{ fontSize: "0.825rem", color: "var(--text-secondary)", lineHeight: 1.5 }}>{row.desc}</span>
            </div>
          ))}
        </div>
      </section>

      {/* Search Modes */}
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
        <h2 style={sectionHeading}>LLM & Embedding API Keys</h2>
        <p style={{ margin: "0 0 1rem", fontSize: "0.875rem", color: "var(--text-secondary)" }}>
          Iatronix uses your own API keys (BYOK — Bring Your Own Key). Keys are encrypted and never shared.
          Add them in <a href="/settings" style={{ color: "var(--accent)" }}>Settings</a>.
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
