# Halyal VPN: статическая заглушка + прокси /api и /sub на backend (бот, подписки).
FROM nginx:1.27-alpine
COPY deploy/nginx-halyal/nginx.conf /etc/nginx/nginx.conf
COPY deploy/nginx-halyal/html/ /usr/share/nginx/html/
EXPOSE 80
