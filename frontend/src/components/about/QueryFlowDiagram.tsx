"use client";

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
  Pill,
  Stethoscope,
  Syringe,
  FlaskConical,
  GitCompare,
  Layers,
} from "lucide-react";

/**
 * QueryFlowDiagram — a theme-aware visual of how a clinical query flows through
 * Iatronix: a single query fans out to one of six strategies, searches run in
 * parallel across trusted sources, results merge into one evidence set, and the
 * answer is grounded, written and delivered.
 *
 * Styling uses ONLY the app's existing CSS-variable tokens (globals.css) so it
 * tracks the light/dark theme automatically — no hardcoded chrome colours.
 */

const QUERY_TYPES = [
  {
    icon: Pill,
    name: "Drug",
    plain: "One medicine",
    tech: "Mechanism, dosing, interactions",
  },
  {
    icon: Stethoscope,
    name: "Disease",
    plain: "One condition or symptom",
    tech: "Diagnosis, staging, management",
  },
  {
    icon: Syringe,
    name: "Procedure",
    plain: "How to perform a technique",
    tech: "Step-by-step technique",
  },
  {
    icon: FlaskConical,
    name: "Evidence",
    plain: "Does a treatment work here?",
    tech: "Includes clinical trials",
  },
  {
    icon: GitCompare,
    name: "Comparative",
    plain: "Drug A vs drug B",
    tech: "Head-to-head comparison",
  },
  {
    icon: Layers,
    name: "Complex",
    plain: "Multiple conditions",
    tech: "Comorbidities — catch-all default",
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
  return (
    <div style={wrap}>
      {/* 1 — Ask */}
      <FlowNode
        num={1}
        icon={<MessageSquare size={18} />}
        title="A clinician asks a question"
        plain="Type it in plain language — no special syntax needed."
        tech="Free-text clinical query."
      />

      <Connector />

      {/* 2 — Understand */}
      <FlowNode
        num={2}
        icon={<Brain size={18} />}
        title="Understand the question"
        plain="The app works out what you are really asking and pulls out the key medical terms."
        tech="Classify into one of 6 types, extract key terms, and rewrite neutrally to strip leading phrasing."
      />

      <Connector />

      {/* Scope guard — a decision off stage 2 */}
      <ScopeGuard />

      <Connector label="clinical question — one path splits into six" icon={<GitBranch size={13} />} />

      {/* 3 + 4 — Branch out (fan) and Fetch in parallel */}
      <div style={branchPanel}>
        <div style={accentStrip} aria-hidden />

        <PanelHeader
          num={3}
          icon={<GitBranch size={16} />}
          title="Branch by type"
          text="One of six strategies is chosen. Each decides which trusted sources to search."
        />

        <div style={typeGrid}>
          {QUERY_TYPES.map((t) => {
            const Icon = t.icon;
            return (
              <div key={t.name} style={typeCard}>
                <div style={typeIconBadge}>
                  <Icon size={15} />
                </div>
                <div>
                  <p style={typeName}>{t.name}</p>
                  <p style={typePlain}>{t.plain}</p>
                  <p style={typeTech}>{t.tech}</p>
                </div>
              </div>
            );
          })}
        </div>

        <div style={fanCaption}>
          <ChevronDown size={13} style={{ flexShrink: 0 }} />
          <span>All of that branch&rsquo;s searches fire at the same time</span>
        </div>

        <PanelHeader
          num={4}
          icon={<Database size={16} />}
          title="Fetch — in parallel"
          text="Every search in the branch runs at once across trusted medical sources, then results come back in one batch."
        />

        <div style={sourceRow}>
          {SOURCES.map((s) => (
            <span key={s} style={sourcePill}>
              {s}
            </span>
          ))}
        </div>
      </div>

      <Connector label="six result sets converge into one" icon={<GitMerge size={13} />} />

      {/* 5 — Merge */}
      <FlowNode
        num={5}
        icon={<GitMerge size={18} />}
        title="Merge into one evidence set"
        plain="Everything found is pooled together into a single body of evidence."
        tech="All retrieved results combined into one evidence set."
      />

      <Connector />

      {/* 6 — Confidence gate */}
      <FlowNode
        num={6}
        icon={<Gauge size={18} />}
        title="Check if it's enough"
        plain="If the evidence looks thin, the app tries harder before answering — or honestly says the evidence isn't strong."
        tech="Confidence gate. If weak, escalate: reword the search → borrow a complementary strategy → chase citations → broad safety-net search, else report no strong evidence."
      />

      <Connector />

      {/* 7 — Ground */}
      <FlowNode
        num={7}
        icon={<Link2 size={18} />}
        title="Ground every claim"
        plain="Each fact is tied to a real, cited article. Anything that can't be backed up is flagged, never stated as fact."
        tech="Per-claim citation binding; unbackable claims marked low-confidence."
      />

      <Connector />

      {/* 8 — Write */}
      <FlowNode
        num={8}
        icon={<PenLine size={18} />}
        title="Write the answer"
        plain="The bottom line comes first, then each section is written and streamed to you live."
        tech="Bottom-line-up-front, then per-section parallel generation, streamed."
      />

      <Connector />

      {/* 9 — Deliver */}
      <FlowNode
        num={9}
        icon={<FileCheck size={18} />}
        title="Deliver"
        plain="You get a clear, structured answer with confidence badges and links to the real sources."
        tech="Structured, cited answer with confidence badges and source links."
        terminal
      />
    </div>
  );
}

/* ── Sub-components ──────────────────────────────────────────────────────── */

function FlowNode({
  num,
  icon,
  title,
  plain,
  tech,
  terminal,
}: {
  num: number;
  icon: ReactNode;
  title: string;
  plain: string;
  tech: string;
  terminal?: boolean;
}) {
  return (
    <div style={{ ...nodeCard, ...(terminal ? terminalCard : null) }}>
      <div style={numBadge}>{num}</div>
      <div style={nodeIcon}>{icon}</div>
      <div style={{ minWidth: 0 }}>
        <p style={nodeTitle}>{title}</p>
        <p style={nodePlain}>{plain}</p>
        <p style={nodeTech}>{tech}</p>
      </div>
    </div>
  );
}

function PanelHeader({
  num,
  icon,
  title,
  text,
}: {
  num: number;
  icon: ReactNode;
  title: string;
  text: string;
}) {
  return (
    <div style={panelHeaderRow}>
      <div style={panelNumBadge}>{num}</div>
      <div style={panelIcon}>{icon}</div>
      <div style={{ minWidth: 0 }}>
        <p style={panelTitle}>{title}</p>
        <p style={panelText}>{text}</p>
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
        <ChevronDown size={16} style={{ color: "var(--text-muted)" }} />
      )}
      <span style={connectorLine} />
    </div>
  );
}

