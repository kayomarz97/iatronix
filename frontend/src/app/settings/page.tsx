"use client";

import { useState, useEffect } from "react";
import { Monitor, Moon, Sun } from "lucide-react";
import { API_KEY_STORAGE_KEY } from "@/lib/constants";
import { useTheme } from "@/hooks/useTheme";

export default function SettingsPage() {
  const [llmKey, setLlmKey] = useState("");
  const [provider, setProvider] = useState<"anthropic" | "openai">("anthropic");
  const [status, setStatus] = useState<{
    provider: string;
    is_set: boolean;
  } | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [email, setEmail] = useState("");
  const [profile, setProfile] = useState<{
    full_name?: string;
    username?: string;
    position?: string;
    specialty?: string;
    institute?: string;
    country?: string;
  }>({});
  const { theme, toggle, resetToSystem } = useTheme();
  const [themeMode, setThemeMode] = useState<"system" | "dark" | "light">(
    typeof window !== "undefined" && localStorage.getItem("theme")
      ? (localStorage.getItem("theme") as "dark" | "light")
      : "system"
  );

  useEffect(() => {
    setEmail(localStorage.getItem("iatronix_email") || "");
    try {
      const stored = localStorage.getItem("iatronix_profile");
      if (stored) setProfile(JSON.parse(stored));
    } catch {}
    fetchStatus();
    fetchProfile();
  }, []);

  const getApiKey = () => localStorage.getItem(API_KEY_STORAGE_KEY) || "";

  const fetchProfile = async () => {
    const apiKey = getApiKey();
    if (!apiKey) return;
    try {
      const res = await fetch("/api/v1/auth/me", {
        headers: { "X-API-Key": apiKey },
      });
      if (res.ok) {
        const data = await res.json();
        setProfile(data);
        localStorage.setItem("iatronix_profile", JSON.stringify(data));
      }
    } catch {}
  };

  const applyThemeMode = (mode: "system" | "dark" | "light") => {
    setThemeMode(mode);
    if (mode === "system") {
      resetToSystem();
    } else {
      if (mode !== theme) toggle();
      localStorage.setItem("theme", mode);
      document.documentElement.dataset.theme = mode;
    }
  };

  const fetchStatus = async () => {
    const apiKey = getApiKey();
    if (!apiKey) return;

    try {
      const res = await fetch("/api/v1/auth/llm-key", {
        headers: { "X-API-Key": apiKey },
      });
      if (res.ok) {
        setStatus(await res.json());
      }
    } catch {
      // ignore
    }
  };

  const saveLLMKey = async () => {
    setLoading(true);
    setMessage(null);

    try {
      const res = await fetch("/api/v1/auth/llm-key", {
        method: "PUT",
        headers: {
          "Content-Type": "application/json",
          "X-API-Key": getApiKey(),
        },
        body: JSON.stringify({ key: llmKey, provider }),
      });

      const data = await res.json();
      if (!res.ok) {
        setMessage(data.detail || "Failed to save key");
      } else {
        setMessage("LLM key saved successfully");
        setLlmKey("");
        fetchStatus();
      }
    } catch {
      setMessage("Network error");
    } finally {
      setLoading(false);
    }
  };

  const removeLLMKey = async () => {
    setLoading(true);
    setMessage(null);

    try {
      const res = await fetch("/api/v1/auth/llm-key", {
        method: "DELETE",
        headers: { "X-API-Key": getApiKey() },
      });

      if (res.ok) {
        setMessage("LLM key removed");
        fetchStatus();
      }
    } catch {
      setMessage("Network error");
    } finally {
      setLoading(false);
    }
  };

  const logout = () => {
    localStorage.removeItem(API_KEY_STORAGE_KEY);
    localStorage.removeItem("iatronix_email");
    window.location.href = "/login";
  };

  return (
    <div className="max-w-lg mx-auto pt-8 space-y-8">
      <h1 className="text-3xl font-bold">Settings</h1>

      {/* Account Info */}
      <section className="space-y-3">
        <h2 className="text-lg font-semibold">Account</h2>
        <div
          style={{
            padding: "1rem",
            background: "var(--bg-elevated)",
            border: "1px solid var(--border)",
            borderRadius: "var(--radius-md)",
          }}
        >
          {(profile.full_name || profile.username) && (
            <p className="font-medium" style={{ color: "var(--text-primary)", marginBottom: "0.25rem" }}>
              {profile.full_name || profile.username}
            </p>
          )}
          {email && (
            <p className="text-sm" style={{ color: "var(--text-secondary)" }}>{email}</p>
          )}
          {(profile.position || profile.specialty) && (
            <p className="text-sm mt-1" style={{ color: "var(--text-muted)" }}>
              {[profile.position, profile.specialty].filter(Boolean).join(" · ")}
            </p>
          )}
          {(profile.institute || profile.country) && (
            <p className="text-sm" style={{ color: "var(--text-muted)" }}>
              {[profile.institute, profile.country].filter(Boolean).join(", ")}
            </p>
          )}
        </div>
        <button
          onClick={logout}
          className="px-4 py-2 text-sm rounded-md border border-danger text-danger hover:bg-danger-bg min-h-[44px]"
        >
          Sign Out
        </button>
      </section>

      {/* Appearance */}
      <section className="space-y-3">
        <h2 className="text-lg font-semibold">Appearance</h2>
        <p className="text-sm" style={{ color: "var(--text-secondary)" }}>
          Choose how Iatronix looks. System setting follows your OS preference.
        </p>
        <div style={{ display: "flex", gap: "0.5rem" }}>
          {(["system", "light", "dark"] as const).map((mode) => {
            const icons = { system: Monitor, light: Sun, dark: Moon };
            const Icon = icons[mode];
            const labels = { system: "System", light: "Light", dark: "Dark" };
            const active = themeMode === mode;
            return (
              <button
                key={mode}
                onClick={() => applyThemeMode(mode)}
                style={{
                  flex: 1,
                  padding: "10px 8px",
                  display: "flex",
                  flexDirection: "column",
                  alignItems: "center",
                  gap: "0.4rem",
                  background: active ? "var(--accent-glow)" : "var(--bg-elevated)",
                  border: `1px solid ${active ? "var(--accent)" : "var(--border)"}`,
                  borderRadius: "var(--radius-md)",
                  cursor: "pointer",
                  fontSize: "0.8rem",
                  fontWeight: active ? 600 : 400,
                  color: active ? "var(--accent)" : "var(--text-secondary)",
                  transition: "all var(--transition)",
                }}
              >
                <Icon size={16} />
                {labels[mode]}
              </button>
            );
          })}
        </div>
      </section>

      {/* LLM Key */}
      <section className="space-y-3">
        <h2 className="text-lg font-semibold">LLM API Key (BYOK)</h2>
        <p className="text-sm text-text-secondary">
          Bring your own Claude or OpenAI API key. Your key is encrypted and
          stored securely.
        </p>

        {status && (
          <div className="p-3 rounded-md bg-surface-alt border border-border text-sm">
            <span className="font-medium">Current:</span>{" "}
            {status.is_set ? (
              <span className="text-success">
                {status.provider} key is set
              </span>
            ) : (
              <span className="text-text-muted">No key set (using server default)</span>
            )}
          </div>
        )}

        <div className="space-y-2">
          <select
            value={provider}
            onChange={(e) =>
              setProvider(e.target.value as "anthropic" | "openai")
            }
            className="w-full px-3 py-2 rounded-md border border-border bg-surface text-sm min-h-[44px]"
          >
            <option value="anthropic">Anthropic (Claude)</option>
            <option value="openai">OpenAI (GPT)</option>
          </select>

          <input
            type="password"
            value={llmKey}
            onChange={(e) => setLlmKey(e.target.value)}
            placeholder={
              provider === "anthropic"
                ? "sk-ant-api03-..."
                : "sk-..."
            }
            className="w-full px-3 py-2 rounded-md border border-border bg-surface text-sm min-h-[44px]"
          />

          <div className="flex gap-2">
            <button
              onClick={saveLLMKey}
              disabled={loading || !llmKey}
              className="px-4 py-2 bg-primary text-white rounded-md text-sm min-h-[44px] disabled:opacity-50"
            >
              {loading ? "Saving..." : "Save Key"}
            </button>
            {status?.is_set && (
              <button
                onClick={removeLLMKey}
                disabled={loading}
                className="px-4 py-2 rounded-md border border-border text-sm hover:bg-surface-hover min-h-[44px]"
              >
                Remove Key
              </button>
            )}
          </div>
        </div>

        {message && (
          <p className="text-sm text-text-secondary">{message}</p>
        )}
      </section>
    </div>
  );
}
