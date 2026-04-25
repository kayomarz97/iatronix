"use client";
import React, { useEffect, useRef, useState } from "react";
import type { FetchedArticle } from "@/lib/api";

type StageGroup = "classifying" | "fetching" | "generating" | "verifying";

interface PipelineStage {
  label: string;
  description: string;
  group: StageGroup;
}

const PIPELINE_STAGES: PipelineStage[] = [
  { label: "Query rewriting",     description: "Normalising clinical terminology",        group: "classifying" },
  { label: "Classification",      description: "Identifying query type and intent",        group: "classifying" },
  { label: "Cache lookup",        description: "Checking semantic cache",                  group: "classifying" },
  { label: "Parallel data fetch", description: "Querying medical databases in parallel",  group: "fetching"    },
  { label: "Evidence scoring",    description: "Ranking and deduplicating sources",        group: "fetching"    },
  { label: "LLM generation",      description: "Generating structured clinical response",  group: "generating"  },
  { label: "Validation & cache",  description: "Verifying citations and caching result",   group: "verifying"   },
];

// Real sources the backend actually queries
const REAL_SOURCES = [
  "PubMed",
  "FDA / OpenFDA",
  "MedlinePlus",
  "Semantic Scholar",
  "DailyMed",
  "PMC / StatPearls",
  "RxNorm",
  "Vector knowledge base",
];

const GROUP_ORDER: StageGroup[] = ["classifying", "fetching", "generating", "verifying"];

function getStageStatus(stageIdx: number, currentGroup: StageGroup): "done" | "active" | "pending" {
  const stage = PIPELINE_STAGES[stageIdx];
  const currentGroupIdx = GROUP_ORDER.indexOf(currentGroup);
  const stageGroupIdx = GROUP_ORDER.indexOf(stage.group);
  if (stageGroupIdx < currentGroupIdx) return "done";
  if (stageGroupIdx === currentGroupIdx) return "active";
  return "pending";
}

// Ticks sources in one by one
function useCyclingCount(max: number, tickMs = 950): number {
  const [count, setCount] = useState(0);
  useEffect(() => {
    setCount(0);
    if (max === 0) return;
    const id = setInterval(() => setCount(prev => Math.min(prev + 1, max)), tickMs);
    return () => clearInterval(id);
  }, [max, tickMs]);
  return count;
}

// ── Scrolling article ticker ──────────────────────────────────────────────────
function ArticleTicker({ articles }: { articles: FetchedArticle[] }) {
  const containerRef = useRef<HTMLDivElement>(null);
  const [visible, setVisible] = useState<FetchedArticle[]>([]);
  const indexRef = useRef(0);

  // Feed articles in one at a time, keep last 6 visible, auto-scroll
  useEffect(() => {
    if (articles.length === 0) return;
    indexRef.current = 0;
    setVisible([]);

    const id = setInterval(() => {
      if (indexRef.current >= articles.length) {
        clearInterval(id);
        return;
      }
      const article = articles[indexRef.current];
      indexRef.current += 1;
      setVisible(prev => [...prev.slice(-5), article]);
    }, 600);

    return () => clearInterval(id);
  }, [articles]);

  useEffect(() => {
    if (containerRef.current) {
      containerRef.current.scrollTop = containerRef.current.scrollHeight;
    }
  }, [visible]);

  if (visible.length === 0) return null;

  return (
    <div className="mt-3 ml-8">
      <p className="text-[10px] uppercase tracking-widest font-semibold mb-1.5" style={{ color: "var(--text-muted)" }}>
        Articles retrieved
      </p>
      <div
        ref={containerRef}
        className="space-y-1.5 overflow-hidden"
        style={{ maxHeight: 180 }}
      >
        {visible.map((a, i) => (
          <div
            key={`${a.pmid}-${i}`}
            className="rounded-lg px-3 py-2 text-[11px] border"
            style={{
              background: "var(--bg-elevated)",
              borderColor: "var(--border)",
              animation: "fadeSlideIn 0.35s ease-out both",
            }}
          >
            <p className="font-medium leading-snug" style={{ color: "var(--text-primary)" }}>
              {a.title}
            </p>
            <p className="mt-0.5" style={{ color: "var(--text-muted)" }}>
              {[a.journal, a.year].filter(Boolean).join(" · ")}
              {a.pmid && (
                <span className="ml-1.5 font-mono" style={{ color: "var(--accent)" }}>
                  PMID {a.pmid}
                </span>
              )}
            </p>
          </div>
        ))}
      </div>
    </div>
  );
}

