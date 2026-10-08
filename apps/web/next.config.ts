import type { NextConfig } from "next";

import path from "node:path";

/**
 * Where the API lives, for the `/api` rewrite below. Next.js fixes rewrites at build time, so
 * this is read when `next build` (or `next dev`) runs: a build argument in apps/web/Dockerfile,
 * `.env.local` in development. The server-side client (src/lib/api/server-client.ts) reads the
 * same variable at run time.
 */
const API_URL = process.env["API_URL"] ?? "http://127.0.0.1:8000";

const nextConfig: NextConfig = {
  // Routes prerender a static shell; uncached reads stream behind <Suspense>.
  cacheComponents: true,
  // The sidebar's Settings link sits bottom-left; keep the dev badge off it.
  devIndicators: { position: "bottom-right" },
  typedRoutes: true,
  reactCompiler: true,
  // The browser reaches the API through this same-origin path, so it needs neither the API's
  // address nor a CORS setup. The API's routes have no trailing slash (a rewrite would drop
  // one), and it does not redirect on a missing or extra slash.
  rewrites: async () => [{ source: "/api/:path*", destination: `${API_URL}/:path*` }],
  // apps/web/Dockerfile copies .next/standalone: a server.js plus only the files it traced. The
  // tracing root is the monorepo root, so workspace packages (@public-atlas/api-client) and
  // hoisted node_modules are included.
  output: "standalone",
  outputFileTracingRoot: path.join(import.meta.dirname, "../.."),
  // Nothing here needs framing or sniffing. HSTS is ignored over plain HTTP, so it is harmless
  // in development.
  headers: async () => [
    {
      source: "/(.*)",
      headers: [
        { key: "X-Content-Type-Options", value: "nosniff" },
        { key: "X-Frame-Options", value: "DENY" },
        { key: "Referrer-Policy", value: "strict-origin-when-cross-origin" },
        { key: "Strict-Transport-Security", value: "max-age=31536000; includeSubDomains" },
      ],
    },
  ],
};

export default nextConfig;
