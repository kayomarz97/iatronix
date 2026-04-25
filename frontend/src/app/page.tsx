"use client";

import { useState, useEffect, useRef, type FormEvent, type KeyboardEvent } from "react";
import { useRouter } from "next/navigation";
import {
  Search,
  Pill,
  Heart,
  GitCompare,
  Stethoscope,
  FlaskConical,
  BookOpen,
} from "lucide-react";
import { SearchHistorySidebar } from "@/components/ui/SearchHistorySidebar";
import { SearchSuggestions } from "@/components/ui/SearchSuggestions";
import { useQueryContext } from "@/components/providers/QueryProvider";
import { useSearchSuggestions } from "@/hooks/useSearchSuggestions";
import { API_KEY_STORAGE_KEY } from "@/lib/constants";

const CATEGORIES = [
  { icon: <Pill size={18} />, label: "Drug Information", seed: "metformin dosing and interactions" },
  { icon: <Heart size={18} />, label: "Disease Lookup", seed: "heart failure management guidelines" },
  { icon: <GitCompare size={18} />, label: "Drug Comparison", seed: "lisinopril vs losartan for hypertension" },
  { icon: <Stethoscope size={18} />, label: "Procedures", seed: "when to change a central line" },
  { icon: <FlaskConical size={18} />, label: "Evidence Review", seed: "is telmisartan given in CKD" },
  { icon: <BookOpen size={18} />, label: "Pathophysiology", seed: "pathophysiology of sepsis" },
];

