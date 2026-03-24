"use client";

import { useState, useEffect } from "react";
import { Clock, ChevronRight, Trash2, X } from "lucide-react";
import { useSearchHistory, type HistoryItem } from "@/hooks/useSearchHistory";

const TYPE_COLORS: Record<string, string> = {
  drug:        "#3b82f6",
  disease:     "#8b5cf6",
  comparative: "#f59e0b",
  general:     "#10b981",
  procedure:   "#06b6d4",
  evidence:    "#ec4899",
};

function timeAgo(iso: string): string {
  const diff = Date.now() - new Date(iso).getTime();
  const m = Math.floor(diff / 60000);
  if (m < 1) return "just now";
  if (m < 60) return `${m}m ago`;
  const h = Math.floor(m / 60);
  if (h < 24) return `${h}h ago`;
  return `${Math.floor(h / 24)}d ago`;
}

interface Props {
  onRerun: (query: string) => void;
  isLoggedIn: boolean;
}

export function SearchHistorySidebar({ onRerun, isLoggedIn }: Props) {
  const [expanded, setExpanded] = useState(false);
  const { history, loading, fetchHistory, clearHistory, deleteItem } =
    useSearchHistory();

  useEffect(() => {
    if (expanded && isLoggedIn) fetchHistory();
  }, [expanded, isLoggedIn, fetchHistory]);

  return (
    <>
      {/* Overlay on mobile when expanded */}
      {expanded && (
        <div
          onClick={() => setExpanded(false)}
          style={{
            position: "fixed",
            inset: 0,
            background: "rgba(0,0,0,0.4)",
            zIndex: 29,
          }}
          className="history-overlay"
        />
      )}

      {/* Sidebar container */}
      <div
        style={{
          position: "fixed",
          left: 0,
          top: "58px",
          bottom: 0,
          zIndex: 30,
          display: "flex",
        }}
      >
        {/* Expanded panel */}
        <div
          style={{
            width: expanded ? 280 : 0,
            overflow: "hidden",
            transition: "width 300ms ease-in-out",
            background: "var(--bg-surface)",
            borderRight: expanded ? "1px solid var(--border)" : "none",
            display: "flex",
            flexDirection: "column",
          }}
        >
          <div style={{ width: 280, height: "100%", display: "flex", flexDirection: "column" }}>
            {/* Header */}
            <div
              style={{
                padding: "1rem 1rem 0.75rem",
                borderBottom: "1px solid var(--border)",
                display: "flex",
                alignItems: "center",
                justifyContent: "space-between",
                flexShrink: 0,
              }}
            >
              <span
                style={{
                  fontSize: "0.875rem",
                  fontWeight: 600,
                  color: "var(--text-primary)",
                  display: "flex",
                  alignItems: "center",
                  gap: "0.5rem",
                }}
              >
                <Clock size={15} />
                Recent Searches
              </span>
              <button
                onClick={() => setExpanded(false)}
                style={{
                  background: "none",
                  border: "none",
                  cursor: "pointer",
                  color: "var(--text-muted)",
                  padding: "4px",
                  display: "flex",
                }}
              >
                <X size={16} />
              </button>
            </div>

            {/* Content */}
            <div style={{ flex: 1, overflowY: "auto", padding: "0.5rem 0" }}>
              {!isLoggedIn ? (
                <p
                  style={{
                    padding: "1rem",
                    fontSize: "0.8rem",
                    color: "var(--text-muted)",
                    textAlign: "center",
                  }}
                >
                  Sign in to see your search history
                </p>
              ) : loading ? (
                <div style={{ padding: "1rem" }}>
                  {[1, 2, 3].map((i) => (
                    <div
                      key={i}
                      className="skeleton"
                      style={{ height: 48, marginBottom: "0.5rem" }}
                    />
                  ))}
                </div>
              ) : history.length === 0 ? (
                <p
                  style={{
                    padding: "1rem",
                    fontSize: "0.8rem",
                    color: "var(--text-muted)",
                    textAlign: "center",
                  }}
                >
                  No recent searches
                </p>
              ) : (
                history.map((item) => (
                  <HistoryRow
                    key={item.id}
                    item={item}
                    onRerun={(q) => {
                      onRerun(q);
                      setExpanded(false);
                    }}
                    onDelete={deleteItem}
                  />
                ))
              )}
            </div>

            {/* Footer */}
            {isLoggedIn && history.length > 0 && (
              <div
                style={{
                  borderTop: "1px solid var(--border)",
                  padding: "0.75rem 1rem",
                  flexShrink: 0,
                }}
              >
                <button
                  onClick={clearHistory}
                  style={{
                    width: "100%",
                    padding: "6px",
                    background: "transparent",
                    border: "1px solid var(--border)",
                    borderRadius: "var(--radius-md)",
                    cursor: "pointer",
                    fontSize: "0.8rem",
                    color: "var(--text-muted)",
                    display: "flex",
                    alignItems: "center",
                    justifyContent: "center",
                    gap: "0.4rem",
                    transition: "all var(--transition)",
                  }}
                  onMouseOver={(e) => {
                    (e.currentTarget as HTMLButtonElement).style.borderColor = "var(--danger)";
                    (e.currentTarget as HTMLButtonElement).style.color = "var(--danger)";
                  }}
                  onMouseOut={(e) => {
                    (e.currentTarget as HTMLButtonElement).style.borderColor = "var(--border)";
                    (e.currentTarget as HTMLButtonElement).style.color = "var(--text-muted)";
                  }}
                >
                  <Trash2 size={13} />
                  Clear all
                </button>
              </div>
            )}
          </div>
        </div>

        {/* Trigger tab */}
        <button
          onClick={() => setExpanded(!expanded)}
          aria-label="Toggle search history"
          style={{
            width: 24,
            background: "var(--bg-surface)",
            border: "1px solid var(--border)",
            borderLeft: "none",
            cursor: "pointer",
            display: "flex",
            flexDirection: "column",
            alignItems: "center",
            justifyContent: "center",
            gap: "0.5rem",
            borderRadius: "0 var(--radius-sm) var(--radius-sm) 0",
            transition: "background var(--transition)",
            padding: "0.75rem 0",
          }}
          onMouseOver={(e) => {
            (e.currentTarget as HTMLButtonElement).style.background = "var(--bg-hover)";
          }}
          onMouseOut={(e) => {
            (e.currentTarget as HTMLButtonElement).style.background = "var(--bg-surface)";
          }}
        >
          <Clock size={13} color="var(--text-muted)" />
          <span className="history-tab-trigger">History</span>
          <ChevronRight
            size={12}
            color="var(--text-muted)"
            style={{
              transform: expanded ? "rotate(180deg)" : "rotate(0deg)",
              transition: "transform var(--transition)",
            }}
          />
        </button>
      </div>

      <style>{`
        @media (max-width: 640px) {
          .history-overlay { display: block; }
        }
      `}</style>
    </>
  );
}