function ScopeGuard() {
  return (
    <div style={guardWrap}>
      <div style={guardHeader}>
        <ShieldCheck size={15} style={{ flexShrink: 0, color: "var(--accent)" }} />
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
              <SearchX size={15} />
            </div>
            <div style={{ minWidth: 0 }}>
              <p style={declineTitle}>Not a clinical question</p>
              <p style={declinePlain}>
                No drug, disease, symptom or procedure is found, so the app declines
                politely and does <strong>not</strong> search the medical literature.
              </p>
              <p style={declineTech}>
                non-medical guard · no medical entities extracted &rarr; out_of_scope
              </p>
            </div>
          </div>
        </div>

        {/* Yes — continue to the six-type branch */}
        <div style={continueCard}>
          <span style={continueTag}>Yes</span>
          <div style={{ minWidth: 0 }}>
            <p style={continueTitle}>A clinical question</p>
            <p style={continuePlain}>
              A medical entity is detected, so the query flows on to the six strategies
              below.
            </p>
          </div>
          <ChevronDown size={16} style={{ color: "var(--accent)", alignSelf: "center" }} />
        </div>
      </div>
    </div>
  );
}

/* ── Styles (tokens only) ───────────────────────────────────────────────── */

const wrap: CSSProperties = {
  display: "flex",
  flexDirection: "column",
  alignItems: "stretch",
};

