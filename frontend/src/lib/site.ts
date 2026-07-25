// Canonical site identity — used by metadata, robots and sitemap.
//
// The DEV deployment (med.debkay.com) is publicly reachable, so it must NEVER be
// indexed: search engines would otherwise treat it as duplicate content and expose a
// staging environment. Indexing is therefore allowed ONLY when the resolved site URL is
// the canonical production host.
//
// NEXT_PUBLIC_SITE_URL is read from .env.local at build time (see frontend/Dockerfile —
// this project feeds NEXT_PUBLIC_* via .env.local, not docker build args). It defaults to
// production so a prod deploy needs no new variable; the dev VPS sets it explicitly.

export const PRODUCTION_URL = "https://med.kayomarz.com";

export const SITE_URL = (process.env.NEXT_PUBLIC_SITE_URL || PRODUCTION_URL).replace(/\/$/, "");

/** True only on the canonical production host. Gates all search-engine indexing. */
export const IS_PRODUCTION_SITE = SITE_URL === PRODUCTION_URL;

export const SITE_NAME = "Iatronix";
export const SITE_TAGLINE = "Evidence-based medical intelligence";
export const SITE_DESCRIPTION =
  "Evidence-based clinical reference for medical professionals. Searches PubMed, FDA, NICE and other authoritative sources in real time, and grades every claim by the evidence behind it.";

/** Public, indexable pages. Authenticated or user-specific routes are deliberately absent. */
export const PUBLIC_ROUTES = [
  { path: "/", priority: 1.0, changeFrequency: "weekly" as const },
  { path: "/about", priority: 0.8, changeFrequency: "monthly" as const },
  { path: "/lessons", priority: 0.7, changeFrequency: "monthly" as const },
  { path: "/waves", priority: 0.6, changeFrequency: "monthly" as const },
  { path: "/register", priority: 0.5, changeFrequency: "yearly" as const },
  { path: "/login", priority: 0.3, changeFrequency: "yearly" as const },
  { path: "/privacy", priority: 0.3, changeFrequency: "yearly" as const },
  { path: "/terms", priority: 0.3, changeFrequency: "yearly" as const },
];