export default function HomePage() {
  const router = useRouter();
  const { submitQuery } = useQueryContext();
  const [query, setQuery] = useState("");
  const [focused, setFocused] = useState(false);
  const [showSuggestions, setShowSuggestions] = useState(false);
  const [highlightIndex, setHighlightIndex] = useState(-1);
  const [isLoggedIn, setIsLoggedIn] = useState(false);
  const wrapperRef = useRef<HTMLDivElement>(null);

  const { suggestions, clear } = useSearchSuggestions(query);

  useEffect(() => {
    const key = localStorage.getItem(API_KEY_STORAGE_KEY);
    setIsLoggedIn(!!key);
  }, []);

  // Close suggestions on outside click
  useEffect(() => {
    const handler = (e: MouseEvent) => {
      if (wrapperRef.current && !wrapperRef.current.contains(e.target as Node)) {
        setShowSuggestions(false);
      }
    };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, []);

  useEffect(() => {
    setHighlightIndex(-1);
    setShowSuggestions(suggestions.length > 0 && focused);
  }, [suggestions, focused]);

  const runSearch = (q: string) => {
    setQuery(q);
    setShowSuggestions(false);
    clear();
    submitQuery(q);
    router.push(`/query?q=${encodeURIComponent(q)}`);
  };

  const handleSubmit = (e: FormEvent) => {
    e.preventDefault();
    const q = (highlightIndex >= 0 && suggestions[highlightIndex]) ? suggestions[highlightIndex] : query.trim();
    if (!q) return;
    runSearch(q);
  };

  const handleKeyDown = (e: KeyboardEvent<HTMLInputElement>) => {
    if (!showSuggestions || suggestions.length === 0) return;
    if (e.key === "ArrowDown") {
      e.preventDefault();
      setHighlightIndex((i) => Math.min(i + 1, suggestions.length - 1));
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      setHighlightIndex((i) => Math.max(i - 1, -1));
    } else if (e.key === "Escape") {
      setShowSuggestions(false);
      setHighlightIndex(-1);
    }
  };

  return (
    <div
      style={{
        minHeight: "calc(100vh - 58px - 52px)",
        display: "flex",
        flexDirection: "column",
        alignItems: "center",
        justifyContent: "center",
        padding: "2rem 1.5rem 2rem calc(1.5rem + 24px)",
        position: "relative",
      }}
    >
      <SearchHistorySidebar onRerun={runSearch} isLoggedIn={isLoggedIn} />

      {/* Hero */}
      <div className="animate-in" style={{ textAlign: "center", marginBottom: "2.5rem", maxWidth: 600 }}>
        <div
          style={{
            width: 56,
            height: 56,
            borderRadius: "50%",
            background: "var(--accent-glow)",
            border: "1px solid rgba(59,130,246,0.3)",
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            margin: "0 auto 1.25rem",
          }}
        >
          <svg width="28" height="28" viewBox="0 0 512 512" xmlns="http://www.w3.org/2000/svg">
            <path d="M 150 160 L 70 256 L 150 352" stroke="#818CF8" fill="none" strokeWidth="40" strokeLinecap="round" strokeLinejoin="round" />
            <path d="M 362 160 L 442 256 L 362 352" stroke="#818CF8" fill="none" strokeWidth="40" strokeLinecap="round" strokeLinejoin="round" />
            <path d="M 70 256 L 180 256 L 215 140 L 275 380 L 310 256 L 442 256" stroke="#22D3EE" fill="none" strokeWidth="40" strokeLinecap="round" strokeLinejoin="round" />
          </svg>
        </div>
        <h1
          style={{
            fontSize: "clamp(2rem, 5vw, 3rem)",
            fontWeight: 800,
            color: "var(--text-primary)",
            margin: "0 0 0.5rem",
            letterSpacing: "-0.02em",
          }}
        >
          Iatronix
        </h1>
        <p style={{ fontSize: "1.05rem", color: "var(--text-secondary)", margin: 0, fontWeight: 400 }}>
          Evidence-based medical intelligence
        </p>
      </div>

      {/* Search form */}
      <form
        onSubmit={handleSubmit}
        className="animate-in"
        style={{ width: "100%", maxWidth: 620, marginBottom: "2rem", animationDelay: "50ms" }}
      >
        <div ref={wrapperRef} style={{ position: "relative" }}>
          <div
            style={{
              position: "relative",
              boxShadow: focused ? "0 0 0 3px var(--accent-glow), var(--shadow-md)" : "var(--shadow-md)",
              borderRadius: "var(--radius-lg)",
              transition: "box-shadow 200ms ease",
            }}
          >
            <Search
              size={19}
              style={{
                position: "absolute", left: 18, top: "50%", transform: "translateY(-50%)",
                color: focused ? "var(--accent)" : "var(--text-muted)",
                transition: "color 200ms ease", pointerEvents: "none",
              }}
            />
            <input
              type="text"
              value={query}
              onChange={(e) => { setQuery(e.target.value); setShowSuggestions(true); }}
              onFocus={() => { setFocused(true); setShowSuggestions(suggestions.length > 0); }}
              onBlur={() => setFocused(false)}
              onKeyDown={handleKeyDown}
              placeholder="Search drugs, diseases, procedures..."
              autoComplete="off"
              style={{
                width: "100%",
                padding: "16px 56px 16px 50px",
                background: "var(--bg-surface)",
                border: "1px solid",
                borderColor: focused ? "var(--border-focus)" : "var(--border)",
                borderRadius: showSuggestions ? "var(--radius-lg) var(--radius-lg) 0 0" : "var(--radius-lg)",
                color: "var(--text-primary)",
                fontSize: "1rem",
                outline: "none",
                boxSizing: "border-box",
                transition: "border-color 200ms ease",
              }}
            />
            <button
              type="submit"
              disabled={!query.trim()}
              style={{
                position: "absolute", right: 8, top: "50%", transform: "translateY(-50%)",
                padding: "8px 18px",
                background: query.trim() ? "var(--accent)" : "var(--bg-elevated)",
                border: "none", borderRadius: "var(--radius-md)",
                cursor: query.trim() ? "pointer" : "not-allowed",
                color: query.trim() ? "#fff" : "var(--text-muted)",
                fontWeight: 600, fontSize: "0.875rem",
                transition: "all 200ms ease",
              }}
            >
              Search
            </button>
          </div>

          {showSuggestions && (
            <SearchSuggestions
              suggestions={suggestions}
              onSelect={runSearch}
              highlightIndex={highlightIndex}
            />
          )}
        </div>
      </form>

      {!isLoggedIn && (
        <div
          className="animate-in"
          style={{
            marginBottom: "2rem", padding: "0.625rem 1.25rem",
            background: "rgba(59,130,246,0.08)", border: "1px solid rgba(59,130,246,0.2)",
            borderRadius: "var(--radius-md)", fontSize: "0.85rem",
            color: "var(--text-secondary)", textAlign: "center", animationDelay: "100ms",
          }}
        >
          <a href="/login" style={{ color: "var(--accent)", fontWeight: 500 }}>Sign in</a>{" "}
          to save search history and use your API key
        </div>
      )}


      <p
        style={{
          marginTop: "2.5rem", fontSize: "0.7rem", color: "var(--text-muted)",
          textAlign: "center", maxWidth: 480, lineHeight: 1.5,
        }}
      >
        For clinical decision support and educational purposes only. Always verify
        information with primary sources. Not a substitute for professional medical judgment.
      </p>
    </div>
  );
}

function CategoryCard({ icon, label, onClick }: { icon: React.ReactNode; label: string; onClick: () => void }) {
  const [hovered, setHovered] = useState(false);
  return (
    <button
      onClick={onClick}
      onMouseEnter={() => setHovered(true)}
      onMouseLeave={() => setHovered(false)}
      style={{
        padding: "0.75rem 0.875rem",
        background: hovered ? "var(--bg-elevated)" : "var(--bg-surface)",
        border: `1px solid ${hovered ? "var(--accent)" : "var(--border)"}`,
        borderLeft: `3px solid ${hovered ? "var(--accent)" : "var(--border)"}`,
        borderRadius: "var(--radius-md)",
        cursor: "pointer",
        textAlign: "left",
        display: "flex",
        flexDirection: "column",
        gap: "0.4rem",
        transition: "all 180ms ease",
        transform: hovered ? "translateY(-1px)" : "none",
        boxShadow: hovered ? "var(--shadow-md)" : "none",
      }}
    >
      <span style={{ color: hovered ? "var(--accent)" : "var(--text-muted)" }}>{icon}</span>
      <span style={{ fontSize: "0.8rem", fontWeight: 500, color: "var(--text-primary)", lineHeight: 1.3 }}>
        {label}
      </span>
    </button>
  );
}
