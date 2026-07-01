# Halyal VPN: заглушка на / + Vue SPA для /sub/:token/open/:client + прокси /api и /sub на backend.
# node:22-alpine ломает npm ci — используем Debian slim (как deploy/nginx/Dockerfile).
FROM node:22-bookworm-slim AS frontend-build
ARG SITE_ADDRESS=halyal-connect.ru
ENV SITE_ADDRESS=$SITE_ADDRESS
WORKDIR /build
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY frontend/ ./
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
COPY deploy/nginx-halyal/html/ /usr/share/nginx/html/
COPY --from=frontend-build /build/dist /usr/share/nginx/sub-app
EXPOSE 80
