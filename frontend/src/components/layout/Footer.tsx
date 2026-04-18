"use client";

import { useRef, useState } from "react";
import dynamic from "next/dynamic";

const TetrisModal = dynamic(() => import("@/components/ui/TetrisModal"), { ssr: false });

export function Footer() {
  const clickCountRef = useRef(0);
  const [isTetrisOpen, setIsTetrisOpen] = useState(false);

  const handleEasterEggClick = () => {
    clickCountRef.current += 1;
    if (clickCountRef.current >= 4) {
      clickCountRef.current = 0;
      setIsTetrisOpen(true);
    }
  };

  return (
    <>
      <footer
        style={{
          borderTop: "1px solid var(--border)",
          padding: "1.25rem 1.25rem",
          textAlign: "center",
          display: "flex",
          flexDirection: "column",
          alignItems: "center",
          gap: "0.5rem",
        }}
      >
        <p
          style={{
            margin: 0,
            fontSize: "0.75rem",
            color: "var(--text-muted)",
          }}
        >
          Iatronix Medical Reference — For clinical decision support only. Not a
          substitute for professional medical judgment.
        </p>
        <p
          onClick={handleEasterEggClick}
          style={{
            margin: 0,
            fontSize: "0.7rem",
            fontFamily: "monospace",
            color: "var(--text-muted)",
            opacity: 0.4,
            cursor: "pointer",
            userSelect: "none",
            transition: "opacity 0.3s",
          }}
          onMouseOver={(e) => (e.currentTarget.style.opacity = "1")}
          onMouseOut={(e) => (e.currentTarget.style.opacity = "0.4")}
        >
          Made with Love and syntax delegation (and a clinically significant dose of regular Coca-Cola)
        </p>
      </footer>
      {isTetrisOpen && <TetrisModal onClose={() => setIsTetrisOpen(false)} />}
    </>
  );
}
