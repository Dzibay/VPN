# Сборка frontend-admin (Vite) + Nginx для админ-домена.
# node:22-alpine ломает npm ci ("Exit handler never called") — используем Debian slim.
# Vite-алиасы @legacy-* смотрят в ../frontend/src — копируем оба каталога с сохранением layout.
FROM node:22-bookworm-slim AS admin-build
WORKDIR /workspace

COPY frontend-admin/package.json frontend-admin/package-lock.json* frontend-admin/
WORKDIR /workspace/frontend-admin
RUN if [ -f package-lock.json ]; then npm ci --no-audit --no-fund; else npm install --no-audit --no-fund; fi

COPY frontend-admin/ ./
COPY frontend/src/ ../frontend/src/

RUN npm run build

FROM nginx:1.27-alpine
COPY deploy/nginx-admin/nginx.conf /etc/nginx/nginx.conf
COPY --from=admin-build /workspace/frontend-admin/dist /usr/share/nginx/html
EXPOSE 80
