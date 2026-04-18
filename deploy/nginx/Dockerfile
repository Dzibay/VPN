# Сборка Vue (Vite) + Nginx: статика и reverse proxy к API
FROM node:22-alpine AS frontend-build
WORKDIR /build
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

FROM nginx:1.27-alpine
COPY deploy/nginx/nginx.conf /etc/nginx/nginx.conf
COPY --from=frontend-build /build/dist /usr/share/nginx/html
EXPOSE 80
