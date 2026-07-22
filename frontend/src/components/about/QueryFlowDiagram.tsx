"use client";

import { useState } from "react";
import type { CSSProperties, ReactNode } from "react";
import {
  MessageSquare,
  Brain,
  GitBranch,
  Database,
  GitMerge,
  Gauge,
  Link2,
  PenLine,
  FileCheck,
  ChevronDown,
  ShieldCheck,
  SearchX,
  RefreshCw,
  Pill,
  Stethoscope,
  Syringe,
  FlaskConical,
  GitCompare,
  Layers,
} from "lucide-react";

/**
 * QueryFlowDiagram — a theme-aware visual of how a clinical query flows through
 * Iatronix: the question is understood, scope-checked, fanned out to one of six
 * strategies, searched in parallel across trusted sources, merged into one
 * evidence set, gated on confidence, grounded to citations, written and delivered.
 *
 * A Plain / Technical / Both toggle rewrites every node so a clinician can read
 * the layman explanation, an engineer can read the technical one, or both.
 *
 * Styling uses ONLY the app's existing CSS-variable tokens (globals.css), so it
 * tracks the light/dark theme automatically — no hardcoded chrome colours.
 */

type Mode = "plain" | "technical" | "both";

const QUERY_TYPES = [
  {
    icon: Pill,
    name: "Drug",
    plain: "One medicine — its mechanism, dosing and interactions.",
    tech: "single-drug intent → openFDA + RxNorm + label sources",
  },
  {
    icon: Stethoscope,
    name: "Disease",
    plain: "One condition or symptom — diagnosis, staging and management.",
    tech: "single-condition intent → guidelines + reviews",
  },
  {
    icon: Syringe,
    name: "Procedure",
    plain: "How to perform a technique, step by step.",
    tech: "how-to intent → StatPearls / Bookshelf + guidelines",
  },
  {
    icon: FlaskConical,
    name: "Evidence",
    plain: "Does a treatment actually work here? Includes clinical trials.",
    tech: "efficacy intent → PubMed + ClinicalTrials.gov",
  },
  {
    icon: GitCompare,
    name: "Comparative",
    plain: "Drug A versus drug B, head to head.",
    tech: "two-entity intent → comparative retrieval",
  },
  {
    icon: Layers,
    name: "Complex",
    plain: "Multiple conditions or comorbidities — the catch-all default.",
    tech: "multi-entity / fallback intent → broad retrieval",
  },
];

const SOURCES = [
  "PubMed",
  "openFDA",
  "RxNorm",
  "ClinicalTrials.gov",
  "NICE",
  "StatPearls / Bookshelf",
  "MedlinePlus",
];

