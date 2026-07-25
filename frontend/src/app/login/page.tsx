"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { Activity, Mail } from "lucide-react";
import { PasswordInput } from "@/components/ui/PasswordInput";
import { API_KEY_STORAGE_KEY } from "@/lib/constants";
import { signInWithEmailAndPassword, setPersistence, browserLocalPersistence, browserSessionPersistence } from "firebase/auth";
import { auth } from "@/lib/firebase";
import { GoogleSignIn } from "@/components/GoogleSignIn";
import { requestPasswordReset } from "@/lib/authGoogle";
import posthog from "posthog-js";

/**
 * Turn a Firebase sign-in error into something a human can act on.
 *
 * `auth/invalid-credential` is deliberately ambiguous on Firebase's side: with email
 * enumeration protection on (default since 2023-09-15) it covers "wrong password",
 * "no such user" AND "this account has no password provider at all" — and
 * fetchSignInMethodsForEmail, which used to tell them apart, is deprecated and returns
 * empty. We cannot distinguish them client-side without building an enumeration
 * oracle, so we name both realistic causes in one honest message. The Google case is
 * real and common: see the provider matrix in lib/authGoogle.ts.
 */
function loginErrorMessage(err: any): string {
  switch (err?.code) {
    case "auth/too-many-requests":
      return "Too many failed attempts. Please try again later or reset your password.";
    case "auth/invalid-credential":
    case "auth/wrong-password":
    case "auth/user-not-found":
      return "Wrong email or password — or this account signs in with Google. If you've used \"Continue with Google\" before, use that below, then add a password from Settings → Sign-in methods.";
    case "auth/invalid-email":
      return "That doesn't look like a valid email address.";
    case "auth/user-disabled":
      return "This account has been disabled. Please contact support.";
    case "auth/network-request-failed":
      return "Network error. Check your connection and try again.";
    default:
      return err?.message || "Invalid email or password";
  }
}

