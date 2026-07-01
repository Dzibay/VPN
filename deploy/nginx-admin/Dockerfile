# Сборка frontend-admin (Vite) + Nginx для админ-домена admin.<your-domain>.
FROM node:22-alpine AS admin-build
WORKDIR /build
COPY frontend-admin/package.json frontend-admin/package-lock.json* ./
RUN if [ -f package-lock.json ]; then npm ci; else npm install; fi
COPY frontend-admin/ ./
# frontend-admin — SPA, ходит по абсолютным путям /api/*; SITE_URL здесь не нужен.
RUN npm run build

FROM nginx:1.27-alpine
COPY deploy/nginx-admin/nginx.conf /etc/nginx/nginx.conf
COPY --from=admin-build /build/dist /usr/share/nginx/html
EXPOSE 80
