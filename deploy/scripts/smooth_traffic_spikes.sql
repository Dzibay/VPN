-- Сглаживание пиков в user_server_traffic (один проход).
-- Логика: при падении total находим якорь (последний день с total < падения),
-- дни между якорем и падением с total > падения — линейная интерполяция.
-- Запускать несколько раз, пока UPDATE не вернёт 0.
--   docker compose exec -T postgres psql -U vpn -d vpn -v ON_ERROR_STOP=1 -f /scripts/smooth_traffic_spikes.sql
-- Или из stdin (см. README в ответе агента).

SET statement_timeout = '600s';

BEGIN;

CREATE TEMP TABLE _pairs ON COMMIT DROP AS
SELECT DISTINCT user_id, server_id
FROM (
    SELECT
        user_id,
        server_id,
        up_bytes + down_bytes AS total,
        LAG(up_bytes + down_bytes) OVER (
            PARTITION BY user_id, server_id ORDER BY traffic_date
        ) AS prev_total
    FROM user_server_traffic
) t
WHERE prev_total IS NOT NULL AND total < prev_total;

WITH base AS (
    SELECT
        u.user_id,
        u.server_id,
        u.traffic_date,
        u.up_bytes,
        u.down_bytes,
        u.up_bytes + u.down_bytes AS total,
        ROW_NUMBER() OVER (
            PARTITION BY u.user_id, u.server_id ORDER BY u.traffic_date
        ) AS rn,
        LAG(u.up_bytes + u.down_bytes) OVER (
            PARTITION BY u.user_id, u.server_id ORDER BY u.traffic_date
        ) AS prev_total
    FROM user_server_traffic u
    INNER JOIN _pairs p USING (user_id, server_id)
),
drops AS (
    SELECT user_id, server_id, rn AS drop_rn, total AS drop_total
    FROM base
    WHERE rn > 1 AND total < prev_total
),
anchors AS (
    SELECT
        d.user_id,
        d.server_id,
        d.drop_rn,
        d.drop_total,
        MAX(a.rn) AS anchor_rn
    FROM drops d
    INNER JOIN base a
        ON a.user_id = d.user_id
       AND a.server_id = d.server_id
       AND a.rn < d.drop_rn
       AND a.total < d.drop_total
    GROUP BY d.user_id, d.server_id, d.drop_rn, d.drop_total
),
to_fix AS (
    SELECT
        d.user_id,
        d.server_id,
        s.traffic_date,
        s.up_bytes,
        s.down_bytes,
        a.total
            + ((d.drop_total - a.total) * (s.rn - d.anchor_rn) / (d.drop_rn - d.anchor_rn)) AS new_total
    FROM anchors d
    INNER JOIN base a
        ON a.user_id = d.user_id
       AND a.server_id = d.server_id
       AND a.rn = d.anchor_rn
    INNER JOIN base s
        ON s.user_id = d.user_id
       AND s.server_id = d.server_id
       AND s.rn > d.anchor_rn
       AND s.rn < d.drop_rn
       AND s.total > d.drop_total
    WHERE d.drop_rn > d.anchor_rn
),
calc AS (
    SELECT
        user_id,
        server_id,
        traffic_date,
        new_total,
        CASE
            WHEN up_bytes + down_bytes > 0
                THEN (new_total * up_bytes / (up_bytes + down_bytes))::bigint
            ELSE new_total / 2
        END AS new_up
    FROM to_fix
)
UPDATE user_server_traffic u
SET
    up_bytes = c.new_up,
    down_bytes = c.new_total - c.new_up
FROM calc c
WHERE u.user_id = c.user_id
  AND u.server_id = c.server_id
  AND u.traffic_date = c.traffic_date
  AND (u.up_bytes + u.down_bytes) IS DISTINCT FROM c.new_total;

SELECT COUNT(*) AS pairs_with_dip FROM _pairs;

COMMIT;
