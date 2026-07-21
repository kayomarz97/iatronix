"use client";

import { useState } from "react";
import { PasswordInput } from "@/components/ui/PasswordInput";
import { startGoogleSignIn, linkGoogleToPassword, type MergePrompt } from "@/lib/authGoogle";

// Multicolour Google "G" (lucide has no brand marks).
function GoogleIcon() {
  return (
    <svg width="18" height="18" viewBox="0 0 48 48" aria-hidden focusable="false">
      <path fill="#EA4335" d="M24 9.5c3.54 0 6.71 1.22 9.21 3.6l6.85-6.85C35.9 2.38 30.47 0 24 0 14.62 0 6.51 5.38 2.56 13.22l7.98 6.19C12.43 13.72 17.74 9.5 24 9.5z" />
      <path fill="#4285F4" d="M46.98 24.55c0-1.57-.15-3.09-.38-4.55H24v9.02h12.94c-.58 2.96-2.26 5.48-4.78 7.18l7.73 6c4.51-4.18 7.09-10.36 7.09-17.65z" />
      <path fill="#FBBC05" d="M10.53 28.59c-.48-1.45-.76-2.99-.76-4.59s.27-3.14.76-4.59l-7.98-6.19C.92 16.46 0 20.12 0 24c0 3.88.92 7.54 2.56 10.78l7.97-6.19z" />
      <path fill="#34A853" d="M24 48c6.48 0 11.93-2.13 15.89-5.81l-7.73-6c-2.15 1.45-4.92 2.3-8.16 2.3-6.26 0-11.57-4.22-13.47-9.91l-7.98 6.19C6.51 42.62 14.62 48 24 48z" />
    </svg>
  );
}

const boxErr: React.CSSProperties = {
  marginBottom: "1rem", padding: "0.75rem 1rem", background: "rgba(239,68,68,0.1)",
  border: "1px solid rgba(239,68,68,0.3)", borderRadius: "var(--radius-md)",
  fontSize: "0.875rem", color: "var(--danger)",
};

export function GoogleSignIn({ rememberMe = false }: { rememberMe?: boolean }) {
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [merge, setMerge] = useState<MergePrompt | null>(null);
  const [password, setPassword] = useState("");

  async function handleGoogle() {
    setError(null);
    setLoading(true);
    try {
      const prompt = await startGoogleSignIn(rememberMe); // null => redirecting
      if (prompt) setMerge(prompt);
    } catch (err: any) {
      if (err?.code === "auth/popup-closed-by-user" || err?.code === "auth/cancelled-popup-request") {
        // user dismissed the popup — not an error worth showing
      } else {
        setError(err?.message || "Google sign-in failed");
      }
    } finally {
      setLoading(false);
    }
  }

  async function handleLink(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setLoading(true);
    try {
      await linkGoogleToPassword(merge!.email, password, merge!.pendingCred);
    } catch (err: any) {
      setError(
        err?.code === "auth/wrong-password" || err?.code === "auth/invalid-credential"
          ? "That password doesn't match this email. Try again."
          : err?.message || "Could not link the accounts",
      );
    } finally {
      setLoading(false);
    }
  }

  if (merge) {
    return (
      <div>
        {error && <div style={boxErr}>{error}</div>}
        <div
          style={{
            marginBottom: "1rem", padding: "0.75rem 1rem", background: "var(--accent-glow)",
            border: "1px solid rgba(59,130,246,0.3)", borderRadius: "var(--radius-md)",
            fontSize: "0.85rem", color: "var(--text-secondary)",
          }}
        >
          <strong style={{ color: "var(--text-primary)" }}>{merge.email}</strong> already has a
          password account. Enter your existing password once to link Google to it — same account, no duplicates.
        </div>
        <form onSubmit={handleLink} style={{ display: "flex", flexDirection: "column", gap: "0.75rem" }}>
          <PasswordInput
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            required
            placeholder="Your existing password"
            style={{ background: "var(--bg-elevated)" }}
          />
          <button
            type="submit"
            disabled={loading}
            style={{
              width: "100%", padding: "11px", background: loading ? "var(--bg-elevated)" : "var(--accent)",
              border: "none", borderRadius: "var(--radius-md)", color: loading ? "var(--text-muted)" : "#fff",
              fontSize: "0.95rem", fontWeight: 600, cursor: loading ? "not-allowed" : "pointer",
            }}
          >
            {loading ? "Linking..." : "Link & sign in"}
          </button>
          <button
            type="button"
            onClick={() => { setMerge(null); setPassword(""); setError(null); }}
            style={{ background: "none", border: "none", color: "var(--text-muted)", fontSize: "0.8rem", cursor: "pointer" }}
          >
            Cancel
          </button>
        </form>
      </div>
    );
  }

  return (
    <div>
      {error && <div style={boxErr}>{error}</div>}
      <button
        type="button"
        onClick={handleGoogle}
        disabled={loading}
        style={{
          width: "100%", padding: "10px", display: "flex", alignItems: "center", justifyContent: "center",
          gap: "0.6rem", background: "var(--bg-elevated)", border: "1px solid var(--border)",
          borderRadius: "var(--radius-md)", color: "var(--text-primary)", fontSize: "0.95rem",
          fontWeight: 500, cursor: loading ? "not-allowed" : "pointer",
          transition: "border-color var(--transition)",
        }}
      >
        <GoogleIcon />
        {loading ? "Please wait..." : "Continue with Google"}
      </button>
    </div>
  );
}
