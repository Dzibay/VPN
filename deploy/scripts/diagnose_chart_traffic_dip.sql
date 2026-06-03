-- Симуляция графика «Накопительный трафик по дням» и поиск просадок суммы.
-- Запуск: psql -v user_id=123 -f diagnose_chart_traffic_dip.sql
-- (подставьте id пользователя с графика)

-- \set user_id 1

WITH per_server AS (
    SELECT
        user_id,
        server_id,
        traffic_date,
        up_bytes + down_bytes AS total
    FROM user_server_traffic
    WHERE user_id = :user_id
),
markers AS (
    SELECT DISTINCT traffic_date
    FROM per_server
),
grid AS (
    SELECT
        m.traffic_date,
        s.server_id,
        (
            SELECT p.total
            FROM per_server p
            WHERE p.server_id = s.server_id
              AND p.traffic_date = (
                  SELECT MAX(p2.traffic_date)
                  FROM per_server p2
                  WHERE p2.server_id = s.server_id
                    AND p2.traffic_date <= m.traffic_date
              )
        ) AS contrib
    FROM markers m
    CROSS JOIN (SELECT DISTINCT server_id FROM per_server) s
),
chart AS (
    SELECT
        traffic_date,
        COALESCE(SUM(contrib), 0) AS chart_total
    FROM grid
    GROUP BY traffic_date
),
with_prev AS (
    SELECT
        traffic_date,
        chart_total,
        LAG(chart_total) OVER (ORDER BY traffic_date) AS prev_chart
    FROM chart
)
SELECT
    traffic_date,
    chart_total,
    prev_chart,
    chart_total - prev_chart AS delta
FROM with_prev
WHERE prev_chart IS NOT NULL AND chart_total < prev_chart
ORDER BY traffic_date;

-- По узлам в дни просадки (подставьте дату из вывода выше):
-- \set dip_date '2026-05-28'
-- SELECT server_id, traffic_date, up_bytes, down_bytes, up_bytes + down_bytes AS total
-- FROM user_server_traffic
-- WHERE user_id = :user_id AND traffic_date >= '2026-05-25' AND traffic_date <= '2026-05-30'
-- ORDER BY server_id, traffic_date;
