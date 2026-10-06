# The Next.js console. Build from the repository root, where the pnpm workspace and lockfile
# live:
#
#   docker build --file apps/web/Dockerfile --build-arg API_URL=http://api:8000 --tag public-atlas-web .
#
# `API_URL` is where the API lives. The browser's `/api/*` requests reach it through a rewrite
# (next.config.ts) that Next.js fixes at build time, so the address is a build argument; the
# server-side client reads the same variable at run time.

# --- Dependencies -------------------------------------------------------------
# The Node version from .node-version. pnpm is the version pinned in package.json
# "packageManager"; Corepack is deprecated, so npm installs it.
FROM node:24.18.0-bookworm-slim AS deps

RUN npm install --global pnpm@12.3.4

WORKDIR /app

# Manifests only, so the install layer survives source changes. The filter installs
# @public-atlas/web and the workspace packages it depends on.
COPY package.json pnpm-lock.yaml pnpm-workspace.yaml ./
COPY apps/web/package.json apps/web/package.json
COPY packages/api-client/package.json packages/api-client/package.json
RUN --mount=type=cache,id=pnpm,target=/root/.local/share/pnpm/store \
    pnpm install --frozen-lockfile --filter "@public-atlas/web..."

# --- Build --------------------------------------------------------------------
FROM deps AS build

ARG API_URL=http://api:8000
ENV API_URL=$API_URL \
    NEXT_TELEMETRY_DISABLED=1

COPY tsconfig tsconfig
COPY packages/api-client packages/api-client
COPY apps/web apps/web

# `output: "standalone"` in next.config.ts writes a self-contained server with only the files
# it traced into .next/standalone.
RUN pnpm --filter @public-atlas/web exec next build

# --- Runtime ------------------------------------------------------------------
FROM node:24.18.0-bookworm-slim AS runtime

ARG API_URL=http://api:8000
ENV NODE_ENV=production \
    NEXT_TELEMETRY_DISABLED=1 \
    HOSTNAME=0.0.0.0 \
    PORT=3000 \
    API_URL=$API_URL

WORKDIR /app

# The standalone output mirrors the monorepo layout, so server.js lands under apps/web. Static
# assets and public/ are not traced and are copied alongside.
COPY --from=build --chown=node:node /app/apps/web/.next/standalone ./
COPY --from=build --chown=node:node /app/apps/web/.next/static ./apps/web/.next/static
COPY --from=build --chown=node:node /app/apps/web/public ./apps/web/public

USER node

EXPOSE 3000

HEALTHCHECK --interval=10s --timeout=3s --start-period=10s --retries=5 \
    CMD ["node", "-e", "fetch('http://127.0.0.1:3000/', {redirect: 'manual'}).then(r => process.exit(r.status < 400 ? 0 : 1), () => process.exit(1))"]

CMD ["node", "apps/web/server.js"]
