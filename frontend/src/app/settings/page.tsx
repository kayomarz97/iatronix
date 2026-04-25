"use client";

import { useState, useEffect } from "react";
import { Monitor, Moon, Sun, Edit2, Check, X } from "lucide-react";
import { API_KEY_STORAGE_KEY, LLM_PROVIDER_STORAGE_KEY } from "@/lib/constants";
import { useTheme } from "@/hooks/useTheme";
import { saveServiceKey, deleteServiceKey, listServiceKeys } from "@/lib/api";
// Voyage AI hidden — reserved for future re-enable

const POSITIONS = [
  "Medical Student", "Intern", "Junior Resident", "Senior Resident",
  "Fellow", "Consultant/Attending", "Researcher", "Nursing Staff",
  "Pharmacist", "Allied Health Professional", "Other",
];

const GENDERS = ["Male", "Female", "Non-binary", "Prefer not to say", "Other"];

export default function SettingsPage() {
  const [llmKey, setLlmKey] = useState("");
  const [provider, setProvider] = useState<"anthropic">("anthropic");
  const [llmStatus, setLlmStatus] = useState<{ provider: string; is_set: boolean } | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [email, setEmail] = useState("");

  const [ncbiKey, setNcbiKey] = useState("");
  const [ncbiStatus, setNcbiStatus] = useState<{ is_set: boolean } | null>(null);
  const [ncbiMessage, setNcbiMessage] = useState<string | null>(null);
  const [ncbiLoading, setNcbiLoading] = useState(false);

  const [openrouterConnected, setOpenrouterConnected] = useState<boolean | null>(null);
  const [openrouterMessage, setOpenrouterMessage] = useState<string | null>(null);
  const [openrouterLoading, setOpenrouterLoading] = useState(false);
  const [enginePref, setEnginePref] = useState<"anthropic" | "openrouter">("anthropic");

  const [profile, setProfile] = useState<{
    full_name?: string;
    username?: string;
    position?: string;
    specialty?: string;
    institute?: string;
    country?: string;
    age?: number;
    gender?: string;
    institution_type?: string;
    tier?: string;
  }>({});

  const [editing, setEditing] = useState(false);
  const [editForm, setEditForm] = useState<typeof profile>({});
  const [profileMsg, setProfileMsg] = useState<string | null>(null);

  const { theme, toggle, resetToSystem } = useTheme();
  const [themeMode, setThemeMode] = useState<"system" | "dark" | "light">(
    typeof window !== "undefined" && localStorage.getItem("theme")
      ? (localStorage.getItem("theme") as "dark" | "light")
      : "system"
  );

  useEffect(() => {
    setEmail(localStorage.getItem("iatronix_email") || "");
    const savedEngine = localStorage.getItem("iatronix_engine_pref") as "anthropic" | "openrouter" | null;
    if (savedEngine) setEnginePref(savedEngine);
    // Immediately show last-known OpenRouter status from profile cache (no network flash)
    try {
      const cached = localStorage.getItem("iatronix_profile");
      if (cached) {
        const p = JSON.parse(cached);
        if (typeof p.has_openrouter_key === "boolean") {
          setOpenrouterConnected(p.has_openrouter_key);
        }
      }
    } catch {}
    fetchProfile();
    fetchLlmStatus();
    fetchNcbiStatus();
  }, []);

  const getApiKey = () => localStorage.getItem(API_KEY_STORAGE_KEY) || "";
  const authHeader = () => ({ "Authorization": `Bearer ${getApiKey()}` });

  const fetchProfile = async () => {
    const apiKey = getApiKey();
    if (!apiKey) return;
    try {
      const res = await fetch("/api/v1/auth/me", { headers: authHeader() });
      if (res.ok) {
        const data = await res.json();
        setProfile(data);
        localStorage.setItem("iatronix_profile", JSON.stringify(data));
        // Sync OpenRouter status from profile (avoids a separate round-trip)
        if (typeof data.has_openrouter_key === "boolean") {
          setOpenrouterConnected(data.has_openrouter_key);
        }
        // Sync engine pref from server — server is source of truth
        if (data.preferences?.engine_pref) {
          const serverPref = data.preferences.engine_pref as "anthropic" | "openrouter";
          setEnginePref(serverPref);
          localStorage.setItem(LLM_PROVIDER_STORAGE_KEY, serverPref);
          localStorage.setItem("iatronix_engine_pref", serverPref);
        }
      }
    } catch {}
  };

  const fetchLlmStatus = async () => {
    const apiKey = getApiKey();
    if (!apiKey) return;
    try {
      const res = await fetch("/api/v1/auth/llm-key", { headers: authHeader() });
      if (res.ok) {
        const data = await res.json();
        setLlmStatus(data);
        // Do NOT write LLM_PROVIDER_STORAGE_KEY here — that would override the user's
        // engine preference (Anthropic vs OpenRouter). Engine pref is synced via fetchProfile.
      }
    } catch {}
  };

  const startEdit = () => {
    setEditForm({ ...profile });
    setEditing(true);
    setProfileMsg(null);
  };

  const cancelEdit = () => {
    setEditing(false);
    setProfileMsg(null);
  };

  const saveProfile = async () => {
    setLoading(true);
    setProfileMsg(null);
    try {
      const res = await fetch("/api/v1/auth/profile", {
        method: "PUT",
        headers: { "Content-Type": "application/json", ...authHeader() },
        body: JSON.stringify({
          full_name: editForm.full_name || null,
          username: editForm.username || null,
          position: editForm.position || null,
          specialty: editForm.specialty || null,
          institute: editForm.institute || null,
          country: editForm.country || null,
          institution_type: editForm.institution_type || null,
          age: editForm.age ? Number(editForm.age) : null,
          gender: editForm.gender || null,
        }),
      });
      if (res.ok) {
        const data = await res.json();
        setProfile(data);
        localStorage.setItem("iatronix_profile", JSON.stringify(data));
        setEditing(false);
        setProfileMsg("Profile updated");
      } else {
        const err = await res.json().catch(() => ({}));
        setProfileMsg(err.detail || "Failed to update profile");
      }
    } catch {
      setProfileMsg("Network error");
    } finally {
      setLoading(false);
    }
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

  const saveLLMKey = async () => {
    setLoading(true);
    setMessage(null);
    try {
      const res = await fetch("/api/v1/auth/llm-key", {
        method: "PUT",
        headers: { "Content-Type": "application/json", ...authHeader() },
        body: JSON.stringify({ key: llmKey, provider }),
      });
      const data = await res.json();
      if (!res.ok) {
        setMessage(data.detail || "Failed to save key");
      } else {
        setMessage("LLM key saved successfully");
        setLlmKey("");
        localStorage.setItem(LLM_PROVIDER_STORAGE_KEY, provider);
        fetchLlmStatus();
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
        headers: authHeader(),
      });
      if (res.ok) {
        setMessage("LLM key removed");
        fetchLlmStatus();
      }
    } catch {
      setMessage("Network error");
    } finally {
      setLoading(false);
    }
  };

  const fetchNcbiStatus = async () => {
    const apiKey = getApiKey();
    if (!apiKey) return;
    try {
      const keys = await listServiceKeys(apiKey);
      const ncbiKey = keys.find(k => k.service_name === "ncbi");
      setNcbiStatus({ is_set: !!ncbiKey });
    } catch {}
  };

  const saveNcbiKey = async () => {
    setNcbiLoading(true);
    setNcbiMessage(null);
    try {
      const apiKey = getApiKey();
      await saveServiceKey(apiKey, "ncbi", ncbiKey);
      setNcbiMessage("NCBI key saved successfully");
      setNcbiKey("");
      fetchNcbiStatus();
    } catch (err) {
      setNcbiMessage("Failed to save key");
    } finally {
      setNcbiLoading(false);
    }
  };

  const removeNcbiKey = async () => {
    setNcbiLoading(true);
    setNcbiMessage(null);
    try {
      const apiKey = getApiKey();
      await deleteServiceKey(apiKey, "ncbi");
      setNcbiMessage("NCBI key removed");
      fetchNcbiStatus();
    } catch {
      setNcbiMessage("Failed to remove key");
    } finally {
      setNcbiLoading(false);
    }
  };

  const disconnectOpenrouter = async () => {
    setOpenrouterLoading(true);
    setOpenrouterMessage(null);
    try {
      const res = await fetch("/api/v1/auth/openrouter/key", {
        method: "DELETE",
        headers: authHeader(),
      });
      if (res.ok) {
        setOpenrouterConnected(false);
        setOpenrouterMessage("OpenRouter disconnected");
        if (enginePref === "openrouter") {
          setEnginePref("anthropic");
          localStorage.setItem("iatronix_engine_pref", "anthropic");
        }
      } else {
        setOpenrouterMessage("Failed to disconnect");
      }
    } catch {
      setOpenrouterMessage("Network error");
    } finally {
      setOpenrouterLoading(false);
    }
  };

  const handleEngineToggle = (pref: "anthropic" | "openrouter") => {
    setEnginePref(pref);
    // Write to both keys so QueryProvider reads the correct model immediately
    localStorage.setItem("iatronix_engine_pref", pref);
    localStorage.setItem(LLM_PROVIDER_STORAGE_KEY, pref);
    fetch("/api/v1/auth/settings", {
      method: "POST",
      headers: { "Content-Type": "application/json", ...authHeader() },
      body: JSON.stringify({ preferences: { engine_pref: pref } }),
    }).catch(() => {});
  };

  const logout = () => {
    localStorage.removeItem(API_KEY_STORAGE_KEY);
    localStorage.removeItem("iatronix_email");
    window.location.href = "/login";
  };

  return (
    <div className="max-w-lg mx-auto pt-8 space-y-8">
      <h1 className="text-3xl font-bold">Settings</h1>

      {/* ── Account / Profile ── */}
      <section className="space-y-3">
        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
          <h2 className="text-lg font-semibold">Account</h2>
          {!editing && (
            <button
              onClick={startEdit}
              style={{
                display: "flex", alignItems: "center", gap: "0.35rem",
                fontSize: "0.825rem", color: "var(--accent)", background: "none",
                border: "none", cursor: "pointer", padding: "4px 8px",
                borderRadius: "var(--radius-sm)",
              }}
            >
              <Edit2 size={13} /> Edit
            </button>
          )}
        </div>

        {!editing ? (
          <div style={{ padding: "1rem", background: "var(--bg-elevated)", border: "1px solid var(--border)", borderRadius: "var(--radius-md)", display: "flex", flexDirection: "column", gap: "0.4rem" }}>
            <ProfileRow label="Name" value={profile.full_name} />
            <ProfileRow label="Username" value={profile.username ? `@${profile.username}` : undefined} />
            <ProfileRow label="Email" value={email} />
            <ProfileRow label="Age" value={profile.age?.toString()} />
            <ProfileRow label="Gender" value={profile.gender} />
            <ProfileRow label="Position" value={profile.position} />
            <ProfileRow label="Specialty" value={profile.specialty} />
            <ProfileRow label="Institution" value={profile.institute} />
            <ProfileRow label="Institution Type" value={profile.institution_type} />
            <ProfileRow label="Country" value={profile.country} />
            {profile.tier && (
              <ProfileRow label="Tier" value={profile.tier.charAt(0).toUpperCase() + profile.tier.slice(1)} />
            )}
          </div>
        ) : (
          <div style={{ padding: "1rem", background: "var(--bg-elevated)", border: "1px solid var(--border)", borderRadius: "var(--radius-md)", display: "flex", flexDirection: "column", gap: "0.75rem" }}>
            <FormField label="Full Name">
              <input style={inputStyle} value={editForm.full_name || ""} onChange={(e) => setEditForm({ ...editForm, full_name: e.target.value })} placeholder="Dr. John Smith" />
            </FormField>
            <FormField label="Username">
              <input style={inputStyle} value={editForm.username || ""} onChange={(e) => setEditForm({ ...editForm, username: e.target.value.replace(/\s/g, "") })} placeholder="drjohnsmith" />
            </FormField>
            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "0.75rem" }}>
              <FormField label="Age">
                <input style={inputStyle} type="number" min={16} max={100} value={editForm.age || ""} onChange={(e) => setEditForm({ ...editForm, age: e.target.value ? Number(e.target.value) : undefined })} placeholder="e.g. 32" />
              </FormField>
              <FormField label="Gender">
                <select style={{ ...inputStyle, appearance: "auto" as never }} value={editForm.gender || ""} onChange={(e) => setEditForm({ ...editForm, gender: e.target.value })}>
                  <option value="">Select</option>
                  {GENDERS.map((g) => <option key={g} value={g}>{g}</option>)}
                </select>
              </FormField>
            </div>
            <FormField label="Position">
              <select style={{ ...inputStyle, appearance: "auto" as never }} value={editForm.position || ""} onChange={(e) => setEditForm({ ...editForm, position: e.target.value })}>
                <option value="">Select position</option>
                {POSITIONS.map((p) => <option key={p} value={p}>{p}</option>)}
              </select>
            </FormField>
            <FormField label="Specialty">
              <input style={inputStyle} value={editForm.specialty || ""} onChange={(e) => setEditForm({ ...editForm, specialty: e.target.value })} placeholder="e.g. Cardiology" />
            </FormField>
            <FormField label="Institution">
              <input style={inputStyle} value={editForm.institute || ""} onChange={(e) => setEditForm({ ...editForm, institute: e.target.value })} placeholder="AIIMS New Delhi" />
            </FormField>
            <FormField label="Country">
              <input style={inputStyle} value={editForm.country || ""} onChange={(e) => setEditForm({ ...editForm, country: e.target.value })} placeholder="India" />
            </FormField>

            {profileMsg && (
              <p style={{ fontSize: "0.825rem", color: profileMsg.includes("updated") ? "var(--success)" : "var(--danger)" }}>{profileMsg}</p>
            )}

            <div style={{ display: "flex", gap: "0.5rem" }}>
              <button onClick={saveProfile} disabled={loading} style={{ display: "flex", alignItems: "center", gap: "0.35rem", padding: "8px 16px", background: "var(--accent)", color: "#fff", border: "none", borderRadius: "var(--radius-md)", cursor: "pointer", fontSize: "0.875rem", fontWeight: 600, opacity: loading ? 0.6 : 1 }}>
                <Check size={14} /> {loading ? "Saving…" : "Save"}
              </button>
              <button onClick={cancelEdit} style={{ display: "flex", alignItems: "center", gap: "0.35rem", padding: "8px 16px", background: "none", border: "1px solid var(--border)", borderRadius: "var(--radius-md)", cursor: "pointer", fontSize: "0.875rem", color: "var(--text-secondary)" }}>
                <X size={14} /> Cancel
              </button>
            </div>
          </div>
        )}

        {profileMsg && !editing && (
          <p style={{ fontSize: "0.825rem", color: "var(--success)" }}>{profileMsg}</p>
        )}

        <button onClick={logout} className="px-4 py-2 text-sm rounded-md border border-danger text-danger hover:bg-danger-bg min-h-[44px]">
          Sign Out
        </button>
      </section>

      {/* ── Appearance ── */}
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
                  flex: 1, padding: "10px 8px", display: "flex", flexDirection: "column",
                  alignItems: "center", gap: "0.4rem",
                  background: active ? "var(--accent-glow)" : "var(--bg-elevated)",
                  border: `1px solid ${active ? "var(--accent)" : "var(--border)"}`,
                  borderRadius: "var(--radius-md)", cursor: "pointer",
                  fontSize: "0.8rem", fontWeight: active ? 600 : 400,
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

      {/* ── LLM Key ── */}
      <section className="space-y-3">
        <h2 className="text-lg font-semibold">Anthropic API Key (BYOK)</h2>
        <p className="text-sm" style={{ color: "var(--text-secondary)" }}>
          Bring your own Anthropic (Claude) API key. Your key is encrypted and stored securely — never used server-side.
        </p>

        {llmStatus && (
          <div className="p-3 rounded-md text-sm" style={{ background: "var(--bg-elevated)", border: "1px solid var(--border)" }}>
            <span className="font-medium">Current: </span>
            {llmStatus.is_set ? (
              <span style={{ color: "var(--success)" }}>Anthropic key is active</span>
            ) : (
              <span style={{ color: "var(--danger)" }}>No key set — AI features require your own Anthropic API key</span>
            )}
          </div>
        )}

        <div className="space-y-2">
          <input
            type="password"
            value={llmKey}
            onChange={(e) => setLlmKey(e.target.value)}
            placeholder="sk-ant-..."
            className="w-full px-3 py-2 rounded-md border border-border bg-surface text-sm min-h-[44px]"
          />
          <div className="flex gap-2">
            <button onClick={saveLLMKey} disabled={loading || !llmKey} className="px-4 py-2 bg-primary text-white rounded-md text-sm min-h-[44px] disabled:opacity-50">
              {loading ? "Saving..." : "Save Key"}
            </button>
            {llmStatus?.is_set && (
              <button onClick={removeLLMKey} disabled={loading} className="px-4 py-2 rounded-md border border-border text-sm min-h-[44px]">
                Remove Key
              </button>
            )}
          </div>
        </div>
        {message && <p className="text-sm" style={{ color: message.includes("saved") || message.includes("removed") ? "var(--success)" : "var(--text-secondary)" }}>{message}</p>}
      </section>

      {/* ── OpenRouter OAuth ── */}
      <section className="space-y-3">
        <h2 className="text-lg font-semibold">OpenRouter (Gemma 4)</h2>
        <p className="text-sm" style={{ color: "var(--text-secondary)" }}>
          Connect your OpenRouter account to use Gemma 4 as the AI engine. Your credits are used directly — no server-side key stored in plaintext.
        </p>

        <div className="p-3 rounded-md text-sm" style={{ background: "var(--bg-elevated)", border: "1px solid var(--border)" }}>
          <span className="font-medium">Status: </span>
          {openrouterConnected === null ? (
            <span style={{ color: "var(--text-muted)" }}>Loading…</span>
          ) : openrouterConnected ? (
            <span style={{ color: "var(--success)" }}>Connected</span>
          ) : (
            <span style={{ color: "var(--danger)" }}>Not connected</span>
          )}
        </div>

        <div className="flex gap-2">
          {!openrouterConnected && (
            <button
              onClick={async () => {
                try {
                  const res = await fetch("/api/v1/auth/openrouter/login", {
                    method: "POST",
                    headers: authHeader(),
                  });
                  if (res.ok) {
                    const { redirect_url } = await res.json();
                    window.location.href = redirect_url;
                  } else {
                    setOpenrouterMessage("Failed to start OpenRouter login");
                  }
                } catch {
                  setOpenrouterMessage("Network error — try again");
                }
              }}
              className="px-4 py-2 bg-primary rounded-md text-sm min-h-[44px] inline-flex items-center"
              style={{ color: "white" }}
            >
              Connect OpenRouter →
            </button>
          )}
          {openrouterConnected && (
            <button
              onClick={disconnectOpenrouter}
              disabled={openrouterLoading}
              className="px-4 py-2 rounded-md border border-border text-sm min-h-[44px] disabled:opacity-50"
            >
              {openrouterLoading ? "Disconnecting…" : "Disconnect"}
            </button>
          )}
        </div>
        {openrouterMessage && (
          <p className="text-sm" style={{ color: openrouterMessage.includes("disconnected") ? "var(--success)" : "var(--danger)" }}>
            {openrouterMessage}
          </p>
        )}
      </section>

      {/* ── Engine Toggle ── */}
      <section className="space-y-3">
        <h2 className="text-lg font-semibold">Search Engine</h2>
        <p className="text-sm" style={{ color: "var(--text-secondary)" }}>
          Choose which AI model powers your medical queries.
        </p>
        <div className="flex gap-2">
          <button
            onClick={() => handleEngineToggle("anthropic")}
            className="flex-1 px-4 py-3 rounded-md border text-sm min-h-[44px]"
            style={{
              background: enginePref === "anthropic" ? "var(--primary)" : "var(--bg-elevated)",
              borderColor: enginePref === "anthropic" ? "var(--primary)" : "var(--border)",
              color: enginePref === "anthropic" ? "#fff" : "var(--text-primary)",
            }}
          >
            <div className="font-medium">Claude Haiku</div>
            <div className="text-xs opacity-70 mt-0.5">Your Anthropic key</div>
          </button>
          <button
            onClick={() => handleEngineToggle("openrouter")}
            className="flex-1 px-4 py-3 rounded-md border text-sm min-h-[44px]"
            style={{
              background: enginePref === "openrouter" ? "var(--primary)" : "var(--bg-elevated)",
              borderColor: enginePref === "openrouter" ? "var(--primary)" : "var(--border)",
              color: enginePref === "openrouter" ? "#fff" : "var(--text-primary)",
            }}
          >
            <div className="font-medium">Gemma 4</div>
            <div className="text-xs opacity-70 mt-0.5">Your OpenRouter credits</div>
          </button>
        </div>
        {enginePref === "openrouter" && !openrouterConnected && (
          <p className="text-xs" style={{ color: "var(--text-muted)" }}>
            Connect OpenRouter above to enable Gemma 4.
          </p>
        )}
      </section>

      {/* ── NCBI API Key ── */}
      <section className="space-y-3">
        <h2 className="text-lg font-semibold">PubMed API Key (NCBI)</h2>
        <p className="text-sm" style={{ color: "var(--text-secondary)" }}>
          Free NCBI API key increases PubMed retrieval speed and reliability. Increases rate limit from 3 to 10 requests/second.{" "}
          <a
            href="https://www.ncbi.nlm.nih.gov/account/"
            target="_blank"
            rel="noopener noreferrer"
            style={{ color: "var(--primary)", textDecoration: "underline" }}
          >
            Register free at NCBI
          </a>
          .
        </p>

        {ncbiStatus && (
          <div className="p-3 rounded-md text-sm" style={{ background: "var(--bg-elevated)", border: "1px solid var(--border)" }}>
            <span className="font-medium">Current: </span>
            {ncbiStatus.is_set ? (
              <span style={{ color: "var(--success)" }}>PubMed rate limit: 10 req/s (key active)</span>
            ) : (
              <span style={{ color: "var(--text-muted)" }}>PubMed rate limit: 3 req/s (no key — add a free NCBI key to improve retrieval)</span>
            )}
          </div>
        )}

        <div className="space-y-2">
          <input
            type="password"
            value={ncbiKey}
            onChange={(e) => setNcbiKey(e.target.value)}
            placeholder="Your NCBI API key"
            className="w-full px-3 py-2 rounded-md border border-border bg-surface text-sm min-h-[44px]"
          />
          <div className="flex gap-2">
            <button
              onClick={saveNcbiKey}
              disabled={ncbiLoading || !ncbiKey}
              className="px-4 py-2 bg-primary text-white rounded-md text-sm min-h-[44px] disabled:opacity-50"
            >
              {ncbiLoading ? "Saving..." : "Save Key"}
            </button>
            {ncbiStatus?.is_set && (
              <button
                onClick={removeNcbiKey}
                disabled={ncbiLoading}
                className="px-4 py-2 rounded-md border border-border text-sm min-h-[44px]"
              >
                Remove Key
              </button>
            )}
          </div>
        </div>
        {ncbiMessage && (
          <p
            className="text-sm"
            style={{
              color: ncbiMessage.includes("saved") || ncbiMessage.includes("removed")
                ? "var(--success)"
                : "var(--text-secondary)",
            }}
          >
            {ncbiMessage}
          </p>
        )}
      </section>
    </div>
  );
}

function ProfileRow({ label, value }: { label: string; value?: string }) {
  if (!value) return null;
  return (
    <div style={{ display: "flex", gap: "0.5rem", fontSize: "0.875rem" }}>
      <span style={{ color: "var(--text-muted)", minWidth: 110, flexShrink: 0 }}>{label}</span>
      <span style={{ color: "var(--text-primary)" }}>{value}</span>
    </div>
  );
}

function FormField({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div>
      <label style={{ display: "block", fontSize: "0.8rem", fontWeight: 500, color: "var(--text-secondary)", marginBottom: "0.3rem" }}>{label}</label>
      {children}
    </div>
  );
}

const inputStyle: React.CSSProperties = {
  width: "100%", padding: "8px 12px",
  background: "var(--bg-base)", border: "1px solid var(--border)",
  borderRadius: "var(--radius-md)", color: "var(--text-primary)",
  fontSize: "0.875rem", outline: "none", boxSizing: "border-box",
};
