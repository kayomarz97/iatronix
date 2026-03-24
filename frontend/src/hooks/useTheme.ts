"use client";

import { useEffect, useState } from "react";

function getSystemTheme(): "dark" | "light" {
  if (typeof window === "undefined") return "dark";
  return window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
}

function applyTheme(t: "dark" | "light") {
  document.documentElement.dataset.theme = t;
}

export function useTheme() {
  const [theme, setTheme] = useState<"dark" | "light">("dark");

  useEffect(() => {
    const saved = localStorage.getItem("theme") as "dark" | "light" | null;
    const initial = saved ?? getSystemTheme();
    setTheme(initial);
    applyTheme(initial);

    // Sync with OS preference changes only when user hasn't manually set a preference
    const mq = window.matchMedia("(prefers-color-scheme: dark)");
    const handleChange = (e: MediaQueryListEvent) => {
      if (!localStorage.getItem("theme")) {
        const next = e.matches ? "dark" : "light";
        setTheme(next);
        applyTheme(next);
      }
    };
    mq.addEventListener("change", handleChange);
    return () => mq.removeEventListener("change", handleChange);
  }, []);

  const toggle = () => {
    const next = theme === "dark" ? "light" : "dark";
    setTheme(next);
    applyTheme(next);
    localStorage.setItem("theme", next);
  };

  const resetToSystem = () => {
    localStorage.removeItem("theme");
    const sys = getSystemTheme();
    setTheme(sys);
    applyTheme(sys);
  };

  return { theme, toggle, resetToSystem };
}
