import type { MetadataRoute } from "next";
import { SITE_URL, IS_PRODUCTION_SITE } from "@/lib/site";

// Generates /robots.txt at build time.
//
// Non-production hosts (the public dev site at med.debkay.com) return a blanket
// disallow — see lib/site.ts for why that matters.

export default function robots(): MetadataRoute.Robots {
  if (!IS_PRODUCTION_SITE) {
    return { rules: [{ userAgent: "*", disallow: "/" }] };
  }

  return {
    rules: [
      {
        userAgent: "*",
        allow: "/",
        // Authenticated and user-specific surfaces: nothing to index, and query URLs
        // can carry a user's clinical search terms.
        disallow: ["/api/", "/settings", "/query"],
      },
    ],
    sitemap: `${SITE_URL}/sitemap.xml`,
    host: SITE_URL,
  };
}
