# I-carney-005 — POLARIS webui (Next.js 16) production image.
#
# Multi-stage build: deps → builder → runner with .next/standalone output.
# Per memory next_16_breaking_changes.md, Next 16 has standalone output that
# bundles only the minimum runtime deps; runner stage is tiny.
#
# Codex diff iter-1+2 P1-B: NEXT_PUBLIC_BACKEND_URL is intentionally NOT a
# build arg. Baking it would freeze an absolute URL (e.g., http://api:8000,
# a Docker service hostname) into the client bundle and break production
# browsers. Instead:
#   - web/lib/api.ts hard-codes `/api/v6` for browser-relative fetch.
#   - INTERNAL_API_URL (server-side only) is a BUILD ARG; Next.js evaluates
#     rewrites() destinations during `next build` and bakes them into the
#     standalone routes manifest, so this MUST be set at build time. NOT
#     prefixed NEXT_PUBLIC_, so it does NOT leak into the client bundle.

# ----------- Stage 1: deps -----------
FROM node:20-alpine AS deps
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci --no-audit --no-fund

# ----------- Stage 2: builder -----------
FROM node:20-alpine AS builder
WORKDIR /app
# Codex diff iter-2 P1-B (continuing): Next.js evaluates rewrites()
# DESTINATIONS at build time and bakes them into the routes manifest.
# INTERNAL_API_URL must therefore be a build arg, not a runtime env. It is
# NOT prefixed with NEXT_PUBLIC_, so it does NOT leak into the client bundle
# — only the server-side route table sees it. Compose sets the build arg to
# `http://api:8000` via build.args.INTERNAL_API_URL.
ARG INTERNAL_API_URL=http://api:8000
ENV INTERNAL_API_URL=${INTERNAL_API_URL}
COPY --from=deps /app/node_modules ./node_modules
COPY . .
RUN npm run build

# ----------- Stage 3: runner -----------
FROM node:20-alpine AS runner
WORKDIR /app
ENV NODE_ENV=production
ENV PORT=3000
# I-cd-001 / #494: Next.js standalone server.js binds to $HOSTNAME; the default
# resolves to IPv6 ::1, but the healthcheck + Caddy reach it on IPv4. Force
# 0.0.0.0 so 127.0.0.1 (healthcheck) and webui:3000 (Caddy) both connect.
ENV HOSTNAME=0.0.0.0
# I-ux-001a Codex iter-2 P1: the server-side GPG verifier
# (web/lib/gpg_verify_bundle.ts) shells out to gpg + gpgv to verify the
# audit-bundle signature against a BAKED-IN trust root (the pubkey is public
# per docs/carney_secret_inventory.md #1). Install gnupg (gpg + gpgv on
# Alpine) so the verifier path works in production — without it every signed
# bundle silently degrades to `present_unverified` and the inspector never
# renders the green "Signed bundle" pill.
RUN apk add --no-cache gnupg
# Standalone output: contains a minimal server.js + only the deps needed
# to run it. Requires output: 'standalone' in next.config.ts (P1-004).
COPY --from=builder /app/.next/standalone ./
COPY --from=builder /app/.next/static ./.next/static
COPY --from=builder /app/public ./public

EXPOSE 3000

# Healthcheck via wget --spider (busybox alpine built-in).
HEALTHCHECK --interval=30s --timeout=10s --start-period=20s --retries=3 \
    CMD wget --spider -q http://127.0.0.1:3000/ || exit 1

CMD ["node", "server.js"]