export default function LoginPage() {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [rememberMe, setRememberMe] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [resetting, setResetting] = useState(false);
  const [shaking, setShaking] = useState(false);

  // Read the post-registration flags. Deliberately window.location rather than
  // useSearchParams(), which would force this page into a Suspense boundary at build.
  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    if (!params.get("registered")) return;
    setNotice(
      params.get("verify") === "failed"
        ? "Account created, but we couldn't send the verification email. Use \"Forgot password?\" to request it again — verifying keeps email login working if you also use Google."
        : "Account created. Check your inbox and click the verification link — it keeps email sign-in working even after you use Google.",
    );
  }, []);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    setNotice(null);
    setLoading(true);

    try {
      await setPersistence(auth, rememberMe ? browserLocalPersistence : browserSessionPersistence);
      const userCredential = await signInWithEmailAndPassword(auth, email, password);
      const token = await userCredential.user.getIdToken();

      localStorage.setItem(API_KEY_STORAGE_KEY, token);
      localStorage.setItem("iatronix_email", userCredential.user.email || email);

      // Analytics is best-effort — a PostHog failure must never be reported to the
      // user as a failed login, which is what happened when these were unwrapped.
      try {
        posthog.identify(userCredential.user.uid, { email: userCredential.user.email ?? email });
        posthog.capture("user_logged_in", { method: "email" });
      } catch {
        /* ignore */
      }

      window.location.href = "/";
    } catch (err: any) {
      setError(loginErrorMessage(err));
      setShaking(true);
      setTimeout(() => setShaking(false), 500);
    } finally {
      setLoading(false);
    }
  };

  const handleForgotPassword = async () => {
    setError(null);
    setNotice(null);
    if (!email.trim()) {
      setError("Enter your email address above first, then tap \"Forgot password?\".");
      return;
    }
    setResetting(true);
    try {
      await requestPasswordReset(email.trim());
    } catch (err: any) {
      // Anything other than a malformed address is swallowed on purpose: reporting
      // "no such user" would turn this form into an email-enumeration oracle.
      if (err?.code === "auth/invalid-email") {
        setError("That doesn't look like a valid email address.");
        setResetting(false);
        return;
      }
      if (err?.code === "auth/too-many-requests") {
        setError("Too many requests. Please wait a few minutes and try again.");
        setResetting(false);
        return;
      }
    }
    setResetting(false);
    setNotice(
      "If an account exists for that address, a password reset link is on its way. If you normally sign in with Google, use \"Continue with Google\" below instead.",
    );
  };

  return (
    <div
      style={{
        minHeight: "calc(100vh - 110px)",
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        padding: "2rem 1rem",
      }}
    >
      <div
        className="animate-in"
        style={{
          width: "100%",
          maxWidth: 420,
          background: "var(--bg-surface)",
          border: "1px solid var(--border)",
          borderRadius: "var(--radius-lg)",
          boxShadow: "var(--shadow-lg)",
          padding: "2.5rem 2rem",
        }}
      >
        {/* Header */}
        <div style={{ textAlign: "center", marginBottom: "2rem" }}>
          <div
            style={{
              width: 52,
              height: 52,
              borderRadius: "50%",
              background: "var(--accent-glow)",
              border: "1px solid rgba(59,130,246,0.3)",
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              margin: "0 auto 1rem",
            }}
          >
            <Activity size={22} color="var(--accent)" />
          </div>
          <h1
            style={{
              margin: "0 0 0.25rem",
              fontSize: "1.5rem",
              fontWeight: 700,
              color: "var(--text-primary)",
            }}
          >
            Sign in to Iatronix
          </h1>
          <p style={{ margin: 0, fontSize: "0.875rem", color: "var(--text-muted)" }}>
            Evidence-based medical intelligence
          </p>
        </div>

        {/* Informational notice (registration confirmation, reset requested) */}
        {notice && (
          <div
            style={{
              marginBottom: "1.25rem",
              padding: "0.75rem 1rem",
              background: "var(--accent-glow)",
              border: "1px solid rgba(59,130,246,0.3)",
              borderRadius: "var(--radius-md)",
              fontSize: "0.85rem",
              color: "var(--text-secondary)",
            }}
          >
            {notice}
          </div>
        )}

        {/* Error message */}
        {error && (
          <div
            className={shaking ? "shake" : ""}
            style={{
              marginBottom: "1.25rem",
              padding: "0.75rem 1rem",
              background: "rgba(239,68,68,0.1)",
              border: "1px solid rgba(239,68,68,0.3)",
              borderRadius: "var(--radius-md)",
              fontSize: "0.875rem",
              color: "var(--danger)",
            }}
          >
            {error}
          </div>
        )}

        {/* Form */}
        <form onSubmit={handleSubmit} style={{ display: "flex", flexDirection: "column", gap: "1rem" }}>
          {/* Email */}
          <div>
            <label
              style={{
                display: "block",
                fontSize: "0.875rem",
                fontWeight: 500,
                color: "var(--text-secondary)",
                marginBottom: "0.375rem",
              }}
            >
              Email
            </label>
            <div style={{ position: "relative" }}>
              <Mail
                size={16}
                style={{
                  position: "absolute",
                  left: 14,
                  top: "50%",
                  transform: "translateY(-50%)",
                  color: "var(--text-muted)",
                  pointerEvents: "none",
                }}
              />
              <input
                type="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                required
                placeholder="you@example.com"
                style={{
                  width: "100%",
                  padding: "10px 14px 10px 40px",
                  background: "var(--bg-elevated)",
                  border: "1px solid var(--border)",
                  borderRadius: "var(--radius-md)",
                  color: "var(--text-primary)",
                  fontSize: "0.95rem",
                  outline: "none",
                  boxSizing: "border-box",
                  transition: "border-color var(--transition), box-shadow var(--transition)",
                }}
                onFocus={(e) => {
                  e.currentTarget.style.borderColor = "var(--border-focus)";
                  e.currentTarget.style.boxShadow = "0 0 0 3px var(--accent-glow)";
                }}
                onBlur={(e) => {
                  e.currentTarget.style.borderColor = "var(--border)";
                  e.currentTarget.style.boxShadow = "none";
                }}
              />
            </div>
          </div>

          {/* Password */}
          <div>
            <div style={{ display: "flex", justifyContent: "space-between", marginBottom: "0.375rem" }}>
              <label
                style={{
                  fontSize: "0.875rem",
                  fontWeight: 500,
                  color: "var(--text-secondary)",
                }}
              >
                Password
              </label>
              <button
                type="button"
                onClick={handleForgotPassword}
                disabled={resetting}
                style={{
                  background: "none",
                  border: "none",
                  fontSize: "0.8rem",
                  color: "var(--accent)",
                  cursor: resetting ? "not-allowed" : "pointer",
                  padding: 0,
                  opacity: resetting ? 0.6 : 1,
                }}
              >
                {resetting ? "Sending…" : "Forgot password?"}
              </button>
            </div>
            <PasswordInput
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              required
              minLength={6}
              placeholder="Min 6 characters"
              style={{ background: "var(--bg-elevated)" }}
            />
          </div>

          {/* Remember me */}
          <label
            style={{
              display: "flex",
              alignItems: "center",
              gap: "0.5rem",
              cursor: "pointer",
              fontSize: "0.875rem",
              color: "var(--text-secondary)",
              userSelect: "none",
            }}
          >
            <input
              type="checkbox"
              checked={rememberMe}
              onChange={(e) => setRememberMe(e.target.checked)}
              style={{ accentColor: "var(--accent)", width: 15, height: 15 }}
            />
            Remember me
          </label>

          {/* Submit */}
          <button
            type="submit"
            disabled={loading}
            style={{
              width: "100%",
              padding: "11px",
              background: loading ? "var(--bg-elevated)" : "var(--accent)",
              border: "none",
              borderRadius: "var(--radius-md)",
              color: loading ? "var(--text-muted)" : "#fff",
              fontSize: "0.95rem",
              fontWeight: 600,
              cursor: loading ? "not-allowed" : "pointer",
              transition: "all var(--transition)",
              marginTop: "0.25rem",
            }}
          >
            {loading ? "Signing in..." : "Sign In"}
          </button>
        </form>

        {/* Divider */}
        <div
          style={{
            display: "flex",
            alignItems: "center",
            gap: "0.75rem",
            margin: "1.5rem 0",
          }}
        >
          <div style={{ flex: 1, height: 1, background: "var(--border)" }} />
          <span style={{ fontSize: "0.8rem", color: "var(--text-muted)" }}>or</span>
          <div style={{ flex: 1, height: 1, background: "var(--border)" }} />
        </div>

        {/* Google sign-in (with safe merge into an existing password account) */}
        <div style={{ marginBottom: "1.5rem" }}>
          <GoogleSignIn rememberMe={rememberMe} />
        </div>

        {/* Create account */}
        <p
          style={{
            textAlign: "center",
            fontSize: "0.875rem",
            color: "var(--text-secondary)",
            margin: 0,
          }}
        >
          Don&apos;t have an account?{" "}
          <Link
            href="/register"
            style={{ color: "var(--accent)", fontWeight: 500, textDecoration: "none" }}
          >
            Create an account
          </Link>
        </p>
      </div>
    </div>
  );
}
