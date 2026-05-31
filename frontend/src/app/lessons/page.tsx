"use client";

// Full "Lessons Learnt" / Engineering Journal article.
// Source of truth: /ENGINEERING_JOURNAL.md (kept in sync).

type Block = { h?: string; p?: string; list?: string[] };

const SECTIONS: { id: string; title: string; blocks: Block[] }[] = [
  {
    id: "what",
    title: "What Iatronix is",
    blocks: [
      {
        p: "A BYOK (bring-your-own-key) medical reference engine. Users supply their own LLM API key; the system classifies a clinical query, fetches live evidence from 10+ free medical APIs (PubMed/NCBI, openFDA, RxNorm, DailyMed, MedlinePlus, NICE, ClinicalTrials.gov, Semantic Scholar, NCBI Bookshelf, ChEMBL), ranks it by evidence quality, and synthesises a typed, evidence-graded answer where every clinical claim traces to a fetched source. No server-side LLM keys, ever.",
      },
      {
        p: "The hardest engineering problem here is not generation — it is grounding: making a language model say only what the retrieved evidence supports, with a correct citation, and nothing else.",
      },
    ],
  },
  {
    id: "seams",
    title: "The two seams every regression came from",
    blocks: [
      {
        h: "Seam A — citation grounding under a changing pipeline",
        p: "References kept disappearing. It was fixed at least five times before it stuck. The lesson: grounding must be deterministic, not best-effort.",
      },
      {
        list: [
          "[REF_N] citation tokens — the LLM may only cite tokens we injected into the data block; a resolver maps them to real PMIDs/URLs. The model can't invent a citation.",
          "Article Registry — an immutable post-fetch registry where every entry has a validated article-level URL. The reference list is built from this, not from LLM output.",
          "Demote, don't drop — ungrounded claims are demoted to low-confidence 'Expert opinion', never deleted. Drop-based logic was what made reference lists vanish.",
          "Evidence Floor — no synthesis without at least one citable source; if retrieval is genuinely empty, return an honest 'No evidence found'.",
        ],
      },
      {
        h: "Seam B — provider/model selection state",
        p: "The provider toggle kept getting stuck: the backend used 'first key wins' instead of honouring the user's preference, and the frontend held a stale config at submit. The fix was a server-canonical active provider + a re-fetch at submit. The deeper lesson that drove the June refactor: provider/model identity must have exactly one source of truth, or the frontend and backend drift.",
      },
    ],
  },
  {
    id: "gotchas",
    title: "Hard-won gotchas",
    blocks: [
      {
        list: [
          "gpt-oss-* must route to Cerebras before the gpt- OpenAI check — order is load-bearing or gpt-oss-120b 404s on OpenAI.",
          "Cerebras prompt caching is byte-fragile: it's a server-side prefix cache, so one character before the static prefix silently kills the hit. Hits cut latency, not cost.",
          "Anthropic Haiku 4.5's cache floor is 4,096 tokens — marking a smaller block does nothing (no error, no cache).",
          "text-embedding-004 was shut down and claude-sonnet-4 (May 2025) retires June 2026 — verify model IDs against live docs, never memory.",
          "Stance-loaded queries bias retrieval. 'Why is X not rational?' fetches one-sided evidence; we neutralise the query before retrieving.",
        ],
      },
    ],
  },
  {
    id: "refactor",
    title: "The provider-agnostic refactor (June 2026)",
    blocks: [
      {
        p: "Four overlapping, drifting catalogs defined providers and models, and provider identity was imperative — provider == 'anthropic' branched in a dozen files. Adding a provider meant editing many files and hoping the frontend and backend agreed.",
      },
      {
        p: "The fix: one file. backend/config/providers.yaml is now the single source of truth. A loaded registry drives routing, client construction, caching, pricing, the providers endpoint, and the frontend's key-entry UI and model picker. Flipping a provider's 'enabled' flag activates it on both the frontend and backend with no other edit.",
      },
      {
        p: "Keys moved behind a KeyStore abstraction (Postgres authoritative, optional Firestore mirror, dual-write) so migration is a config flip. And the old 'thin retrieval -> quick degrade' path was replaced by bounded parallel citation-chasing: from any found article, follow its citations (depth 5, ~120s, in parallel), assemble a grounded answer, or honestly say 'No evidence found' — never fabricating to avoid it.",
      },
      {
        p: "Method that paid off: before writing any adapter or graph code, we fetched the current official docs for every provider and wrote them down. That caught an embedding-model shutdown, a model retirement, wrong pricing in two places, the Haiku cache floor, and a LangGraph default change — all things memory got wrong.",
      },
    ],
  },
  {
    id: "principles",
    title: "Principles, distilled",
    blocks: [
      {
        list: [
          "Grounding is deterministic or it's broken. Tokens -> registry -> demote -> floor. Never trust the model to cite.",
          "One source of truth, or the layers drift.",
          "Fail closed, honestly. For a medical tool, 'No evidence found' is a correct answer; a confident ungrounded answer is a bug.",
          "Read the current docs, not your memory. APIs drift faster than intuition.",
          "Preserve load-bearing invariants (cache prefixes, timeouts, the evidence contract) when refactoring — change structure, not semantics.",
        ],
      },
    ],
  },
];

export default function LessonsPage() {
  return (
    <main style={{ maxWidth: 760, margin: "0 auto", padding: "2.5rem 1.25rem 4rem" }}>
      <p style={{ fontSize: "0.8rem", letterSpacing: "0.08em", textTransform: "uppercase", color: "var(--text-muted)", margin: "0 0 0.4rem" }}>
        Engineering Journal
      </p>
      <h1 style={{ fontSize: "2rem", fontWeight: 800, color: "var(--text-primary)", margin: "0 0 0.5rem" }}>
        Lessons Learnt building Iatronix
      </h1>
      <p style={{ fontSize: "0.95rem", color: "var(--text-secondary)", lineHeight: 1.7, margin: "0 0 2rem" }}>
        Why each design choice was made, the bugs that taught us, and the provider-agnostic refactor.
      </p>

      {SECTIONS.map((s) => (
        <section key={s.id} style={{ marginBottom: "2rem" }}>
          <h2 style={{ fontSize: "1.25rem", fontWeight: 700, color: "var(--text-primary)", margin: "0 0 0.75rem" }}>
            {s.title}
          </h2>
          {s.blocks.map((b, i) => (
            <div key={i} style={{ marginBottom: "0.85rem" }}>
              {b.h && (
                <h3 style={{ fontSize: "1rem", fontWeight: 600, color: "var(--text-primary)", margin: "0 0 0.4rem" }}>{b.h}</h3>
              )}
              {b.p && (
                <p style={{ fontSize: "0.95rem", color: "var(--text-secondary)", lineHeight: 1.75, margin: 0 }}>{b.p}</p>
              )}
              {b.list && (
                <ul style={{ margin: "0.25rem 0 0", paddingLeft: "1.1rem", display: "flex", flexDirection: "column", gap: "0.5rem" }}>
                  {b.list.map((item, j) => (
                    <li key={j} style={{ fontSize: "0.925rem", color: "var(--text-secondary)", lineHeight: 1.65 }}>{item}</li>
                  ))}
                </ul>
              )}
            </div>
          ))}
        </section>
      ))}

      <a href="/about" style={{ display: "inline-flex", fontSize: "0.875rem", fontWeight: 600, color: "var(--primary)" }}>
        &larr; Back to About
      </a>
    </main>
  );
}
