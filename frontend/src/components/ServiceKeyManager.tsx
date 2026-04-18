"use client";
import React, { useState, useEffect, useCallback } from "react";
import { listServiceKeys, saveServiceKey, deleteServiceKey } from "@/lib/api";
import type { ServiceKeyInfo } from "@/lib/api";

const SERVICES = [
  { name: "ncbi", label: "NCBI (Entrez API key)" },
  { name: "europe_pmc", label: "Europe PMC API key" },
  { name: "openfda", label: "OpenFDA API key" },
  { name: "openai", label: "OpenAI API key" },
  { name: "gemini", label: "Google Gemini API key" },
];

interface ServiceKeyManagerProps {
  authToken: string;
  onClose: () => void;
}

export const ServiceKeyManager: React.FC<ServiceKeyManagerProps> = ({
  authToken,
  onClose,
}) => {
  const [keys, setKeys] = useState<ServiceKeyInfo[]>([]);
  const [inputs, setInputs] = useState<Record<string, string>>({});
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      setKeys(await listServiceKeys(authToken));
    } catch {
      setError("Failed to load service keys");
    } finally {
      setLoading(false);
    }
  }, [authToken]);

  useEffect(() => { load(); }, [load]);

  const handleSave = async (serviceName: string) => {
    const val = (inputs[serviceName] || "").trim();
    if (!val) return;
    setSaving(serviceName);
    setError(null);
    try {
      await saveServiceKey(authToken, serviceName, val);
      setInputs((prev) => ({ ...prev, [serviceName]: "" }));
      await load();
    } catch {
      setError(`Failed to save ${serviceName} key`);
    } finally {
      setSaving(null);
    }
  };

  const handleDelete = async (serviceName: string) => {
    setSaving(serviceName);
    setError(null);
    try {
      await deleteServiceKey(authToken, serviceName);
      await load();
    } catch {
      setError(`Failed to delete ${serviceName} key`);
    } finally {
      setSaving(null);
    }
  };

  const isSet = (name: string) => keys.some((k) => k.service_name === name);

  return (
    <div
      style={{
        position: "fixed",
        inset: 0,
        background: "rgba(0,0,0,0.5)",
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        zIndex: 1000,
      }}
      onClick={(e) => e.target === e.currentTarget && onClose()}
    >
      <div
        style={{
          background: "#1e1e2e",
          borderRadius: 12,
          padding: "1.5rem",
          width: "min(480px, 95vw)",
          color: "#e2e8f0",
        }}
      >
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "1rem" }}>
          <h2 style={{ margin: 0, fontSize: "1.1rem" }}>Service API Keys</h2>
          <button onClick={onClose} style={{ background: "none", border: "none", color: "#94a3b8", cursor: "pointer", fontSize: "1.2rem" }}>✕</button>
        </div>
        {error && <p style={{ color: "#f87171", fontSize: "0.85rem", marginBottom: "0.5rem" }}>{error}</p>}
        {loading ? (
          <p style={{ color: "#94a3b8" }}>Loading…</p>
        ) : (
          <ul style={{ listStyle: "none", padding: 0, margin: 0 }}>
            {SERVICES.map((svc) => (
              <li key={svc.name} style={{ marginBottom: "1rem" }}>
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "0.25rem" }}>
                  <span style={{ fontSize: "0.9rem", fontWeight: 500 }}>{svc.label}</span>
                  {isSet(svc.name) && (
                    <span style={{ display: "flex", alignItems: "center", gap: "0.5rem" }}>
                      <span style={{ color: "#22c55e", fontSize: "0.8rem" }}>● set</span>
                      <button
                        onClick={() => handleDelete(svc.name)}
                        disabled={saving === svc.name}
                        style={{ background: "none", border: "none", color: "#f87171", cursor: "pointer", fontSize: "0.8rem" }}
                      >
                        Remove
                      </button>
                    </span>
                  )}
                </div>
                <div style={{ display: "flex", gap: "0.5rem" }}>
                  <input
                    type="password"
                    placeholder={isSet(svc.name) ? "Replace key…" : "Paste key…"}
                    value={inputs[svc.name] || ""}
                    onChange={(e) => setInputs((prev) => ({ ...prev, [svc.name]: e.target.value }))}
                    style={{
                      flex: 1,
                      background: "#2d2d3f",
                      border: "1px solid #3d3d55",
                      borderRadius: 6,
                      padding: "0.4rem 0.6rem",
                      color: "#e2e8f0",
                      fontSize: "0.85rem",
                    }}
                  />
                  <button
                    onClick={() => handleSave(svc.name)}
                    disabled={!inputs[svc.name]?.trim() || saving === svc.name}
                    style={{
                      background: "#3b82f6",
                      border: "none",
                      borderRadius: 6,
                      padding: "0.4rem 0.8rem",
                      color: "#fff",
                      cursor: "pointer",
                      fontSize: "0.85rem",
                      opacity: !inputs[svc.name]?.trim() || saving === svc.name ? 0.5 : 1,
                    }}
                  >
                    {saving === svc.name ? "…" : "Save"}
                  </button>
                </div>
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
};