// ── Source tick-in list ───────────────────────────────────────────────────────
function FetchingDetail({ articles }: { articles: FetchedArticle[] }) {
  const visibleCount = useCyclingCount(REAL_SOURCES.length, 950);

  return (
    <div className="mt-2 ml-8 space-y-1">
      {REAL_SOURCES.slice(0, visibleCount).map(name => (
        <div key={name} className="flex items-center gap-2 text-[11px]" style={{ animation: "fadeSlideIn 0.3s ease-out both" }}>
          <span style={{ color: "#10b981", fontWeight: 700 }}>✓</span>
          <span style={{ color: "var(--text-secondary)" }}>{name}</span>
        </div>
      ))}
      {visibleCount < REAL_SOURCES.length && (
        <div className="flex items-center gap-2 text-[11px]">
          <span style={{ display: "inline-block", width: 7, height: 7, borderRadius: "50%", background: "#3b82f6", animation: "pulse 1s ease-in-out infinite" }} />
          <span style={{ color: "var(--text-muted)" }}>{REAL_SOURCES[visibleCount]}…</span>
        </div>
      )}
      <ArticleTicker articles={articles} />
    </div>
  );
}

interface LoadingScreenProps {
  currentStep: StageGroup;
  fetchedArticles?: FetchedArticle[];
}

export const LoadingScreen: React.FC<LoadingScreenProps> = ({ currentStep, fetchedArticles = [] }) => {
  const doneCount = PIPELINE_STAGES.filter((_, i) => getStageStatus(i, currentStep) === "done").length;
  const progress = Math.round((doneCount / PIPELINE_STAGES.length) * 100);

  return (
    <div className="mx-auto max-w-lg px-4 py-6 space-y-4">
      <style>{`
        @keyframes fadeSlideIn {
          from { opacity: 0; transform: translateY(-5px); }
          to   { opacity: 1; transform: translateY(0); }
        }
      `}</style>

      <div className="h-[3px] rounded-full overflow-hidden" style={{ background: "var(--bg-elevated)" }}>
        <div
          className="h-full rounded-full transition-all duration-500"
          style={{ width: `${Math.max(progress, 8)}%`, background: "linear-gradient(90deg, var(--accent), #10b981)" }}
        />
      </div>

      <div className="space-y-1">
        {PIPELINE_STAGES.map((stage, i) => {
          const status = getStageStatus(i, currentStep);
          const isFetchStep = status === "active" && stage.group === "fetching" && stage.label === "Parallel data fetch";

          return (
            <div key={i}>
              <div
                className="flex items-center gap-3 px-3 py-2 rounded-xl transition-colors"
                style={{ background: status === "active" ? "var(--bg-elevated)" : "transparent", opacity: status === "pending" ? 0.35 : 1 }}
              >
                <div
                  className="w-5 h-5 rounded-full flex items-center justify-center flex-shrink-0 text-[11px] font-bold"
                  style={
                    status === "done"
                      ? { background: "#10b981", color: "#fff" }
                      : status === "active"
                      ? { border: "2px solid #3b82f6", color: "#3b82f6" }
                      : { border: "2px solid #475569", color: "#475569" }
                  }
                >
                  {status === "done" ? "✓" : status === "active" ? (
                    <span style={{ display: "inline-block", width: 6, height: 6, borderRadius: "50%", background: "#3b82f6", animation: "pulse 1.2s ease-in-out infinite" }} />
                  ) : i + 1}
                </div>
                <div className="flex-1 min-w-0">
                  <span className="text-sm" style={{ color: status === "done" ? "#10b981" : status === "active" ? "var(--text-primary)" : "var(--text-muted)", fontWeight: status === "active" ? 600 : 400 }}>
                    {stage.label}
                  </span>
                  {status === "active" && (
                    <p className="text-[11px] leading-tight" style={{ color: "var(--text-muted)" }}>{stage.description}</p>
                  )}
                </div>
              </div>

              {isFetchStep && <FetchingDetail articles={fetchedArticles} />}
            </div>
          );
        })}
      </div>
    </div>
  );
};
