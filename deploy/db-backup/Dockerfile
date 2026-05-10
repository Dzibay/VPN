# Ежедневный pg_dump на Яндекс Диск (WebDAV). Запуск: docker compose --profile backup up -d
FROM postgres:16-alpine

# rclone в репозитории community для версии Alpine базового образа
RUN ALPINE_MINOR=$(awk -F. '{print "v"$1"."$2}' /etc/alpine-release) \
  && apk add --no-cache --repository="https://dl-cdn.alpinelinux.org/alpine/${ALPINE_MINOR}/community" \
    bash rclone

COPY backup.sh /usr/local/bin/db-backup
COPY entrypoint.sh /usr/local/bin/db-backup-entrypoint
RUN chmod +x /usr/local/bin/db-backup /usr/local/bin/db-backup-entrypoint

# UTC. Время: CRON (минуты часы день месяц день_недели)
ARG BACKUP_CRON="15 3 * * *"
RUN echo "${BACKUP_CRON} /usr/local/bin/db-backup >> /var/log/db-backup.log 2>&1" > /etc/crontabs/root \
  && chmod 600 /etc/crontabs/root \
  && touch /var/log/db-backup.log

ENTRYPOINT ["/usr/local/bin/db-backup-entrypoint"]
USER root
