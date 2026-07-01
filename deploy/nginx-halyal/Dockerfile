# Halyal VPN: отдельный Vue SPA + прокси /api и /sub на backend.
FROM node:22-bookworm-slim AS frontend-build
ARG SITE_ADDRESS=halyal-connect.ru
ENV SITE_ADDRESS=$SITE_ADDRESS
ENV VITE_DISABLE_SEO_PAGES=true
WORKDIR /build
COPY frontend-halyal/package.json frontend-halyal/package-lock.json* ./
RUN if [ -f package-lock.json ]; then npm ci --no-audit --no-fund; else npm install --no-audit --no-fund; fi
COPY frontend-halyal/ ./
RUN set -eu; \
    host="${SITE_ADDRESS#https://}"; \
    host="${host#http://}"; \
    host="${host%%/*}"; \
    if [ -n "$host" ]; then \
        case "$host" in localhost*|127.*|0.0.0.0*) scheme=http ;; *) scheme=https ;; esac; \
        export VITE_PUBLIC_SITE_URL="${scheme}://${host}"; \
        export VITE_SUBSCRIPTION_BASE_URL="${VITE_PUBLIC_SITE_URL}"; \
    fi; \
    npm run build

FROM nginx:1.27-alpine
COPY deploy/nginx-halyal/nginx.conf /etc/nginx/nginx.conf
COPY --from=frontend-build /build/dist /usr/share/nginx/html
EXPOSE 80
