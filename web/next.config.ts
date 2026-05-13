import type { NextConfig } from "next";

// I-carney-005 P1-004 + P1-005: standalone output for Docker runner +
// server-side rewrite of /api/v6/* → ${INTERNAL_API_URL}/* so browser
// fetch only talks to the webui container (Next.js then proxies to the
// api container by Docker service name, which the browser can't resolve).
const nextConfig: NextConfig = {
  output: "standalone",
  async rewrites() {
    const internal =
      process.env.INTERNAL_API_URL ||
      process.env.NEXT_PUBLIC_BACKEND_URL ||
      "http://localhost:8000";
    return [
      {
        source: "/api/v6/:path*",
        destination: `${internal}/:path*`,
      },
      // I-carney-003 P1-001: expose FastAPI /transparency directly so
      // reviewers (incl. Carney's office) can audit the deploy without
      // going through /api/v6 prefix routing.
      {
        source: "/transparency",
        destination: `${internal}/transparency`,
      },
      {
        source: "/transparency/:path*",
        destination: `${internal}/transparency/:path*`,
      },
    ];
  },
};

export default nextConfig;
