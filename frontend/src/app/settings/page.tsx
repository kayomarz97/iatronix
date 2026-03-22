"use client";

import { useState, useEffect } from "react";
import { API_KEY_STORAGE_KEY } from "@/lib/constants";

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

  useEffect(() => {
    setEmail(localStorage.getItem("iatronix_email") || "");
    fetchStatus();
  }, []);

  const getApiKey = () => localStorage.getItem(API_KEY_STORAGE_KEY) || "";

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
        {email && (
          <p className="text-sm text-text-secondary">Signed in as {email}</p>
        )}
        <button
          onClick={logout}
          className="px-4 py-2 text-sm rounded-md border border-danger text-danger hover:bg-danger-bg min-h-[44px]"
        >
          Sign Out
        </button>
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
