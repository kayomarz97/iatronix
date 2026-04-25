"use client";
import React, { useEffect, useState } from "react";

type StageGroup = "classifying" | "fetching" | "generating" | "verifying";

interface PipelineStage {
  label: string;
  description: string;
  group: StageGroup;
}

const PIPELINE_STAGES: PipelineStage[] = [
  { label: "Query rewriting",     description: "Normalising clinical terminology",          group: "classifying" },
  { label: "Classification",      description: "Identifying query type and intent",          group: "classifying" },
  { label: "Cache lookup",        description: "Checking semantic cache",                    group: "classifying" },
  { label: "Parallel data fetch", description: "PubMed, FDA, guidelines, vector DB",         group: "fetching"    },
  { label: "Evidence scoring",    description: "Ranking and deduplicating sources",          group: "fetching"    },
  { label: "LLM generation",      description: "Generating structured clinical response",    group: "generating"  },
  { label: "Validation & cache",  description: "Verifying citations and caching result",     group: "verifying"   },
];

const GROUP_ORDER: StageGroup[] = ["classifying", "fetching", "generating", "verifying"];

// Sources that cycle through during the fetching phase
const FETCH_SOURCES = [
  { name: "PubMed",           detail: "35M+ biomedical articles"       },
  { name: "FDA Drug Database",detail: "approved drugs & labels"        },
  { name: "Clinical Guidelines", detail: "ACC/AHA, WHO, NICE, ESC"    },
  { name: "Vector Knowledge Base", detail: "curated medical corpus"    },
  { name: "DailyMed / RxNorm",detail: "drug interactions & dosing"     },
  { name: "ClinicalTrials.gov",detail: "active & completed trials"     },
  { name: "Semantic Scholar", detail: "AI-indexed literature"          },
  { name: "NICE Pathways",    detail: "UK clinical guidelines"         },
];

function getStageStatus(stageIdx: number, currentGroup: StageGroup): "done" | "active" | "pending" {
  const stage = PIPELINE_STAGES[stageIdx];
  const currentGroupIdx = GROUP_ORDER.indexOf(currentGroup);
  const stageGroupIdx = GROUP_ORDER.indexOf(stage.group);

  if (stageGroupIdx < currentGroupIdx) return "done";
  if (stageGroupIdx === currentGroupIdx) return "active";
  return "pending";
}

// Cycles a visible count up from 0 to max over ~tickMs intervals
function useCyclingCount(max: number, tickMs = 1100): number {
  const [count, setCount] = useState(0);
  useEffect(() => {
    setCount(0);
    if (max === 0) return;
    const id = setInterval(() => {
      setCount(prev => (prev < max ? prev + 1 : prev));
    }, tickMs);
    return () => clearInterval(id);
  }, [max, tickMs]);
  return count;
}

function FetchingDetail() {
  const visibleCount = useCyclingCount(FETCH_SOURCES.length, 900);

  return (
    <div className="mt-2 ml-8 space-y-1.5">
      {FETCH_SOURCES.slice(0, visibleCount).map((src, i) => (
        <div
          key={src.name}
          className="flex items-center gap-2 text-[11px]"
          style={{
            animation: "fadeSlideIn 0.3s ease-out both",
          }}
        >
          <span style={{ color: "#10b981", fontWeight: 700 }}>✓</span>
          <span style={{ color: "var(--text-secondary)", fontWeight: 500 }}>{src.name}</span>
          <span style={{ color: "var(--text-muted)" }}>— {src.detail}</span>
        </div>
      ))}
      {visibleCount < FETCH_SOURCES.length && (
        <div className="flex items-center gap-2 text-[11px]">
          <span
            style={{
              display: "inline-block",
              width: 7,
              height: 7,
              borderRadius: "50%",
              background: "#3b82f6",
              animation: "pulse 1s ease-in-out infinite",
            }}
          />
          <span style={{ color: "var(--text-muted)" }}>
            {FETCH_SOURCES[visibleCount]?.name}…
          </span>
        </div>
      )}
    </div>
  );
}

interface LoadingScreenProps {
  currentStep: StageGroup;
}

export const LoadingScreen: React.FC<LoadingScreenProps> = ({ currentStep }) => {
  const doneCount = PIPELINE_STAGES.filter((_, i) => getStageStatus(i, currentStep) === "done").length;
  const progress = Math.round((doneCount / PIPELINE_STAGES.length) * 100);

  return (
    <div className="mx-auto max-w-md px-4 py-6 space-y-4">
      <style>{`
        @keyframes fadeSlideIn {
          from { opacity: 0; transform: translateY(-4px); }
          to   { opacity: 1; transform: translateY(0);    }
        }
      `}</style>

      <div className="h-[3px] rounded-full overflow-hidden" style={{ background: "var(--bg-elevated)" }}>
        <div
          className="h-full rounded-full transition-all duration-500"
          style={{
            width: `${Math.max(progress, 8)}%`,
            background: "linear-gradient(90deg, var(--accent), #10b981)",
          }}
        />
      </div>

      <div className="space-y-1">
        {PIPELINE_STAGES.map((stage, i) => {
          const status = getStageStatus(i, currentStep);
          const isFetching = status === "active" && stage.group === "fetching" && stage.label === "Parallel data fetch";

          return (
            <div key={i}>
              <div
                className="flex items-center gap-3 px-3 py-2 rounded-xl transition-colors"
                style={{
                  background: status === "active" ? "var(--bg-elevated)" : "transparent",
                  opacity: status === "pending" ? 0.35 : 1,
                }}
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
                    <span
                      style={{
                        display: "inline-block",
                        width: 6,
                        height: 6,
                        borderRadius: "50%",
                        background: "#3b82f6",
                        animation: "pulse 1.2s ease-in-out infinite",
                      }}
                    />
                  ) : i + 1}
                </div>
                <div className="flex-1 min-w-0">
                  <span
                    className="text-sm"
                    style={{
                      color: status === "done" ? "#10b981" : status === "active" ? "var(--text-primary)" : "var(--text-muted)",
                      fontWeight: status === "active" ? 600 : 400,
                    }}
                  >
                    {stage.label}
                  </span>
                  {status === "active" && (
                    <p className="text-[11px] text-[var(--text-muted)] leading-tight">{stage.description}</p>
                  )}
                </div>
              </div>

              {isFetching && <FetchingDetail />}
            </div>
          );
        })}
      </div>
    </div>
  );
};
