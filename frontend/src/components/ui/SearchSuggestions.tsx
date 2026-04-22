"use client";

import { Pill, Stethoscope } from "lucide-react";

interface Props {
  suggestions: string[];
  onSelect: (s: string) => void;
  highlightIndex: number;
}

// Heuristic: if a suggestion looks like a drug (ends in common suffixes or is short), show pill icon
const DRUG_SUFFIXES = /(?:in|ol|am|ide|ine|ate|one|il|ab|mab|nib|stat|pril|sartan|cillin|mycin|cycline|pam|zole|dipine|vir|fib|gliptin|tidine|floxacin|oxacin)$/i;
function isDrug(s: string): boolean {
  return DRUG_SUFFIXES.test(s.split(" ")[0]);
}

export function SearchSuggestions({ suggestions, onSelect, highlightIndex }: Props) {
  if (suggestions.length === 0) return null;

  return (
    <ul
      role="listbox"
      style={{
        position: "absolute",
        top: "calc(100% + 4px)",
        left: 0,
        right: 0,
        background: "var(--bg-surface)",
        border: "1px solid var(--border)",
        borderRadius: "var(--radius-md)",
        boxShadow: "var(--shadow-lg)",
        zIndex: 50,
        margin: 0,
        padding: "4px 0",
        listStyle: "none",
        overflow: "hidden",
      }}
    >
      {suggestions.map((s, i) => {
        const active = i === highlightIndex;
        const drug = isDrug(s);
        return (
          <li
            key={s}
            role="option"
            aria-selected={active}
            onMouseDown={(e) => { e.preventDefault(); onSelect(s); }}
            style={{
              display: "flex",
              alignItems: "center",
              gap: "0.625rem",
              padding: "8px 14px",
              cursor: "pointer",
              background: active ? "var(--bg-hover)" : "transparent",
              fontSize: "0.875rem",
              color: active ? "var(--text-primary)" : "var(--text-secondary)",
              transition: "background 0.1s",
            }}
            onMouseEnter={(e) => { (e.currentTarget as HTMLLIElement).style.background = "var(--bg-hover)"; }}
            onMouseLeave={(e) => { (e.currentTarget as HTMLLIElement).style.background = active ? "var(--bg-hover)" : "transparent"; }}
          >
            <span style={{ color: "var(--text-muted)", flexShrink: 0 }}>
              {drug ? <Pill size={13} /> : <Stethoscope size={13} />}
            </span>
            {s}
          </li>
        );
      })}
    </ul>
  );
}