export function QueryFlowDiagram() {
  const [mode, setMode] = useState<Mode>("both");

  return (
    <div>
      {/* Plain / Technical / Both toggle — app-native segmented control */}
      <div style={toggleRow}>
        <span style={toggleHint}>Read it as</span>
        <div className="segment-control" role="tablist" aria-label="Explanation detail level">
          {(["plain", "technical", "both"] as Mode[]).map((m) => (
            <button
              key={m}
              type="button"
              role="tab"
              aria-selected={mode === m}
              className={`segment-btn ${mode === m ? "active" : ""}`}
              onClick={() => setMode(m)}
            >
              {m === "plain" ? "Plain" : m === "technical" ? "Technical" : "Both"}
            </button>
          ))}
        </div>
      </div>

      <div style={wrap}>
        {/* 1 — Ask */}
        <FlowNode
          mode={mode}
          num={1}
          icon={<MessageSquare size={19} />}
          title="A clinician asks a question"
          plain="Type it in plain language — no special syntax needed."
          tech="free-text clinical query captured verbatim"
        />

        <Connector />

        {/* 2 — Understand */}
        <FlowNode
          mode={mode}
          num={2}
          icon={<Brain size={19} />}
          title="Understand the question"
          plain="The app works out what you are really asking and pulls out the key medical terms."
          tech="classify into 1 of 6 types · extract key terms · rewrite neutrally to strip leading phrasing"
        />

        <Connector />

        {/* Scope guard — a decision off stage 2 */}
        <ScopeGuard mode={mode} />

        <Connector label="clinical question — one path splits into six" icon={<GitBranch size={14} />} />

        {/* 3 + 4 — Branch out (fan) and Fetch in parallel */}
        <div style={branchPanel}>
          <div style={accentStrip} aria-hidden />

          <PanelHeader
            mode={mode}
            num={3}
            icon={<GitBranch size={17} />}
            title="Branch by type"
            plain="One of six strategies is chosen. Each decides which trusted sources to search."
            tech="route by query type → strategy selects its source set"
          />

          <div style={typeGrid}>
            {QUERY_TYPES.map((t) => {
              const Icon = t.icon;
              const showPlain = mode !== "technical";
              const showTech = mode !== "plain";
              return (
                <div key={t.name} style={typeCard}>
                  <div style={typeIconBadge}>
                    <Icon size={16} />
                  </div>
                  <div style={{ minWidth: 0 }}>
                    <p style={typeName}>{t.name}</p>
                    {showPlain && <p style={typePlain}>{t.plain}</p>}
                    {showTech && <p style={typeTech}>{t.tech}</p>}
                  </div>
                </div>
              );
            })}
          </div>

          <div style={fanCaption}>
            <ChevronDown size={14} style={{ flexShrink: 0 }} />
            <span>All of that branch&rsquo;s searches fire at the same time</span>
          </div>

          <PanelHeader
            mode={mode}
            num={4}
            icon={<Database size={17} />}
            title="Fetch — in parallel"
            plain="Every search in the branch runs at once across trusted medical sources, then results come back in one batch."
            tech="parallel fan-out across sources · single batched await · per-source failures skipped, not fatal"
          />

          <div style={sourceRow}>
            {SOURCES.map((s) => (
              <span key={s} style={sourcePill}>
                {s}
              </span>
            ))}
          </div>
        </div>

        <Connector label="six result sets converge into one" icon={<GitMerge size={14} />} />

        {/* 5 — Rank & merge */}
        <FlowNode
          mode={mode}
          num={5}
          icon={<GitMerge size={19} />}
          title="Rank, then merge into one evidence set"
          plain="Everything found is scored for quality, then pooled into a single body of evidence — the strongest studies rise to the top."
          tech="score by study type · relevance · recency · citations → combine into one evidence set"
        />

        <Connector label="is the evidence strong enough?" icon={<Gauge size={14} />} />

        {/* Confidence gate — a decision with an escalation loop and an honest dead end */}
        <ConfidenceGate mode={mode} />

        <Connector label="enough evidence — continue" icon={<Link2 size={14} />} />

        {/* 6 — Ground */}
        <FlowNode
          mode={mode}
          num={6}
          icon={<Link2 size={19} />}
          title="Ground every claim"
          plain="Each fact is tied to a real, cited article. Anything that can't be backed up is flagged, never stated as fact."
          tech="per-claim citation binding · unbackable claims marked low-confidence"
        />

        <Connector />

        {/* 7 — Write */}
        <FlowNode
          mode={mode}
          num={7}
          icon={<PenLine size={19} />}
          title="Write the answer"
          plain="The bottom line comes first, then each section is written and streamed to you live."
          tech="bottom-line-up-front, then per-section parallel generation, streamed"
        />

        <Connector />

        {/* 8 — Deliver */}
        <FlowNode
          mode={mode}
          num={8}
          icon={<FileCheck size={19} />}
          title="Deliver"
          plain="You get a clear, structured answer with confidence badges and links to the real sources."
          tech="structured, cited answer with confidence badges and source links"
          terminal
        />
      </div>
    </div>
  );
}

/* ── Sub-components ──────────────────────────────────────────────────────── */

function FlowNode({
  mode,
  num,
  icon,
  title,
  plain,
  tech,
  terminal,
}: {
  mode: Mode;
  num: number;
  icon: ReactNode;
  title: string;
  plain: string;
  tech: string;
  terminal?: boolean;
}) {
  const showPlain = mode !== "technical";
  const showTech = mode !== "plain";
  return (
    <div style={{ ...nodeCard, ...(terminal ? terminalCard : null) }}>
      <div style={numBadge}>{num}</div>
      <div style={nodeIcon}>{icon}</div>
      <div style={{ minWidth: 0 }}>
        <p style={nodeTitle}>{title}</p>
        {showPlain && <p style={nodePlain}>{plain}</p>}
        {showTech && <p style={nodeTech}>{tech}</p>}
      </div>
    </div>
  );
}

