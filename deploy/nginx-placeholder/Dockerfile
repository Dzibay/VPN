# Универсальный "скоро запустимся" nginx для проектов, у которых ещё нет фронта.
# Один контейнер обслуживает N доменов (Host-агностично, backend определяет проект по X-Forwarded-Host).
# Caddy проксирует конкретный домен сюда, добавив reverse_proxy nginx-placeholder:80.
FROM nginx:1.27-alpine
COPY deploy/nginx-placeholder/nginx.conf /etc/nginx/nginx.conf
COPY deploy/nginx-placeholder/html/ /usr/share/nginx/html/
EXPOSE 80