const nodeCard: CSSProperties = {
  position: "relative",
  display: "flex",
  gap: "0.85rem",
  alignItems: "flex-start",
  padding: "0.9rem 1rem 0.9rem 1.1rem",
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
  top: -9,
  left: -9,
  width: 22,
  height: 22,
  borderRadius: "50%",
  background: "var(--accent)",
  color: "#fff",
  fontSize: "0.72rem",
  fontWeight: 700,
  display: "flex",
  alignItems: "center",
  justifyContent: "center",
  boxShadow: "var(--shadow-sm)",
};

const nodeIcon: CSSProperties = {
  flexShrink: 0,
  width: 34,
  height: 34,
  borderRadius: "var(--radius-md)",
  background: "var(--accent-glow)",
  color: "var(--accent)",
  display: "flex",
  alignItems: "center",
  justifyContent: "center",
};

const nodeTitle: CSSProperties = {
  margin: "0 0 0.15rem",
  fontWeight: 600,
  fontSize: "0.92rem",
  color: "var(--text-primary)",
};

const nodePlain: CSSProperties = {
  margin: 0,
  fontSize: "0.83rem",
  color: "var(--text-secondary)",
  lineHeight: 1.55,
};

const nodeTech: CSSProperties = {
  margin: "0.3rem 0 0",
  fontSize: "0.75rem",
  color: "var(--text-muted)",
  lineHeight: 1.5,
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
  gap: "0.35rem",
  fontSize: "0.72rem",
  fontWeight: 500,
  color: "var(--accent)",
  background: "var(--accent-glow)",
  border: "1px solid var(--border-focus)",
  borderRadius: 999,
  padding: "3px 10px",
  textAlign: "center",
};

const branchPanel: CSSProperties = {
  position: "relative",
  overflow: "hidden",
  padding: "1.1rem 1rem 1.15rem",
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
  width: 20,
  height: 20,
  borderRadius: "50%",
  background: "var(--accent)",
  color: "#fff",
  fontSize: "0.7rem",
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
  margin: "0 0 0.1rem",
  fontWeight: 700,
  fontSize: "0.88rem",
  color: "var(--text-primary)",
};

const panelText: CSSProperties = {
  margin: 0,
  fontSize: "0.8rem",
  color: "var(--text-secondary)",
  lineHeight: 1.5,
};

const typeGrid: CSSProperties = {
  display: "grid",
  gridTemplateColumns: "repeat(auto-fit, minmax(155px, 1fr))",
  gap: "0.5rem",
  margin: "0.85rem 0 0.4rem",
};

const typeCard: CSSProperties = {
  display: "flex",
  gap: "0.55rem",
  alignItems: "flex-start",
  padding: "0.6rem 0.7rem",
  background: "var(--bg-surface)",
  border: "1px solid var(--border)",
  borderRadius: "var(--radius-md)",
};

const typeIconBadge: CSSProperties = {
  flexShrink: 0,
  width: 28,
  height: 28,
  borderRadius: "var(--radius-sm)",
  background: "var(--accent-glow)",
  color: "var(--accent)",
  display: "flex",
  alignItems: "center",
  justifyContent: "center",
};

const typeName: CSSProperties = {
  margin: "0 0 0.1rem",
  fontWeight: 600,
  fontSize: "0.82rem",
  color: "var(--text-primary)",
};

const typePlain: CSSProperties = {
  margin: 0,
  fontSize: "0.75rem",
  color: "var(--text-secondary)",
  lineHeight: 1.4,
};

const typeTech: CSSProperties = {
  margin: "0.2rem 0 0",
  fontSize: "0.68rem",
  color: "var(--text-muted)",
  lineHeight: 1.4,
  fontFamily: "var(--font-mono)",
};

const fanCaption: CSSProperties = {
  display: "flex",
  alignItems: "center",
  justifyContent: "center",
  gap: "0.35rem",
  margin: "0.55rem 0 0.9rem",
  fontSize: "0.74rem",
  fontWeight: 500,
  color: "var(--text-muted)",
  textAlign: "center",
};