function PanelHeader({
  mode,
  num,
  icon,
  title,
  plain,
  tech,
}: {
  mode: Mode;
  num: number;
  icon: ReactNode;
  title: string;
  plain: string;
  tech: string;
}) {
  const showPlain = mode !== "technical";
  const showTech = mode !== "plain";
  return (
    <div style={panelHeaderRow}>
      <div style={panelNumBadge}>{num}</div>
      <div style={panelIcon}>{icon}</div>
      <div style={{ minWidth: 0 }}>
        <p style={panelTitle}>{title}</p>
        {showPlain && <p style={panelPlain}>{plain}</p>}
        {showTech && <p style={panelTech}>{tech}</p>}
      </div>
    </div>
  );
}

function ScopeGuard({ mode }: { mode: Mode }) {
  const showPlain = mode !== "technical";
  const showTech = mode !== "plain";
  return (
    <div style={guardWrap}>
      <div style={guardHeader}>
        <ShieldCheck size={16} style={{ flexShrink: 0, color: "var(--accent)" }} />
        <span>
          <strong style={{ color: "var(--text-primary)", fontWeight: 600 }}>
            Scope check
          </strong>{" "}
          — first, is this actually a clinical question?
        </span>
      </div>

      <div style={guardFork}>
        {/* No — decline, dead end (muted, never alarming) */}
        <div style={declineCard}>
          <span style={declineTag}>No</span>
          <div style={declineBody}>
            <div style={declineIcon}>
              <SearchX size={16} />
            </div>
            <div style={{ minWidth: 0 }}>
              <p style={declineTitle}>Not a clinical question</p>
              {showPlain && (
                <p style={declinePlain}>
                  No drug, disease, symptom or procedure is found, so the app declines
                  politely and does <strong>not</strong> search the medical literature.
                </p>
              )}
              {showTech && (
                <p style={declineTech}>
                  non-medical guard · no medical entities extracted &rarr; out_of_scope
                </p>
              )}
            </div>
          </div>
        </div>

        {/* Yes — continue to the six-type branch */}
        <div style={continueCard}>
          <span style={continueTag}>Yes</span>
          <div style={{ minWidth: 0, flex: 1 }}>
            <p style={continueTitle}>A clinical question</p>
            {showPlain && (
              <p style={continuePlain}>
                A medical entity is detected, so the query flows on to the six strategies
                below.
              </p>
            )}
            {showTech && (
              <p style={continueTech}>medical entity extracted &rarr; in_scope, continue</p>
            )}
          </div>
          <ChevronDown size={17} style={{ color: "var(--accent)", alignSelf: "center", flexShrink: 0 }} />
        </div>
      </div>
    </div>
  );
}

function ConfidenceGate({ mode }: { mode: Mode }) {
  const showPlain = mode !== "technical";
  const showTech = mode !== "plain";
  return (
    <div style={guardWrap}>
      <div style={guardHeader}>
        <Gauge size={16} style={{ flexShrink: 0, color: "var(--accent)" }} />
        <span>
          <strong style={{ color: "var(--text-primary)", fontWeight: 600 }}>
            Confidence gate
          </strong>{" "}
          — is there enough distinct evidence to answer?
        </span>
      </div>

      {/* Escalation ladder — the loop that runs BEFORE the app is allowed to give up */}
      <div style={escalateStrip}>
        <div style={escalateIcon}>
          <RefreshCw size={16} />
        </div>
        <div style={{ minWidth: 0 }}>
          <p style={escalateTitle}>If it looks thin, it tries harder before answering</p>
          {showPlain && (
            <p style={escalatePlain}>
              It rewords the search, borrows a complementary strategy, follows citation trails, and
              broadens step by step — looping back to re-check each time — rather than answering on
              weak evidence.
            </p>
          )}
          {showTech && (
            <p style={escalateTech}>
              same-strategy 2nd pass &rarr; cross-strategy borrow &rarr; iCite citation-chase &rarr;
              up to 5 progressive broadenings &rarr; re-evaluate
            </p>
          )}
        </div>
      </div>

      <div style={guardFork}>
        {/* Still nothing — honest dead end (muted, never alarming) */}
        <div style={declineCard}>
          <span style={declineTag}>No</span>
          <div style={declineBody}>
            <div style={declineIcon}>
              <SearchX size={16} />
            </div>
            <div style={{ minWidth: 0 }}>
              <p style={declineTitle}>No strong evidence</p>
              {showPlain && (
                <p style={declinePlain}>
                  If every attempt still comes up short, the app returns an honest &ldquo;not enough
                  evidence&rdquo; card and <strong>never</strong> writes an answer.
                </p>
              )}
              {showTech && (
                <p style={declineTech}>
                  evidence floor unmet after escalation &rarr; DegradedResponse, no generation
                </p>
              )}
            </div>
          </div>
        </div>

        {/* Enough — continue to grounding */}
        <div style={continueCard}>
          <span style={continueTag}>Yes</span>
          <div style={{ minWidth: 0, flex: 1 }}>
            <p style={continueTitle}>Strong enough</p>
            {showPlain && (
              <p style={continuePlain}>
                Enough distinct, on-topic evidence is in hand, so the query flows on to grounding
                and writing.
              </p>
            )}
            {showTech && (
              <p style={continueTech}>&ge; unique-article floor of distinct sources &rarr; proceed</p>
            )}
          </div>
          <ChevronDown size={17} style={{ color: "var(--accent)", alignSelf: "center", flexShrink: 0 }} />
        </div>
      </div>
    </div>
  );
}

