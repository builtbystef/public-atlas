import type { NextConfig } from "next";

import path from "node:path";

// The browser's `/api/*` requests reach the API through src/proxy.ts, which reads `API_URL`
// at run time.
const nextConfig: NextConfig = {
  // Routes prerender a static shell; uncached reads stream behind <Suspense>.
  cacheComponents: true,
  // The sidebar's Settings link sits bottom-left; keep the dev badge off it.
  devIndicators: { position: "bottom-right" },
  typedRoutes: true,
  // The saved lists are the front page.
  redirects: async () => [{ source: "/", destination: "/lists", permanent: false }],
  reactCompiler: true,
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
