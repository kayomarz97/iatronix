import { ImageResponse } from "next/og";
import { SITE_NAME, SITE_TAGLINE } from "@/lib/site";

// Generated social-share card (1200x630) for /, reused as the Twitter card.
// Built at build time by next/og — no binary asset to keep in sync with the brand.
// Colours are literal here on purpose: this renders outside the browser, so CSS
// custom properties from globals.css are not available.

export const alt = `${SITE_NAME} — ${SITE_TAGLINE}`;
export const size = { width: 1200, height: 630 };
export const contentType = "image/png";

export default async function Image() {
  return new ImageResponse(
    (
      <div
        style={{
          width: "100%",
          height: "100%",
          display: "flex",
          flexDirection: "column",
          alignItems: "center",
          justifyContent: "center",
          background: "linear-gradient(135deg, #0a0a0a 0%, #111827 55%, #052e26 100%)",
          color: "#f9fafb",
          fontFamily: "sans-serif",
        }}
      >
        <div style={{ display: "flex", alignItems: "center", gap: 20 }}>
          <div
            style={{
              width: 18,
              height: 72,
              borderRadius: 9,
              background: "#10b981",
              display: "flex",
            }}
          />
          <div style={{ fontSize: 88, fontWeight: 700, letterSpacing: -2, display: "flex" }}>
            {SITE_NAME}
          </div>
        </div>

        <div style={{ marginTop: 24, fontSize: 34, color: "#9ca3af", display: "flex" }}>
          {SITE_TAGLINE}
        </div>

        <div
          style={{
            marginTop: 56,
            fontSize: 24,
            color: "#6ee7b7",
            display: "flex",
            gap: 18,
          }}
        >
          <span>PubMed</span>
          <span style={{ color: "#374151" }}>·</span>
          <span>FDA</span>
          <span style={{ color: "#374151" }}>·</span>
          <span>NICE</span>
          <span style={{ color: "#374151" }}>·</span>
          <span>ClinicalTrials.gov</span>
        </div>

        <div style={{ marginTop: 40, fontSize: 19, color: "#6b7280", display: "flex" }}>
          Every claim graded by the evidence behind it
        </div>
      </div>
    ),
    size,
  );
}
