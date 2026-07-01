# Сборка Vue (Vite) + Nginx: статика и reverse proxy к API
# SITE_ADDRESS опционален: если пустой, frontend использует текущий window.location.origin.
# node:22-alpine ломает npm ci ("Exit handler never called") — используем Debian slim.
FROM node:22-bookworm-slim AS frontend-build
ARG SITE_ADDRESS
ARG ADMIN_SITE_ADDRESS
ENV SITE_ADDRESS=$SITE_ADDRESS
ENV ADMIN_SITE_ADDRESS=$ADMIN_SITE_ADDRESS
WORKDIR /build
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY frontend/ ./
# VITE_PUBLIC_SITE_URL задаём только для single-domain сборки.
# VITE_ADMIN_SITE_URL — куда UserLoginView отправит staff-пользователей, попавших на публичный сайт.
RUN set -eu; \
    host="${SITE_ADDRESS#https://}"; \
    host="${host#http://}"; \
    host="${host%%/*}"; \
    if [ -n "$host" ]; then \
        case "$host" in localhost*|127.*|0.0.0.0*) scheme=http ;; *) scheme=https ;; esac; \
        export VITE_PUBLIC_SITE_URL="${scheme}://${host}"; \
        export VITE_SUBSCRIPTION_BASE_URL="${VITE_PUBLIC_SITE_URL}"; \
    fi; \
    if [ -n "${ADMIN_SITE_ADDRESS:-}" ]; then \
        ahost="${ADMIN_SITE_ADDRESS#https://}"; \
        ahost="${ahost#http://}"; \
        ahost="${ahost%%/*}"; \
        case "$ahost" in localhost*|127.*|0.0.0.0*) ascheme=http ;; *) ascheme=https ;; esac; \
        export VITE_ADMIN_SITE_URL="${ascheme}://${ahost}"; \
    fi; \
    npm run build

FROM nginx:1.27-alpine
COPY deploy/nginx/nginx.conf /etc/nginx/nginx.conf
COPY deploy/nginx/docker-entrypoint.sh /docker-entrypoint.sh
RUN chmod +x /docker-entrypoint.sh \
    && mkdir -p /etc/nginx/conf.d
COPY --from=frontend-build /build/dist /usr/share/nginx/html
EXPOSE 80
ENTRYPOINT ["/docker-entrypoint.sh"]
