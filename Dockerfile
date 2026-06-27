# Found-First Missing Persons System — Backend
# Build context = repo root (Claude Lab/). Build with:
#   docker build -t found-first-server .
# Run with:
#   docker run --rm -p 3001:3001 -e NODE_ENV=production found-first-server

# ---------- Build stage ----------
FROM node:20-alpine AS build
WORKDIR /app/server
COPY server/package.json server/package-lock.json* ./
# Use --omit=optional because better-sqlite3 native build needs python+make+gcc
# and we ship with JSON fallback by default. To enable SQLite, build with
# --build-arg WITH_SQLITE=1 (and accept a much larger build).
ARG WITH_SQLITE=0
RUN if [ "$WITH_SQLITE" = "1" ]; then \
        apk add --no-cache python3 make g++ && \
        npm ci --omit=dev --no-audit --no-fund ; \
    else \
        npm ci --omit=dev --omit=optional --no-audit --no-fund ; \
    fi

# ---------- Runtime stage ----------
FROM node:20-alpine AS runtime
ENV NODE_ENV=production
ENV PORT=3001
ENV LOG_LEVEL=info
WORKDIR /app/server

# Non-root user
RUN addgroup -S app && adduser -S app -G app

COPY --from=build /app/server/node_modules ./node_modules
COPY server/package.json server/db.js server/matcher.js server/server.js server/test_matcher.js ./
COPY data /app/data

RUN chown -R app:app /app
USER app

EXPOSE 3001
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD wget --quiet --tries=1 --spider http://localhost:3001/api/health || exit 1

CMD ["node", "server.js"]
