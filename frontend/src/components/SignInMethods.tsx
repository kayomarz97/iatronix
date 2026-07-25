"use client";

// "Sign-in methods" panel for Settings.
//
// Exists because Firebase's untrusted -> trusted rule (see lib/authGoogle.ts) can
// strip the password credential off an account that signed in with Google: the user
// keeps their uid and all their data, but email login stops working with no way back
// from inside the app. This panel is that way back — it attaches a password to the
// signed-in account, so Google AND email both work on ONE account.

import { useState } from "react";
import { AlertTriangle, Check, KeyRound, MailCheck } from "lucide-react";
import { sendEmailVerification } from "firebase/auth";
import { useAuth } from "@/components/providers/AuthProvider";
import { PasswordInput } from "@/components/ui/PasswordInput";
import { hasPasswordProvider, providerIds, linkPasswordToCurrentUser } from "@/lib/authGoogle";

const MIN_PASSWORD = 8; // matches the register flow

const cardStyle: React.CSSProperties = {
  padding: "1rem",
  background: "var(--bg-elevated)",
  border: "1px solid var(--border)",
  borderRadius: "var(--radius-md)",
  display: "flex",
  flexDirection: "column",
  gap: "0.75rem",
};

function friendlyError(err: any): string {
  switch (err?.code) {
    case "auth/weak-password":
      return `Password is too weak. Use at least ${MIN_PASSWORD} characters.`;
    case "auth/provider-already-linked":
      return "This account already has a password.";
    case "auth/credential-already-in-use":
    case "auth/email-already-in-use":
      return "That password credential is already attached to a different account.";
    case "auth/popup-closed-by-user":
    case "auth/cancelled-popup-request":
      return "Confirmation window closed before finishing. Please try again.";
    case "auth/requires-recent-login":
      return "For security, sign out and sign in again, then retry.";
    default:
      return err?.message || "Could not set the password.";
  }
}

