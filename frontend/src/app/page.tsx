"use client";

import { useState, useEffect, type FormEvent } from "react";
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
import { useQueryContext } from "@/components/providers/QueryProvider";
import { API_KEY_STORAGE_KEY } from "@/lib/constants";

const CATEGORIES = [
  { icon: <Pill size={20} />, label: "Drug Information", seed: "metformin dosing and interactions" },
  { icon: <Heart size={20} />, label: "Disease Lookup", seed: "heart failure management guidelines" },
  { icon: <GitCompare size={20} />, label: "Drug Comparison", seed: "lisinopril vs losartan for hypertension" },
  { icon: <Stethoscope size={20} />, label: "Procedures", seed: "when to change a central line" },
  { icon: <FlaskConical size={20} />, label: "Evidence Review", seed: "is telmisartan given in CKD" },
  { icon: <BookOpen size={20} />, label: "Pathophysiology", seed: "pathophysiology of sepsis" },
];

export default function HomePage() {
  const router = useRouter();
  const { submitQuery } = useQueryContext();
  const [query, setQuery] = useState("");
  const [focused, setFocused] = useState(false);
  const [isLoggedIn, setIsLoggedIn] = useState(false);

  useEffect(() => {
    const key = localStorage.getItem(API_KEY_STORAGE_KEY);
    setIsLoggedIn(!!key);
  }, []);

  const handleSubmit = (e: FormEvent) => {
    e.preventDefault();
    const q = query.trim();
    if (!q) return;
    submitQuery(q);
    router.push(`/query?q=${encodeURIComponent(q)}`);
  };

  const runSearch = (q: string) => {
    setQuery(q);
    submitQuery(q);
    router.push(`/query?q=${encodeURIComponent(q)}`);
  };

  return (
    <div
      style={{
        minHeight: "calc(100vh - 58px - 52px)",
        display: "flex",
        flexDirection: "column",
        alignItems: "center",
        justifyContent: "center",
        padding: "2rem 1.5rem",
        position: "relative",
      }}
    >
      {/* Search history sidebar */}
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
          <svg
            width="26"
            height="26"
            viewBox="0 0 24 24"
            fill="none"
            stroke="var(--accent)"
            strokeWidth="2.5"
            strokeLinecap="round"
            strokeLinejoin="round"
          >
            <polyline points="22 12 18 12 15 21 9 3 6 12 2 12" />
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
        <p
          style={{
            fontSize: "1.05rem",
            color: "var(--text-secondary)",
            margin: 0,
            fontWeight: 400,
          }}
        >
          Evidence-based medical intelligence
        </p>
      </div>

      {/* Search form */}
      <form
        onSubmit={handleSubmit}
        className="animate-in"
        style={{
          width: "100%",
          maxWidth: 620,
          marginBottom: "2rem",
          animationDelay: "50ms",
        }}
      >
        <div
          style={{
            position: "relative",
            boxShadow: focused
              ? "0 0 0 3px var(--accent-glow), var(--shadow-md)"
              : "var(--shadow-md)",
            borderRadius: "var(--radius-lg)",
            transition: "box-shadow 200ms ease",
          }}
        >
          <Search
            size={19}
            style={{
              position: "absolute",
              left: 18,
              top: "50%",
              transform: "translateY(-50%)",
              color: focused ? "var(--accent)" : "var(--text-muted)",
              transition: "color 200ms ease",
              pointerEvents: "none",
            }}
          />
          <input
            type="text"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            onFocus={() => setFocused(true)}
            onBlur={() => setFocused(false)}
            placeholder="Search drugs, diseases, procedures..."
            style={{
              width: "100%",
              padding: "16px 56px 16px 50px",
              background: "var(--bg-surface)",
              border: "1px solid",
              borderColor: focused ? "var(--border-focus)" : "var(--border)",
              borderRadius: "var(--radius-lg)",
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
              position: "absolute",
              right: 8,
              top: "50%",
              transform: "translateY(-50%)",
              padding: "8px 18px",
              background: query.trim() ? "var(--accent)" : "var(--bg-elevated)",
              border: "none",
              borderRadius: "var(--radius-md)",
              cursor: query.trim() ? "pointer" : "not-allowed",
              color: query.trim() ? "#fff" : "var(--text-muted)",
              fontWeight: 600,
              fontSize: "0.875rem",
              transition: "all 200ms ease",
            }}
          >
            Search
          </button>
        </div>
      </form>

      {/* Login banner */}
      {!isLoggedIn && (
        <div
          className="animate-in"
          style={{
            marginBottom: "2rem",
            padding: "0.625rem 1.25rem",
            background: "rgba(59,130,246,0.08)",
            border: "1px solid rgba(59,130,246,0.2)",
            borderRadius: "var(--radius-md)",
            fontSize: "0.85rem",
            color: "var(--text-secondary)",
            textAlign: "center",
            animationDelay: "100ms",
          }}
        >
          <a href="/login" style={{ color: "var(--accent)", fontWeight: 500 }}>
            Sign in
          </a>{" "}
          to save search history and use your API key
        </div>
      )}

      {/* Category cards */}
      <div
        className="animate-in"
        style={{
          display: "grid",
          gridTemplateColumns: "repeat(auto-fill, minmax(170px, 1fr))",
          gap: "0.75rem",
          width: "100%",
          maxWidth: 620,
          animationDelay: "100ms",
        }}
      >
        {CATEGORIES.map((cat) => (
          <CategoryCard
            key={cat.label}
            icon={cat.icon}
            label={cat.label}
            onClick={() => runSearch(cat.seed)}
          />
        ))}
      </div>

      {/* Disclaimer */}
      <p
        style={{
          marginTop: "2.5rem",
          fontSize: "0.7rem",
          color: "var(--text-muted)",
          textAlign: "center",
          maxWidth: 480,
          lineHeight: 1.5,
        }}
      >
        For clinical decision support and educational purposes only. Always verify
        information with primary sources. Not a substitute for professional medical judgment.
      </p>
    </div>
  );
}

function CategoryCard({
  icon,
  label,
  onClick,
}: {
  icon: React.ReactNode;
  label: string;
  onClick: () => void;
}) {
  const [hovered, setHovered] = useState(false);
  return (
    <button
      onClick={onClick}
      onMouseEnter={() => setHovered(true)}
      onMouseLeave={() => setHovered(false)}
      style={{
        padding: "0.875rem 1rem",
        background: hovered ? "var(--bg-elevated)" : "var(--bg-surface)",
        border: `1px solid ${hovered ? "var(--border-focus)" : "var(--border)"}`,
        borderRadius: "var(--radius-md)",
        cursor: "pointer",
        textAlign: "left",
        display: "flex",
        flexDirection: "column",
        gap: "0.5rem",
        transition: "all 200ms ease",
        transform: hovered ? "translateY(-1px)" : "none",
        boxShadow: hovered ? "var(--shadow-md)" : "none",
      }}
    >
      <span style={{ color: "var(--accent)" }}>{icon}</span>
      <span
        style={{
          fontSize: "0.825rem",
          fontWeight: 500,
          color: "var(--text-primary)",
          lineHeight: 1.3,
        }}
      >
        {label}
      </span>
    </button>
  );
}
