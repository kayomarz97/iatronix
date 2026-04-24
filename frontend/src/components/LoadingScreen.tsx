"use client";
import React from "react";

type StageGroup = "classifying" | "fetching" | "generating" | "verifying";

interface PipelineStage {
  label: string;
  description: string;
  group: StageGroup;
}

const PIPELINE_STAGES: PipelineStage[] = [
  { label: "Query rewriting", description: "Normalising clinical terminology", group: "classifying" },
  { label: "Classification", description: "Identifying query type and intent", group: "classifying" },
  { label: "Cache lookup", description: "Checking semantic cache", group: "classifying" },
  { label: "Parallel data fetch", description: "PubMed, FDA, guidelines, vector DB", group: "fetching" },
  { label: "Evidence scoring", description: "Ranking and deduplicating sources", group: "fetching" },
  { label: "LLM formatting", description: "Generating structured clinical response", group: "generating" },
  { label: "Validation & cache", description: "Verifying citations and caching result", group: "verifying" },
];

const GROUP_ORDER: StageGroup[] = ["classifying", "fetching", "generating", "verifying"];

function getStageStatus(stageIdx: number, currentGroup: StageGroup): "done" | "active" | "pending" {
  const stage = PIPELINE_STAGES[stageIdx];
  const currentGroupIdx = GROUP_ORDER.indexOf(currentGroup);
  const stageGroupIdx = GROUP_ORDER.indexOf(stage.group);

  if (stageGroupIdx < currentGroupIdx) return "done";
  if (stageGroupIdx === currentGroupIdx) {
    const firstInGroup = PIPELINE_STAGES.findIndex(s => s.group === currentGroup);
    return stageIdx === firstInGroup ? "active" : "done";
  }
  return "pending";
}

interface LoadingScreenProps {
  currentStep: StageGroup;
}

export const LoadingScreen: React.FC<LoadingScreenProps> = ({ currentStep }) => {
  const doneCount = PIPELINE_STAGES.filter((_, i) => getStageStatus(i, currentStep) === "done").length;
  const progress = Math.round((doneCount / PIPELINE_STAGES.length) * 100);

  return (
    <div className="mx-auto max-w-md px-4 py-6 space-y-4">
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
          return (
            <div
              key={i}
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
          );
        })}
      </div>
    </div>
  );
};