export function SignInMethods() {
  const { user, loading } = useAuth();
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [busy, setBusy] = useState(false);
  const [justLinked, setJustLinked] = useState(false);
  const [msg, setMsg] = useState<{ ok: boolean; text: string } | null>(null);
  const [verifyMsg, setVerifyMsg] = useState<string | null>(null);
  const [verifyBusy, setVerifyBusy] = useState(false);

  if (loading || !user) return null;

  const providers = providerIds(user);
  const hasPassword = justLinked || hasPasswordProvider(user);
  const hasGoogle = providers.includes("google.com");

  // An unverified password account is "untrusted" to Firebase: the next Google
  // sign-in on a trusted domain would DELETE this password. Verifying promotes it
  // to trusted so the two link instead. Register-time verification only covers new
  // accounts — this is how existing at-risk accounts protect themselves.
  const passwordAtRisk = hasPassword && !hasGoogle && !user.emailVerified;

  const resendVerification = async () => {
    setVerifyMsg(null);
    setVerifyBusy(true);
    try {
      await sendEmailVerification(user);
      setVerifyMsg("Verification email sent. Open it, then reload this page.");
    } catch (err: any) {
      setVerifyMsg(
        err?.code === "auth/too-many-requests"
          ? "Too many requests — please wait a few minutes and try again."
          : err?.message || "Could not send the verification email.",
      );
    } finally {
      setVerifyBusy(false);
    }
  };

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setMsg(null);

    if (password.length < MIN_PASSWORD) {
      setMsg({ ok: false, text: `Password must be at least ${MIN_PASSWORD} characters.` });
      return;
    }
    if (password !== confirm) {
      setMsg({ ok: false, text: "Passwords do not match." });
      return;
    }

    setBusy(true);
    try {
      await linkPasswordToCurrentUser(password);
      setJustLinked(true);
      setPassword("");
      setConfirm("");
      setMsg({ ok: true, text: "Password set. You can now sign in with your email as well as Google." });
    } catch (err: any) {
      setMsg({ ok: false, text: friendlyError(err) });
    } finally {
      setBusy(false);
    }
  };

  return (
    <section className="space-y-3">
      <h2 className="text-lg font-semibold">Sign-in methods</h2>
      <p className="text-sm" style={{ color: "var(--text-secondary)" }}>
        How you can get into this account. Adding a password does not create a second
        account — it adds another way into this one.
      </p>

      <div style={cardStyle}>
        <div style={{ display: "flex", flexDirection: "column", gap: "0.4rem" }}>
          <MethodRow label="Google" enabled={hasGoogle} />
          <MethodRow label="Email + password" enabled={hasPassword} />
        </div>

        {passwordAtRisk && (
          <div
            style={{
              display: "flex", gap: "0.6rem", padding: "0.75rem",
              background: "rgba(234,179,8,0.1)", border: "1px solid rgba(234,179,8,0.35)",
              borderRadius: "var(--radius-md)", fontSize: "0.825rem", color: "var(--text-secondary)",
            }}
          >
            <AlertTriangle size={16} style={{ flexShrink: 0, color: "var(--warning, #eab308)" }} />
            <div style={{ display: "flex", flexDirection: "column", gap: "0.5rem" }}>
              <span>
                Your email isn&apos;t verified yet. If you sign in with Google before verifying,
                Google replaces this password and email login stops working. Verify now to keep both.
              </span>
              <button
                type="button"
                onClick={resendVerification}
                disabled={verifyBusy}
                style={{
                  alignSelf: "flex-start", display: "flex", alignItems: "center", gap: "0.35rem",
                  padding: "6px 12px", background: "none", border: "1px solid var(--border)",
                  borderRadius: "var(--radius-md)", cursor: verifyBusy ? "not-allowed" : "pointer",
                  fontSize: "0.8rem", color: "var(--text-primary)",
                }}
              >
                <MailCheck size={13} /> {verifyBusy ? "Sending…" : "Send verification email"}
              </button>
              {verifyMsg && <span style={{ color: "var(--text-muted)" }}>{verifyMsg}</span>}
            </div>
          </div>
        )}

        {hasPassword ? (
          <p style={{ fontSize: "0.825rem", color: "var(--text-secondary)", margin: 0 }}>
            {hasGoogle
              ? "Both sign-in methods are active on this account."
              : "Email + password sign-in is active on this account."}
          </p>
        ) : (
          <>
            <p style={{ fontSize: "0.825rem", color: "var(--text-secondary)", margin: 0 }}>
              This account currently signs in with Google only, so email + password login
              will fail. Set a password below to enable it for{" "}
              <strong style={{ color: "var(--text-primary)" }}>{user.email}</strong>.
            </p>
            <form onSubmit={submit} style={{ display: "flex", flexDirection: "column", gap: "0.75rem" }}>
              <PasswordInput
                label="New password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                required
                minLength={MIN_PASSWORD}
                autoComplete="new-password"
                placeholder={`Min ${MIN_PASSWORD} characters`}
              />
              <PasswordInput
                label="Confirm password"
                value={confirm}
                onChange={(e) => setConfirm(e.target.value)}
                required
                minLength={MIN_PASSWORD}
                autoComplete="new-password"
                placeholder="Re-enter the password"
              />
              <button
                type="submit"
                disabled={busy}
                style={{
                  display: "flex", alignItems: "center", justifyContent: "center", gap: "0.4rem",
                  padding: "9px 16px", background: "var(--accent)", color: "#fff", border: "none",
                  borderRadius: "var(--radius-md)", cursor: busy ? "not-allowed" : "pointer",
                  fontSize: "0.875rem", fontWeight: 600, opacity: busy ? 0.6 : 1,
                }}
              >
                <KeyRound size={14} /> {busy ? "Setting password…" : "Set password"}
              </button>
            </form>
          </>
        )}

        {msg && (
          <p style={{ fontSize: "0.825rem", margin: 0, color: msg.ok ? "var(--success)" : "var(--danger)" }}>
            {msg.text}
          </p>
        )}
      </div>
    </section>
  );
}

function MethodRow({ label, enabled }: { label: string; enabled: boolean }) {
  return (
    <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", fontSize: "0.875rem" }}>
      <span style={{ color: "var(--text-secondary)" }}>{label}</span>
      <span
        style={{
          display: "flex", alignItems: "center", gap: "0.3rem", fontWeight: 500,
          color: enabled ? "var(--success)" : "var(--text-muted)",
        }}
      >
        {enabled && <Check size={13} />}
        {enabled ? "Enabled" : "Not set"}
      </span>
    </div>
  );
}
