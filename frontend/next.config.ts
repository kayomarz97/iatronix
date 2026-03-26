import type { NextConfig } from "next";

const INTERNAL_API_URL =
  process.env.INTERNAL_API_URL || "http://iatronix-backend:8000";

const nextConfig: NextConfig = {
  output: "standalone",
  async rewrites() {
    return [
      {
        source: "/api/v1/:path*",
        destination: `${INTERNAL_API_URL}/api/v1/:path*`,
      },
    ];
  },
};

export default nextConfig;
