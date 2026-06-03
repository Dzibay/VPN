-- 2-й проход: просадка на ГРАФИКЕ (сумма по узлам), хотя по каждому server_id LAG уже OK.
-- Снижает вклад узла в день chart_dip: линейно между якорём и днём падения суммы.
-- Запускать после smooth_traffic_spikes.sql, пока UPDATE не 0.

SET statement_timeout = '600s';

BEGIN;

CREATE TEMP TABLE _chart_dips ON COMMIT DROP AS
WITH per_server AS (
    SELECT user_id, server_id, traffic_date, up_bytes + down_bytes AS total
    FROM user_server_traffic
),
markers AS (
    SELECT DISTINCT user_id, traffic_date FROM per_server
),
grid AS (
    SELECT
        m.user_id,
        m.traffic_date,
        s.server_id,
        (
            SELECT p.total
            FROM per_server p
            WHERE p.user_id = m.user_id
              AND p.server_id = s.server_id
              AND p.traffic_date = (
                  SELECT MAX(p2.traffic_date)
                  FROM per_server p2
                  WHERE p2.user_id = m.user_id
                    AND p2.server_id = s.server_id
                    AND p2.traffic_date <= m.traffic_date
              )
        ) AS contrib
    FROM markers m
    INNER JOIN (SELECT DISTINCT user_id, server_id FROM per_server) s
        ON s.user_id = m.user_id
),
chart AS (
    SELECT user_id, traffic_date, COALESCE(SUM(contrib), 0)::bigint AS chart_total
    FROM grid
    GROUP BY user_id, traffic_date
),
with_prev AS (
    SELECT
        user_id,
        traffic_date,
        chart_total,
        LAG(chart_total) OVER (PARTITION BY user_id ORDER BY traffic_date) AS prev_chart,
        LAG(traffic_date) OVER (PARTITION BY user_id ORDER BY traffic_date) AS prev_date
    FROM chart
)
SELECT user_id, traffic_date AS dip_date, prev_date, chart_total AS dip_total, prev_chart AS prev_total
FROM with_prev
WHERE prev_chart IS NOT NULL AND chart_total < prev_chart;

CREATE TEMP TABLE _to_fix ON COMMIT DROP AS
WITH per_server AS (
    SELECT user_id, server_id, traffic_date, up_bytes, down_bytes, up_bytes + down_bytes AS total
    FROM user_server_traffic
),
grid AS (
    SELECT
        cd.user_id,
        cd.dip_date,
        cd.prev_date,
        cd.prev_total,
        cd.dip_total,
        s.server_id,
        (
            SELECT p.total
            FROM per_server p
            WHERE p.user_id = cd.user_id AND p.server_id = s.server_id
              AND p.traffic_date = (
                  SELECT MAX(p2.traffic_date)
                  FROM per_server p2
                  WHERE p2.user_id = cd.user_id AND p2.server_id = s.server_id
                    AND p2.traffic_date <= cd.prev_date
              )
        ) AS contrib_prev,
        (
            SELECT p.total
            FROM per_server p
            WHERE p.user_id = cd.user_id AND p.server_id = s.server_id
              AND p.traffic_date = (
                  SELECT MAX(p2.traffic_date)
                  FROM per_server p2
                  WHERE p2.user_id = cd.user_id AND p2.server_id = s.server_id
                    AND p2.traffic_date <= cd.dip_date
              )
        ) AS contrib_dip
    FROM _chart_dips cd
    CROSS JOIN LATERAL (
        SELECT DISTINCT server_id FROM per_server p WHERE p.user_id = cd.user_id
    ) s
),
fallen AS (
    SELECT *
    FROM grid
    WHERE contrib_dip IS NOT NULL
      AND contrib_prev IS NOT NULL
      AND contrib_dip < contrib_prev
),
base AS (
    SELECT
        u.user_id,
        u.server_id,
        u.traffic_date,
        u.up_bytes,
        u.down_bytes,
        u.up_bytes + u.down_bytes AS total,
        ROW_NUMBER() OVER (
            PARTITION BY u.user_id, u.server_id ORDER BY u.traffic_date
        ) AS rn
    FROM user_server_traffic u
    INNER JOIN (SELECT DISTINCT user_id, server_id FROM fallen) f
        USING (user_id, server_id)
),
targets AS (
    SELECT
        f.user_id,
        f.server_id,
        f.dip_date,
        f.prev_total AS chart_prev,
        f.dip_total AS chart_dip,
        MAX(b.rn) FILTER (WHERE b.traffic_date <= f.prev_date AND b.total < f.dip_total) AS anchor_rn,
        MAX(b.rn) FILTER (WHERE b.traffic_date = f.dip_date) AS drop_rn
    FROM fallen f
    INNER JOIN base b
        ON b.user_id = f.user_id AND b.server_id = f.server_id
    GROUP BY f.user_id, f.server_id, f.dip_date, f.prev_total, f.dip_total
    HAVING MAX(b.rn) FILTER (WHERE b.traffic_date = f.dip_date) IS NOT NULL
),
calc AS (
    SELECT
        s.user_id,
        s.server_id,
        s.traffic_date,
        s.up_bytes,
        s.down_bytes,
        FLOOR(
            a.total::numeric
            + (t.chart_dip::numeric - a.total::numeric)
              * (s.rn - t.anchor_rn)::numeric
              / NULLIF(t.drop_rn - t.anchor_rn, 0)::numeric
        )::bigint AS new_total
    FROM targets t
    INNER JOIN base a
        ON a.user_id = t.user_id AND a.server_id = t.server_id AND a.rn = t.anchor_rn
    INNER JOIN base s
        ON s.user_id = t.user_id AND s.server_id = t.server_id
       AND s.rn > t.anchor_rn AND s.rn <= t.drop_rn
       AND s.total > t.chart_dip
    WHERE t.anchor_rn IS NOT NULL
      AND t.drop_rn > t.anchor_rn
),
final AS (
    SELECT
        user_id,
        server_id,
        traffic_date,
        new_total,
        CASE
            WHEN up_bytes + down_bytes > 0
                THEN FLOOR(new_total::numeric * up_bytes::numeric / (up_bytes + down_bytes)::numeric)::bigint
            ELSE new_total / 2
        END AS new_up
    FROM calc
)
UPDATE user_server_traffic u
SET
    up_bytes = f.new_up,
    down_bytes = f.new_total - f.new_up
FROM final f
WHERE u.user_id = f.user_id
  AND u.server_id = f.server_id
  AND u.traffic_date = f.traffic_date
  AND (u.up_bytes + u.down_bytes) IS DISTINCT FROM f.new_total;

SELECT COUNT(*) AS chart_dips_found FROM _chart_dips;

COMMIT;
