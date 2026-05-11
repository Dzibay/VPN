#!/bin/sh
set -e
# Prometheus http_sd требует credentials_file; токен тот же, что PROMETHEUS_SD_TOKEN у API (.env).
printf '%s' "${PROMETHEUS_SD_TOKEN:-}" >/etc/prometheus/sd_bearer.txt
exec /bin/prometheus "$@"
