# Сборка Vue (Vite) + Nginx: статика и reverse proxy к API
# SITE_ADDRESS — домен из deploy/.env (как у Caddy); Vite собирает canonical, sitemap, og:*.
FROM node:22-alpine AS frontend-build
ARG SITE_ADDRESS
ENV SITE_ADDRESS=$SITE_ADDRESS
WORKDIR /build
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
# Канонический origin в бандле: ссылки подписки/рефералов не зависят от Host в браузере.
RUN set -eu; \
    host="${SITE_ADDRESS#https://}"; \
    host="${host#http://}"; \
    host="${host%%/*}"; \
    case "$host" in localhost*|127.*|0.0.0.0*) scheme=http ;; *) scheme=https ;; esac; \
    export VITE_PUBLIC_SITE_URL="${scheme}://${host}"; \
    export VITE_SUBSCRIPTION_BASE_URL="${VITE_PUBLIC_SITE_URL}"; \
    npm run build

FROM nginx:1.27-alpine
COPY deploy/nginx/nginx.conf /etc/nginx/nginx.conf
COPY --from=frontend-build /build/dist /usr/share/nginx/html
EXPOSE 80