function Connector({ label, icon }: { label?: string; icon?: ReactNode }) {
  return (
    <div style={connectorWrap} aria-hidden={!label}>
      <span style={connectorLine} />
      {label ? (
        <span style={connectorLabel}>
          {icon}
          {label}
        </span>
      ) : (
        <ChevronDown size={17} style={{ color: "var(--text-muted)" }} />
      )}
      <span style={connectorLine} />
    </div>
  );
}

/* ── Styles (tokens only) ───────────────────────────────────────────────── */

const toggleRow: CSSProperties = {
  display: "flex",
  alignItems: "center",
  gap: "0.6rem",
  marginBottom: "1.1rem",
  flexWrap: "wrap",
};

const toggleHint: CSSProperties = {
  fontSize: "0.85rem",
  color: "var(--text-muted)",
};

const wrap: CSSProperties = {
  display: "flex",
  flexDirection: "column",
  alignItems: "stretch",
};

const nodeCard: CSSProperties = {
  position: "relative",
  display: "flex",
  gap: "0.9rem",
  alignItems: "flex-start",
  padding: "1rem 1.1rem 1rem 1.15rem",
  background: "var(--bg-surface)",
  border: "1px solid var(--border)",
  borderRadius: "var(--radius-lg)",
  boxShadow: "var(--shadow-sm)",
};

const terminalCard: CSSProperties = {
  borderColor: "var(--border-focus)",
  boxShadow: "var(--ring)",
};

const numBadge: CSSProperties = {
  position: "absolute",
  top: -10,
  left: -10,
  width: 24,
  height: 24,
  borderRadius: "50%",
  background: "var(--accent)",
  color: "#fff",
  fontSize: "0.78rem",
  fontWeight: 700,
  display: "flex",
  alignItems: "center",
  justifyContent: "center",
  boxShadow: "var(--shadow-sm)",
};

const nodeIcon: CSSProperties = {
  flexShrink: 0,
  width: 38,
  height: 38,
  borderRadius: "var(--radius-md)",
  background: "var(--accent-glow)",
  color: "var(--accent)",
  display: "flex",
  alignItems: "center",
  justifyContent: "center",
};

const nodeTitle: CSSProperties = {
  margin: "0 0 0.3rem",
  fontWeight: 600,
  fontSize: "1rem",
  color: "var(--text-primary)",
};

const nodePlain: CSSProperties = {
  margin: 0,
  fontSize: "0.95rem",
  color: "var(--text-secondary)",
  lineHeight: 1.55,
};

const nodeTech: CSSProperties = {
  margin: "0.4rem 0 0",
  fontSize: "0.85rem",
  color: "var(--text-muted)",
  lineHeight: 1.55,
  fontFamily: "var(--font-mono)",
};

const connectorWrap: CSSProperties = {
  display: "flex",
  alignItems: "center",
  justifyContent: "center",
  gap: "0.6rem",
  padding: "0.5rem 0",
};

const connectorLine: CSSProperties = {
  flex: 1,
  maxWidth: 90,
  height: 2,
  borderRadius: 1,
  background:
    "linear-gradient(90deg, transparent, var(--border-focus), transparent)",
  opacity: 0.7,
};

const connectorLabel: CSSProperties = {
  display: "inline-flex",
  alignItems: "center",
  gap: "0.4rem",
  fontSize: "0.8rem",
  fontWeight: 500,
  color: "var(--accent)",
  background: "var(--accent-glow)",
  border: "1px solid var(--border-focus)",
  borderRadius: 999,
  padding: "4px 12px",
  textAlign: "center",
};

