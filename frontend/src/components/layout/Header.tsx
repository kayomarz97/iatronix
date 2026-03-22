"use client";

import { useState, useEffect } from "react";
import Link from "next/link";
import { API_KEY_STORAGE_KEY } from "@/lib/constants";

export function Header() {
  const [darkMode, setDarkMode] = useState(false);
  const [email, setEmail] = useState("");
  const [isLoggedIn, setIsLoggedIn] = useState(false);

  useEffect(() => {
    const stored = localStorage.getItem(API_KEY_STORAGE_KEY);
    setIsLoggedIn(!!stored);
    setEmail(localStorage.getItem("iatronix_email") || "");

    // Restore dark mode from localStorage
    const savedDark = localStorage.getItem("iatronix_dark") === "true";
    if (savedDark) {
      document.documentElement.classList.add("dark");
      setDarkMode(true);
    }
  }, []);

  const toggleDark = () => {
    const next = !darkMode;
    if (next) {
      document.documentElement.classList.add("dark");
    } else {
      document.documentElement.classList.remove("dark");
    }
    localStorage.setItem("iatronix_dark", String(next));
    setDarkMode(next);
  };

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
            {darkMode ? "\u2600" : "\u263E"}
          </button>

          {isLoggedIn ? (
            <Link
              href="/settings"
              className="px-3 py-2 text-sm rounded-md border border-border hover:bg-surface-hover min-h-[44px] flex items-center"
            >
              {email || "Account"}
            </Link>
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
    </header>
  );
}
