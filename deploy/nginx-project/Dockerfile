# Per-project nginx: собирает frontend-projects/<slug>/ (Vite) и подаёт SPA + /api.
# Args:
#   PROJECT_SLUG    — имя папки внутри frontend-projects/ (например 'acme').
#   SITE_ADDRESS    — основной домен проекта (для canonical/sitemap/og).
# node:22-alpine ломает npm ci ("Exit handler never called") — используем Debian slim.
FROM node:22-bookworm-slim AS frontend-build
ARG PROJECT_SLUG
ARG SITE_ADDRESS
ENV SITE_ADDRESS=$SITE_ADDRESS

WORKDIR /build
# Копируем именно проектный форк.
COPY frontend-projects/${PROJECT_SLUG}/package.json frontend-projects/${PROJECT_SLUG}/package-lock.json* ./
RUN if [ -f package-lock.json ]; then npm ci --no-audit --no-fund; else npm install --no-audit --no-fund; fi
COPY frontend-projects/${PROJECT_SLUG}/ ./
RUN set -eu; \
    host="${SITE_ADDRESS#https://}"; \
    host="${host#http://}"; \
    host="${host%%/*}"; \
    case "$host" in localhost*|127.*|0.0.0.0*) scheme=http ;; *) scheme=https ;; esac; \
    export VITE_PUBLIC_SITE_URL="${scheme}://${host}"; \
    export VITE_SUBSCRIPTION_BASE_URL="${VITE_PUBLIC_SITE_URL}"; \
    npm run build

FROM nginx:1.27-alpine
# Проектный nginx использует тот же nginx.conf (SPA + /api), что и основной.
COPY deploy/nginx/nginx.conf /etc/nginx/nginx.conf
COPY --from=frontend-build /build/dist /usr/share/nginx/html
EXPOSE 80