const sourceRow: CSSProperties = {
  display: "flex",
  flexWrap: "wrap",
  gap: "0.4rem",
  marginTop: "0.7rem",
};

const sourcePill: CSSProperties = {
  fontSize: "0.72rem",
  fontWeight: 500,
  color: "var(--text-secondary)",
  background: "var(--bg-hover)",
  border: "1px solid var(--border)",
  borderRadius: 999,
  padding: "3px 10px",
  fontFamily: "var(--font-mono)",
};

/* Scope guard */
const guardWrap: CSSProperties = {
  padding: "0.9rem 1rem 1rem",
  background: "var(--bg-elevated)",
  border: "1px solid var(--border)",
  borderRadius: "var(--radius-lg)",
  boxShadow: "var(--shadow-sm)",
};

const guardHeader: CSSProperties = {
  display: "flex",
  alignItems: "center",
  gap: "0.45rem",
  fontSize: "0.82rem",
  color: "var(--text-secondary)",
  lineHeight: 1.45,
};

const guardFork: CSSProperties = {
  display: "grid",
  gridTemplateColumns: "repeat(auto-fit, minmax(230px, 1fr))",
  gap: "0.6rem",
  marginTop: "0.75rem",
};

const declineCard: CSSProperties = {
  position: "relative",
  padding: "0.7rem 0.8rem",
  background: "var(--bg-surface)",
  border: "1px dashed var(--border)",
  borderRadius: "var(--radius-md)",
  opacity: 0.9,
};

const declineTag: CSSProperties = {
  display: "inline-block",
  marginBottom: "0.45rem",
  fontSize: "0.66rem",
  fontWeight: 700,
  letterSpacing: "0.06em",
  textTransform: "uppercase",
  color: "var(--text-muted)",
  background: "var(--bg-hover)",
  border: "1px solid var(--border)",
  borderRadius: 999,
  padding: "1px 8px",
};

const declineBody: CSSProperties = {
  display: "flex",
  gap: "0.55rem",
  alignItems: "flex-start",
};

const declineIcon: CSSProperties = {
  flexShrink: 0,
  width: 28,
  height: 28,
  borderRadius: "var(--radius-sm)",
  background: "var(--bg-hover)",
  color: "var(--text-muted)",
  display: "flex",
  alignItems: "center",
  justifyContent: "center",
};

const declineTitle: CSSProperties = {
  margin: "0 0 0.15rem",
  fontWeight: 600,
  fontSize: "0.82rem",
  color: "var(--text-secondary)",
};

const declinePlain: CSSProperties = {
  margin: 0,
  fontSize: "0.76rem",
  color: "var(--text-muted)",
  lineHeight: 1.45,
};

const declineTech: CSSProperties = {
  margin: "0.3rem 0 0",
  fontSize: "0.68rem",
  color: "var(--text-muted)",
  lineHeight: 1.4,
  fontFamily: "var(--font-mono)",
};

const continueCard: CSSProperties = {
  position: "relative",
  display: "flex",
  gap: "0.5rem",
  alignItems: "flex-start",
  padding: "0.7rem 0.8rem",
  background: "var(--accent-glow)",
  border: "1px solid var(--border-focus)",
  borderRadius: "var(--radius-md)",
};

const continueTag: CSSProperties = {
  flexShrink: 0,
  alignSelf: "flex-start",
  fontSize: "0.66rem",
  fontWeight: 700,
  letterSpacing: "0.06em",
  textTransform: "uppercase",
  color: "var(--accent)",
  background: "var(--bg-surface)",
  border: "1px solid var(--border-focus)",
  borderRadius: 999,
  padding: "1px 8px",
};

const continueTitle: CSSProperties = {
  margin: "0 0 0.15rem",
  fontWeight: 600,
  fontSize: "0.82rem",
  color: "var(--text-primary)",
};

const continuePlain: CSSProperties = {
  margin: 0,
  fontSize: "0.76rem",
  color: "var(--text-secondary)",
  lineHeight: 1.45,
};
