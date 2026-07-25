import type { MetadataRoute } from "next";
import { SITE_URL, PUBLIC_ROUTES } from "@/lib/site";

// Generates /sitemap.xml at build time from the single PUBLIC_ROUTES list in lib/site.ts.
// Add new public pages there, not here, so robots/sitemap/metadata never drift apart.
//
// lastModified uses build time rather than a literal date: hardcoding one would go stale
// silently, and Date.now() at module scope is evaluated during `next build`.

export default function sitemap(): MetadataRoute.Sitemap {
  const lastModified = new Date();

  return PUBLIC_ROUTES.map(({ path, priority, changeFrequency }) => ({
    url: `${SITE_URL}${path === "/" ? "" : path}`,
    lastModified,
    changeFrequency,
    priority,
  }));
}
