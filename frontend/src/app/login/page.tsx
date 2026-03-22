"use client";

import { useState } from "react";
import { API_KEY_STORAGE_KEY } from "@/lib/constants";

export default function LoginPage() {
  const [isRegister, setIsRegister] = useState(false);
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    setLoading(true);

    try {
      const endpoint = isRegister ? "/api/auth/register" : "/api/auth/login";
      const res = await fetch(endpoint, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email, password }),
      });

      const data = await res.json();

      if (!res.ok) {
        setError(data.detail || "Request failed");
        return;
      }

      // Save API key and redirect
      localStorage.setItem(API_KEY_STORAGE_KEY, data.api_key);
      localStorage.setItem("iatronix_email", data.email);
      window.location.href = "/";
    } catch {
      setError("Network error. Please try again.");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="max-w-md mx-auto pt-16">
      <h1 className="text-3xl font-bold text-center mb-8">
        {isRegister ? "Create Account" : "Sign In"}
      </h1>

      <form onSubmit={handleSubmit} className="space-y-4">
        <div>
          <label className="block text-sm font-medium mb-1">Email</label>
          <input
            type="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            required
            className="w-full px-3 py-2 rounded-md border border-border bg-surface text-sm min-h-[44px]"
            placeholder="you@example.com"
          />
        </div>

        <div>
          <label className="block text-sm font-medium mb-1">Password</label>
          <input
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            required
            minLength={6}
            className="w-full px-3 py-2 rounded-md border border-border bg-surface text-sm min-h-[44px]"
            placeholder="Min 6 characters"
          />
        </div>

        {error && (
          <div className="p-3 rounded-lg bg-danger-bg border border-danger/30 text-sm text-danger">
            {error}
          </div>
        )}

        <button
          type="submit"
          disabled={loading}
          className="w-full py-2 bg-primary text-white rounded-md text-sm font-medium min-h-[44px] disabled:opacity-50"
        >
          {loading
            ? "Please wait..."
            : isRegister
              ? "Create Account"
              : "Sign In"}
        </button>
      </form>

      <p className="text-center text-sm text-text-muted mt-6">
        {isRegister ? "Already have an account?" : "Don't have an account?"}{" "}
        <button
          onClick={() => {
            setIsRegister(!isRegister);
            setError(null);
          }}
          className="text-primary hover:underline"
        >
          {isRegister ? "Sign in" : "Create one"}
        </button>
      </p>
    </div>
  );
}