const branchPanel: CSSProperties = {
  position: "relative",
  overflow: "hidden",
  padding: "1.2rem 1.1rem 1.25rem",
  background: "var(--bg-elevated)",
  border: "1px solid var(--border)",
  borderRadius: "var(--radius-lg)",
  boxShadow: "var(--shadow-sm)",
};

const accentStrip: CSSProperties = {
  position: "absolute",
  top: 0,
  left: 0,
  right: 0,
  height: 3,
  background: "var(--accent-gradient)",
};

const panelHeaderRow: CSSProperties = {
  position: "relative",
  display: "flex",
  gap: "0.7rem",
  alignItems: "flex-start",
  marginTop: "0.35rem",
};

const panelNumBadge: CSSProperties = {
  flexShrink: 0,
  width: 22,
  height: 22,
  borderRadius: "50%",
  background: "var(--accent)",
  color: "#fff",
  fontSize: "0.75rem",
  fontWeight: 700,
  display: "flex",
  alignItems: "center",
  justifyContent: "center",
};

const panelIcon: CSSProperties = {
  flexShrink: 0,
  color: "var(--accent)",
  display: "flex",
  alignItems: "center",
  marginTop: 1,
};

const panelTitle: CSSProperties = {
  margin: "0 0 0.2rem",
  fontWeight: 700,
  fontSize: "0.98rem",
  color: "var(--text-primary)",
};

const panelPlain: CSSProperties = {
  margin: 0,
  fontSize: "0.9rem",
  color: "var(--text-secondary)",
  lineHeight: 1.5,
};

const panelTech: CSSProperties = {
  margin: "0.3rem 0 0",
  fontSize: "0.85rem",
  color: "var(--text-muted)",
  lineHeight: 1.5,
  fontFamily: "var(--font-mono)",
};

const typeGrid: CSSProperties = {
  display: "grid",
  gridTemplateColumns: "repeat(auto-fit, minmax(200px, 1fr))",
  gap: "0.6rem",
  margin: "0.9rem 0 0.4rem",
};

const typeCard: CSSProperties = {
  display: "flex",
  gap: "0.6rem",
  alignItems: "flex-start",
  padding: "0.75rem 0.8rem",
  background: "var(--bg-surface)",
  border: "1px solid var(--border)",
  borderRadius: "var(--radius-md)",
};

const typeIconBadge: CSSProperties = {
  flexShrink: 0,
  width: 30,
  height: 30,
  borderRadius: "var(--radius-sm)",
  background: "var(--accent-glow)",
  color: "var(--accent)",
  display: "flex",
  alignItems: "center",
  justifyContent: "center",
};

const typeName: CSSProperties = {
  margin: "0 0 0.2rem",
  fontWeight: 600,
  fontSize: "0.95rem",
  color: "var(--text-primary)",
};

const typePlain: CSSProperties = {
  margin: 0,
  fontSize: "0.9rem",
  color: "var(--text-secondary)",
  lineHeight: 1.45,
};

const typeTech: CSSProperties = {
  margin: "0.3rem 0 0",
  fontSize: "0.85rem",
  color: "var(--text-muted)",
  lineHeight: 1.45,
  fontFamily: "var(--font-mono)",
};

const fanCaption: CSSProperties = {
  display: "flex",
  alignItems: "center",
  justifyContent: "center",
  gap: "0.4rem",
  margin: "0.65rem 0 1rem",
  fontSize: "0.85rem",
  fontWeight: 500,
  color: "var(--text-muted)",
  textAlign: "center",
};

const sourceRow: CSSProperties = {
  display: "flex",
  flexWrap: "wrap",
  gap: "0.45rem",
  marginTop: "0.75rem",
};

const sourcePill: CSSProperties = {
  fontSize: "0.82rem",
  fontWeight: 500,
  color: "var(--text-secondary)",
  background: "var(--bg-hover)",
  border: "1px solid var(--border)",
  borderRadius: 999,
  padding: "4px 11px",
  fontFamily: "var(--font-mono)",
};

/* Scope guard */
const guardWrap: CSSProperties = {
  padding: "1rem 1.1rem 1.1rem",
  background: "var(--bg-elevated)",
  border: "1px solid var(--border)",
  borderRadius: "var(--radius-lg)",
  boxShadow: "var(--shadow-sm)",
};

const guardHeader: CSSProperties = {
  display: "flex",
  alignItems: "center",
  gap: "0.5rem",
  fontSize: "0.92rem",
  color: "var(--text-secondary)",
  lineHeight: 1.45,
};

