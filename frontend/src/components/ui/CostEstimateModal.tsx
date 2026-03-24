"use client";

import { FileText, Clock, Upload, X } from "lucide-react";

export interface DocumentEstimate {
  word_count: number;
  page_count: number;
  chunk_count: number;
  file_name: string;
}

interface Props {
  estimate: DocumentEstimate;
  onConfirm: () => void;
  onCancel: () => void;
}

export function CostEstimateModal({ estimate, onConfirm, onCancel }: Props) {
  return (
    <div className="modal-backdrop" onClick={onCancel}>
      <div
        className="modal-box animate-in"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div
          style={{
            display: "flex",
            alignItems: "center",
            justifyContent: "space-between",
            padding: "1.25rem 1.5rem 0",
          }}
        >
          <h2
            style={{
              margin: 0,
              fontSize: "1.1rem",
              fontWeight: 600,
              color: "var(--text-primary)",
              display: "flex",
              alignItems: "center",
              gap: "0.5rem",
            }}
          >
            <FileText size={18} color="var(--accent)" />
            Ready to upload
          </h2>
          <button
            onClick={onCancel}
            style={{
              background: "none",
              border: "none",
              cursor: "pointer",
              color: "var(--text-muted)",
              padding: "4px",
              display: "flex",
            }}
          >
            <X size={18} />
          </button>
        </div>

        {/* Content */}
        <div style={{ padding: "1rem 1.5rem" }}>
          <p
            style={{
              fontSize: "0.875rem",
              color: "var(--text-secondary)",
              marginTop: 0,
              marginBottom: "1rem",
            }}
          >
            {estimate.file_name}
          </p>

          {/* Stats grid */}
          <div
            style={{
              display: "grid",
              gridTemplateColumns: "1fr 1fr 1fr",
              gap: "0.75rem",
              marginBottom: "1rem",
            }}
          >
            <StatBox label="Pages" value={estimate.page_count.toString()} />
            <StatBox label="Words" value={estimate.word_count.toLocaleString()} />
            <StatBox label="Chunks" value={estimate.chunk_count.toString()} />
          </div>

          {/* No tokens notice */}
          <div
            style={{
              background: "var(--bg-elevated)",
              border: "1px solid var(--border)",
              borderRadius: "var(--radius-md)",
              padding: "0.75rem 1rem",
              marginBottom: "0.75rem",
              display: "flex",
              gap: "0.625rem",
              alignItems: "flex-start",
            }}
          >
            <span style={{ fontSize: "0.875rem", color: "var(--success)", flexShrink: 0 }}>
              No AI tokens consumed for upload
            </span>
          </div>

          {/* 48h notice */}
          <div
            style={{
              background: "rgba(245, 158, 11, 0.1)",
              border: "1px solid rgba(245, 158, 11, 0.3)",
              borderRadius: "var(--radius-md)",
              padding: "0.75rem 1rem",
              display: "flex",
              gap: "0.625rem",
              alignItems: "flex-start",
            }}
          >
            <Clock size={15} color="var(--warning)" style={{ flexShrink: 0, marginTop: 1 }} />
            <p style={{ margin: 0, fontSize: "0.8rem", color: "var(--warning)", lineHeight: 1.5 }}>
              This document will be deleted in 48 hours unless it is from a verified publisher, in which case it will be added to the shared knowledge base.
            </p>
          </div>
        </div>

        {/* Actions */}
        <div
          style={{
            padding: "0 1.5rem 1.5rem",
            display: "flex",
            gap: "0.75rem",
          }}
        >
          <button
            onClick={onCancel}
            style={{
              flex: 1,
              padding: "10px",
              background: "transparent",
              border: "1px solid var(--border)",
              borderRadius: "var(--radius-md)",
              cursor: "pointer",
              fontSize: "0.9rem",
              fontWeight: 500,
              color: "var(--text-secondary)",
              transition: "all var(--transition)",
            }}
            onMouseOver={(e) => {
              (e.currentTarget as HTMLButtonElement).style.background = "var(--bg-hover)";
              (e.currentTarget as HTMLButtonElement).style.color = "var(--text-primary)";
            }}
            onMouseOut={(e) => {
              (e.currentTarget as HTMLButtonElement).style.background = "transparent";
              (e.currentTarget as HTMLButtonElement).style.color = "var(--text-secondary)";
            }}
          >
            Cancel
          </button>
          <button
            onClick={onConfirm}
            style={{
              flex: 2,
              padding: "10px",
              background: "var(--accent)",
              border: "none",
              borderRadius: "var(--radius-md)",
              cursor: "pointer",
              fontSize: "0.9rem",
              fontWeight: 500,
              color: "#fff",
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              gap: "0.5rem",
              transition: "background var(--transition), transform var(--transition)",
            }}
            onMouseOver={(e) => {
              (e.currentTarget as HTMLButtonElement).style.background = "var(--accent-hover)";
              (e.currentTarget as HTMLButtonElement).style.transform = "translateY(-1px)";
            }}
            onMouseOut={(e) => {
              (e.currentTarget as HTMLButtonElement).style.background = "var(--accent)";
              (e.currentTarget as HTMLButtonElement).style.transform = "none";
            }}
          >
            <Upload size={16} />
            Upload
          </button>
        </div>
      </div>
    </div>
  );
}

function StatBox({ label, value }: { label: string; value: string }) {
  return (
    <div
      style={{
        background: "var(--bg-elevated)",
        border: "1px solid var(--border)",
        borderRadius: "var(--radius-md)",
        padding: "0.75rem",
        textAlign: "center",
      }}
    >
      <div style={{ fontSize: "1.25rem", fontWeight: 700, color: "var(--text-primary)" }}>
        {value}
      </div>
      <div style={{ fontSize: "0.75rem", color: "var(--text-muted)", marginTop: 2 }}>
        {label}
      </div>
    </div>
  );
}
