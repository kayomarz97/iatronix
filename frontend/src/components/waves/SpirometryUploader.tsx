"use client";

import { useState, useRef } from "react";
import { Upload, Camera, Loader2, Copy, Check, AlertCircle, RefreshCw, FileText } from "lucide-react";
import { API_KEY_STORAGE_KEY } from "@/lib/constants";

interface InterpRow {
  "Metric / Step": string;
  "Value / Observation": string;
  "Diagnostic Interpretation": string;
}

interface TokenUsage {
  input_tokens: number;
  output_tokens: number;
}

interface SpirometryResult {
  status: string;
  interpretation: InterpRow[];
  model_used?: string;
  token_usage?: TokenUsage;
}

export function SpirometryUploader() {
  const [files, setFiles] = useState<File[]>([]);
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<SpirometryResult | null>(null);
  const [error, setError] = useState<{ title: string; message: string } | null>(null);
  const [copied, setCopied] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const cameraInputRef = useRef<HTMLInputElement>(null);

  const isMobile = typeof navigator !== "undefined" && /iPhone|iPad|iPod|Android/i.test(navigator.userAgent);

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const selected = Array.from(e.target.files ?? []);
    setFiles((prev) => [...prev, ...selected]);
  };

  const removeFile = (i: number) => setFiles(files.filter((_, idx) => idx !== i));

  const reset = () => { setFiles([]); setResult(null); setError(null); };

  const handleUpload = async () => {
    if (files.length === 0) return;
    const authToken = localStorage.getItem(API_KEY_STORAGE_KEY);
    if (!authToken) {
      setError({ title: "Not signed in", message: "Sign in and add your Anthropic API key in Settings to use Waves." });
      return;
    }

    setLoading(true);
    setError(null);
    try {
      const formData = new FormData();
      formData.append("file", files[0]);

      const res = await fetch("/api/waves/spirometry", {
        method: "POST",
        headers: { Authorization: `Bearer ${authToken}` },
        body: formData,
      });

      const data = await res.json();
      if (!res.ok) {
        const detail = data?.detail ?? "Analysis failed";
        if (res.status === 401 || res.status === 403) {
          setError({ title: "API Key Error", message: "Your Anthropic key is missing or invalid. Add it in Settings → Anthropic API Key." });
        } else if (res.status === 422) {
          setError({ title: "Not a Spirometry Report", message: detail });
        } else {
          setError({ title: "Processing Error", message: detail });
        }
        return;
      }
      if (!data.interpretation?.length) {
        setError({ title: "No Data Found", message: "The report could not be interpreted. Upload a clear spirometry printout." });
        return;
      }
      setResult(data);
    } catch {
      setError({ title: "Network Error", message: "Could not reach the server. Check your connection and try again." });
    } finally {
      setLoading(false);
    }
  };

  const copyToClipboard = () => {
    if (!result) return;
    const text = result.interpretation
      .map((r) => `${r["Metric / Step"]}\t${r["Value / Observation"]}\t${r["Diagnostic Interpretation"]}`)
      .join("\n");
    navigator.clipboard.writeText(text);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  const cardStyle: React.CSSProperties = {
    padding: "1.25rem",
    background: "var(--bg-elevated)",
    border: "1px solid var(--border)",
    borderRadius: "var(--radius-lg)",
  };

  if (result) {
    return (
      <div style={{ display: "flex", flexDirection: "column", gap: "1rem" }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", flexWrap: "wrap", gap: "0.5rem" }}>
          <h3 style={{ margin: 0, fontSize: "1rem", fontWeight: 700, color: "var(--text-primary)" }}>
            Spirometry Interpretation
          </h3>
          <div style={{ display: "flex", gap: "0.5rem" }}>
            <button
              onClick={copyToClipboard}
              style={{ display: "flex", alignItems: "center", gap: "0.4rem", padding: "6px 12px", background: "var(--bg-elevated)", border: "1px solid var(--border)", borderRadius: "var(--radius-md)", cursor: "pointer", fontSize: "0.8rem", color: "var(--text-secondary)" }}
            >
              {copied ? <Check size={14} color="var(--success)" /> : <Copy size={14} />}
              {copied ? "Copied" : "Copy for Sheets"}
            </button>
            <button
              onClick={reset}
              style={{ padding: "6px 12px", background: "var(--bg-elevated)", border: "1px solid var(--border)", borderRadius: "var(--radius-md)", cursor: "pointer", fontSize: "0.8rem", color: "var(--text-secondary)" }}
            >
              New Analysis
            </button>
          </div>
        </div>

        <div style={{ overflowX: "auto", borderRadius: "var(--radius-md)", border: "1px solid var(--border)" }}>
          <table style={{ width: "100%", borderCollapse: "collapse", fontSize: "0.85rem" }}>
            <thead>
              <tr style={{ background: "var(--bg-surface)", borderBottom: "1px solid var(--border)" }}>
                {["Metric / Step", "Value / Observation", "Diagnostic Interpretation"].map((h) => (
                  <th key={h} style={{ padding: "0.625rem 0.875rem", textAlign: "left", fontWeight: 600, color: "var(--text-secondary)", whiteSpace: "nowrap" }}>{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {result.interpretation.map((row, i) => {
                const isFinal = row["Metric / Step"] === "FINAL DIAGNOSIS";
                return (
                  <tr
                    key={i}
                    style={{
                      borderBottom: "1px solid var(--border)",
                      background: isFinal ? "var(--accent-glow)" : i % 2 === 0 ? "var(--bg-base)" : "var(--bg-elevated)",
                    }}
                  >
                    <td style={{ padding: "0.625rem 0.875rem", fontWeight: isFinal ? 700 : 500, color: isFinal ? "var(--accent)" : "var(--text-primary)" }}>
                      {row["Metric / Step"]}
                    </td>
                    <td style={{ padding: "0.625rem 0.875rem", color: "var(--text-primary)" }}>{row["Value / Observation"]}</td>
                    <td style={{ padding: "0.625rem 0.875rem", color: isFinal ? "var(--accent)" : "var(--text-secondary)" }}>{row["Diagnostic Interpretation"]}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
        <p style={{ margin: 0, fontSize: "0.75rem", color: "var(--text-muted)" }}>
          Based on ATS/ERS spirometry guidelines. For clinical decision support only — always verify with the full report and clinical context.
        </p>
        {(result.model_used || result.token_usage) && (
          <div style={{ display: "flex", alignItems: "center", gap: "0.75rem", flexWrap: "wrap" }}>
            {result.model_used && (
              <span style={{ display: "inline-flex", alignItems: "center", gap: "0.3rem", padding: "3px 8px", background: "var(--bg-surface)", border: "1px solid var(--border)", borderRadius: "var(--radius-sm)", fontSize: "0.72rem", color: "var(--text-secondary)" }}>
                Model: {result.model_used}
              </span>
            )}
            {result.token_usage && (
              <span style={{ fontSize: "0.72rem", color: "var(--text-muted)" }}>
                {result.token_usage.input_tokens.toLocaleString()} in / {result.token_usage.output_tokens.toLocaleString()} out tokens
              </span>
            )}
          </div>
        )}
      </div>
    );
  }

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "1rem" }}>
      {error && (
        <div style={{ padding: "1rem", borderRadius: "var(--radius-md)", border: "1px solid rgba(239,68,68,0.3)", background: "rgba(239,68,68,0.06)" }}>
          <div style={{ display: "flex", gap: "0.75rem", alignItems: "flex-start" }}>
            <AlertCircle size={18} style={{ color: "var(--danger)", flexShrink: 0, marginTop: 2 }} />
            <div>
              <p style={{ margin: "0 0 0.25rem", fontWeight: 600, fontSize: "0.875rem", color: "var(--danger)" }}>{error.title}</p>
              <p style={{ margin: "0 0 0.5rem", fontSize: "0.8rem", color: "var(--text-secondary)", lineHeight: 1.6 }}>{error.message}</p>
              <button
                onClick={reset}
                style={{ display: "flex", alignItems: "center", gap: "0.4rem", padding: "4px 10px", background: "none", border: "1px solid var(--border)", borderRadius: "var(--radius-sm)", cursor: "pointer", fontSize: "0.78rem", color: "var(--text-secondary)" }}
              >
                <RefreshCw size={12} /> Try Again
              </button>
            </div>
          </div>
        </div>
      )}

      <div style={{ display: "grid", gridTemplateColumns: isMobile ? "1fr 1fr" : "1fr", gap: "0.75rem" }}>
        {/* Upload card */}
        <button
          onClick={() => fileInputRef.current?.click()}
          style={{ ...cardStyle, display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center", gap: "0.5rem", cursor: "pointer", border: "2px dashed var(--border)", background: "none", textAlign: "center", minHeight: 120 }}
        >
          <Upload size={28} color="var(--accent)" />
          <span style={{ fontWeight: 600, fontSize: "0.875rem", color: "var(--text-primary)" }}>Upload Report</span>
          <span style={{ fontSize: "0.75rem", color: "var(--text-muted)" }}>Images or PDF</span>
          <input ref={fileInputRef} type="file" accept="image/*,.pdf" multiple style={{ display: "none" }} onChange={handleFileChange} />
        </button>

        {/* Camera card (mobile only) */}
        {isMobile && (
          <button
            onClick={() => cameraInputRef.current?.click()}
            style={{ ...cardStyle, display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center", gap: "0.5rem", cursor: "pointer", border: "2px dashed var(--border)", background: "none", textAlign: "center", minHeight: 120 }}
          >
            <Camera size={28} color="var(--accent)" />
            <span style={{ fontWeight: 600, fontSize: "0.875rem", color: "var(--text-primary)" }}>Take Photo</span>
            <span style={{ fontSize: "0.75rem", color: "var(--text-muted)" }}>Device camera</span>
            <input ref={cameraInputRef} type="file" accept="image/*" capture="environment" style={{ display: "none" }} onChange={handleFileChange} />
          </button>
        )}
      </div>

      {files.length > 0 && (
        <div style={cardStyle}>
          <p style={{ margin: "0 0 0.5rem", fontSize: "0.8rem", fontWeight: 600, color: "var(--text-secondary)" }}>Selected</p>
          <div style={{ display: "flex", flexDirection: "column", gap: "0.4rem" }}>
            {files.map((f, i) => (
              <div key={i} style={{ display: "flex", justifyContent: "space-between", alignItems: "center", padding: "6px 10px", background: "var(--bg-surface)", borderRadius: "var(--radius-sm)" }}>
                <div style={{ display: "flex", alignItems: "center", gap: "0.4rem" }}>
                  <FileText size={13} color="var(--accent)" />
                  <span style={{ fontSize: "0.8rem", color: "var(--text-primary)" }}>{f.name}</span>
                </div>
                <button onClick={() => removeFile(i)} style={{ background: "none", border: "none", cursor: "pointer", fontSize: "0.75rem", color: "var(--danger)" }}>Remove</button>
              </div>
            ))}
          </div>
          <button
            onClick={handleUpload}
            disabled={loading}
            style={{
              width: "100%", marginTop: "0.75rem", padding: "10px", background: "var(--accent)", color: "#fff",
              border: "none", borderRadius: "var(--radius-md)", cursor: loading ? "not-allowed" : "pointer",
              fontSize: "0.875rem", fontWeight: 600, display: "flex", alignItems: "center", justifyContent: "center", gap: "0.5rem",
              opacity: loading ? 0.7 : 1,
            }}
          >
            {loading ? <><Loader2 size={16} className="animate-spin" /> Analysing...</> : "Analyse Report"}
          </button>
        </div>
      )}

      <p style={{ margin: 0, fontSize: "0.75rem", color: "var(--text-muted)" }}>
        Uses your Anthropic API key (set in Settings). Report is processed securely and not stored.
      </p>
    </div>
  );
}