const guardFork: CSSProperties = {
  display: "grid",
  gridTemplateColumns: "repeat(auto-fit, minmax(250px, 1fr))",
  gap: "0.7rem",
  marginTop: "0.85rem",
};

/* Confidence-gate escalation ladder (the loop before giving up) */
const escalateStrip: CSSProperties = {
  display: "flex",
  gap: "0.6rem",
  alignItems: "flex-start",
  marginTop: "0.85rem",
  padding: "0.8rem 0.9rem",
  background: "var(--accent-glow)",
  border: "1px dashed var(--border-focus)",
  borderRadius: "var(--radius-md)",
};

const escalateIcon: CSSProperties = {
  flexShrink: 0,
  width: 30,
  height: 30,
  borderRadius: "var(--radius-sm)",
  background: "var(--bg-surface)",
  color: "var(--accent)",
  display: "flex",
  alignItems: "center",
  justifyContent: "center",
};

const escalateTitle: CSSProperties = {
  margin: "0 0 0.2rem",
  fontWeight: 600,
  fontSize: "0.92rem",
  color: "var(--text-primary)",
};

const escalatePlain: CSSProperties = {
  margin: 0,
  fontSize: "0.88rem",
  color: "var(--text-secondary)",
  lineHeight: 1.5,
};

const escalateTech: CSSProperties = {
  margin: "0.3rem 0 0",
  fontSize: "0.85rem",
  color: "var(--text-muted)",
  lineHeight: 1.45,
  fontFamily: "var(--font-mono)",
};

const declineCard: CSSProperties = {
  position: "relative",
  padding: "0.8rem 0.9rem",
  background: "var(--bg-surface)",
  border: "1px dashed var(--border)",
  borderRadius: "var(--radius-md)",
};

const declineTag: CSSProperties = {
  display: "inline-block",
  marginBottom: "0.5rem",
  fontSize: "0.72rem",
  fontWeight: 700,
  letterSpacing: "0.06em",
  textTransform: "uppercase",
  color: "var(--text-muted)",
  background: "var(--bg-hover)",
  border: "1px solid var(--border)",
  borderRadius: 999,
  padding: "2px 9px",
};

const declineBody: CSSProperties = {
  display: "flex",
  gap: "0.6rem",
  alignItems: "flex-start",
};

const declineIcon: CSSProperties = {
  flexShrink: 0,
  width: 30,
  height: 30,
  borderRadius: "var(--radius-sm)",
  background: "var(--bg-hover)",
  color: "var(--text-muted)",
  display: "flex",
  alignItems: "center",
  justifyContent: "center",
};

const declineTitle: CSSProperties = {
  margin: "0 0 0.2rem",
  fontWeight: 600,
  fontSize: "0.95rem",
  color: "var(--text-secondary)",
};

const declinePlain: CSSProperties = {
  margin: 0,
  fontSize: "0.88rem",
  color: "var(--text-muted)",
  lineHeight: 1.5,
};

const declineTech: CSSProperties = {
  margin: "0.35rem 0 0",
  fontSize: "0.85rem",
  color: "var(--text-muted)",
  lineHeight: 1.45,
  fontFamily: "var(--font-mono)",
};

const continueCard: CSSProperties = {
  position: "relative",
  display: "flex",
  gap: "0.6rem",
  alignItems: "flex-start",
  padding: "0.8rem 0.9rem",
  background: "var(--accent-glow)",
  border: "1px solid var(--border-focus)",
  borderRadius: "var(--radius-md)",
};

const continueTag: CSSProperties = {
  flexShrink: 0,
  alignSelf: "flex-start",
  fontSize: "0.72rem",
  fontWeight: 700,
  letterSpacing: "0.06em",
  textTransform: "uppercase",
  color: "var(--accent)",
  background: "var(--bg-surface)",
  border: "1px solid var(--border-focus)",
  borderRadius: 999,
  padding: "2px 9px",
};

const continueTitle: CSSProperties = {
  margin: "0 0 0.2rem",
  fontWeight: 600,
  fontSize: "0.95rem",
  color: "var(--text-primary)",
};

const continuePlain: CSSProperties = {
  margin: 0,
  fontSize: "0.88rem",
  color: "var(--text-secondary)",
  lineHeight: 1.5,
};

const continueTech: CSSProperties = {
  margin: "0.35rem 0 0",
  fontSize: "0.85rem",
  color: "var(--text-muted)",
  lineHeight: 1.45,
  fontFamily: "var(--font-mono)",
};
