"use client";

import { useState, useEffect } from "react";
import Link from "next/link";
import { API_KEY_STORAGE_KEY } from "@/lib/constants";

export function Header() {
  const [apiKey, setApiKey] = useState("");
  const [showKeyInput, setShowKeyInput] = useState(false);
  const [darkMode, setDarkMode] = useState(false);
  const [email, setEmail] = useState("");

  useEffect(() => {
    const stored = localStorage.getItem(API_KEY_STORAGE_KEY);
    if (stored) setApiKey(stored);
    setEmail(localStorage.getItem("iatronix_email") || "");
    if (document.documentElement.classList.contains("dark")) setDarkMode(true);
  }, []);

  const saveKey = () => {
    localStorage.setItem(API_KEY_STORAGE_KEY, apiKey);
    setShowKeyInput(false);
  };

  const toggleDark = () => {
    document.documentElement.classList.toggle("dark");
    setDarkMode(!darkMode);
  };

  const isLoggedIn = !!apiKey;

  return (
    <header className="border-b border-border bg-surface-alt">
      <div className="max-w-5xl mx-auto px-4 h-14 flex items-center justify-between">
        <div className="flex items-center gap-4">
          <Link href="/" className="font-bold text-lg text-primary">
            Iatronix
          </Link>
          {isLoggedIn && (
            <nav className="flex items-center gap-3 text-sm">
              <Link
                href="/documents"
                className="text-text-secondary hover:text-text"
              >
                Documents
              </Link>
              <Link
                href="/settings"
                className="text-text-secondary hover:text-text"
              >
                Settings
              </Link>
            </nav>
          )}
        </div>

        <div className="flex items-center gap-3">
          <button
            onClick={toggleDark}
            className="p-2 rounded-md hover:bg-surface-hover min-h-[44px] min-w-[44px] flex items-center justify-center"
            aria-label="Toggle dark mode"
          >
            {darkMode ? "☀" : "☾"}
          </button>

          {isLoggedIn ? (
            <button
              onClick={() => setShowKeyInput(!showKeyInput)}
              className="px-3 py-2 text-sm rounded-md border border-border hover:bg-surface-hover min-h-[44px]"
            >
              {email || "Key Set"}
            </button>
          ) : (
            <Link
              href="/login"
              className="px-3 py-2 text-sm rounded-md bg-primary text-white min-h-[44px] flex items-center"
            >
              Sign In
            </Link>
          )}
        </div>
      </div>

      {showKeyInput && (
        <div className="max-w-5xl mx-auto px-4 pb-3 flex gap-2">
          <input
            type="password"
            value={apiKey}
            onChange={(e) => setApiKey(e.target.value)}
            placeholder="iatx.key_id.secret"
            className="flex-1 px-3 py-2 rounded-md border border-border bg-surface text-sm min-h-[44px]"
          />
          <button
            onClick={saveKey}
            className="px-4 py-2 bg-primary text-white rounded-md text-sm min-h-[44px]"
          >
            Save
          </button>
        </div>
      )}
    </header>
  );
}