function HistoryRow({
  item,
  onRerun,
  onDelete,
}: {
  item: HistoryItem;
  onRerun: (q: string) => void;
  onDelete: (id: number) => void;
}) {
  return (
    <div
      style={{
        display: "flex",
        alignItems: "center",
        gap: "0.25rem",
        padding: "0 0.5rem",
      }}
    >
      <button
        onClick={() => onRerun(item.query_text)}
        style={{
          flex: 1,
          padding: "0.5rem 0.625rem",
          background: "transparent",
          border: "none",
          cursor: "pointer",
          textAlign: "left",
          borderRadius: "var(--radius-sm)",
          transition: "background var(--transition)",
          minWidth: 0,
        }}
        onMouseOver={(e) => {
          (e.currentTarget as HTMLButtonElement).style.background = "var(--bg-hover)";
        }}
        onMouseOut={(e) => {
          (e.currentTarget as HTMLButtonElement).style.background = "transparent";
        }}
      >
        <div
          style={{
            fontSize: "0.8rem",
            color: "var(--text-primary)",
            fontWeight: 500,
            whiteSpace: "nowrap",
            overflow: "hidden",
            textOverflow: "ellipsis",
          }}
        >
          {item.query_text}
        </div>
        <div
          style={{
            display: "flex",
            alignItems: "center",
            gap: "0.4rem",
            marginTop: "2px",
          }}
        >
          {item.query_type && (
            <span
              style={{
                fontSize: "0.65rem",
                fontWeight: 600,
                padding: "1px 6px",
                borderRadius: "9999px",
                background: `${TYPE_COLORS[item.query_type] ?? "#64748b"}22`,
                color: TYPE_COLORS[item.query_type] ?? "var(--text-muted)",
                textTransform: "uppercase",
                letterSpacing: "0.04em",
              }}
            >
              {item.query_type}
            </span>
          )}
          <span style={{ fontSize: "0.7rem", color: "var(--text-muted)" }}>
            {timeAgo(item.created_at)}
          </span>
        </div>
      </button>
      <button
        onClick={() => onDelete(item.id)}
        aria-label="Remove"
        style={{
          background: "none",
          border: "none",
          cursor: "pointer",
          padding: "6px",
          color: "var(--text-muted)",
          borderRadius: "var(--radius-sm)",
          display: "flex",
          opacity: 0.5,
          transition: "opacity var(--transition), color var(--transition)",
          flexShrink: 0,
        }}
        onMouseOver={(e) => {
          (e.currentTarget as HTMLButtonElement).style.opacity = "1";
          (e.currentTarget as HTMLButtonElement).style.color = "var(--danger)";
        }}
        onMouseOut={(e) => {
          (e.currentTarget as HTMLButtonElement).style.opacity = "0.5";
          (e.currentTarget as HTMLButtonElement).style.color = "var(--text-muted)";
        }}
      >
        <X size={13} />
      </button>
    </div>
  );
}
