-- Опускание трафика до users.traffic_limit_bytes.
--
-- Если сумма последних снимков (по каждому server_id) > лимита:
--   все строки user_server_traffic этого пользователя × (лимит / сумма),
--   up/down в той же пропорции → без просадок на графике (форму ряда сохраняем).
--
-- Запуск (из каталога deploy):
--   docker compose exec -T postgres psql -U vpn -d vpn -v ON_ERROR_STOP=1 -f - < scripts/cap_traffic_to_user_limit.sql
--
-- Dry-run: закомментируйте блок UPDATE и раскомментируйте SELECT preview.

SET statement_timeout = '600s';

BEGIN;

CREATE TEMP TABLE _over_limit ON COMMIT DROP AS
WITH latest AS (
    SELECT DISTINCT ON (user_id, server_id)
        user_id,
        up_bytes + down_bytes AS total
    FROM user_server_traffic
    ORDER BY user_id, server_id, traffic_date DESC
),
used AS (
    SELECT user_id, SUM(total)::bigint AS used_bytes
    FROM latest
    GROUP BY user_id
)
SELECT
    u.id AS user_id,
    u.traffic_limit_bytes AS limit_bytes,
    us.used_bytes
FROM users u
INNER JOIN used us ON us.user_id = u.id
WHERE u.traffic_limit_bytes IS NOT NULL
  AND u.traffic_limit_bytes > 0
  AND us.used_bytes > u.traffic_limit_bytes;

-- SELECT user_id, limit_bytes, used_bytes,
--        ROUND(limit_bytes::numeric * 100.0 / used_bytes, 2) AS pct_of_limit
-- FROM _over_limit ORDER BY used_bytes DESC;

CREATE TEMP TABLE _apply ON COMMIT DROP AS
SELECT
    ust.user_id,
    ust.server_id,
    ust.traffic_date,
    FLOOR(
        (ust.up_bytes + ust.down_bytes)::numeric
        * o.limit_bytes::numeric
        / o.used_bytes::numeric
    )::bigint AS new_total,
    ust.up_bytes,
    ust.down_bytes
FROM user_server_traffic ust
INNER JOIN _over_limit o ON o.user_id = ust.user_id;

CREATE TEMP TABLE _apply2 ON COMMIT DROP AS
SELECT
    user_id,
    server_id,
    traffic_date,
    new_total,
    CASE
        WHEN up_bytes + down_bytes > 0
            THEN FLOOR(
                new_total::numeric * up_bytes::numeric / (up_bytes + down_bytes)::numeric
            )::bigint
        ELSE new_total / 2
    END AS new_up
FROM _apply
WHERE new_total >= 0;

-- Округление могло дать просадку на 1–2 байта — подтянуть до prev (не выше scaled)
CREATE TEMP TABLE _apply3 ON COMMIT DROP AS
SELECT
    user_id,
    server_id,
    traffic_date,
    GREATEST(
        new_total,
        COALESCE(
            MAX(new_total) OVER (
                PARTITION BY user_id, server_id
                ORDER BY traffic_date
                ROWS BETWEEN UNBOUNDED PRECEDING AND 1 PRECEDING
            ),
            0
        )
    )::bigint AS new_total,
    new_up,
    up_bytes,
    down_bytes
FROM _apply2;

CREATE TEMP TABLE _final ON COMMIT DROP AS
SELECT
    user_id,
    server_id,
    traffic_date,
    new_total,
    CASE
        WHEN up_bytes + down_bytes > 0
            THEN FLOOR(
                new_total::numeric * up_bytes::numeric / (up_bytes + down_bytes)::numeric
            )::bigint
        ELSE new_total / 2
    END AS new_up
FROM _apply3;

UPDATE user_server_traffic u
SET
    up_bytes = f.new_up,
    down_bytes = f.new_total - f.new_up
FROM _final f
WHERE u.user_id = f.user_id
  AND u.server_id = f.server_id
  AND u.traffic_date = f.traffic_date
  AND (u.up_bytes + u.down_bytes) IS DISTINCT FROM f.new_total;

SELECT COUNT(*) AS users_capped FROM _over_limit;
SELECT COUNT(*) AS rows_touched FROM _final;

COMMIT;
