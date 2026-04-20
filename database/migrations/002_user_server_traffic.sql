-- Накопленный трафик по паре (пользователь, сервер); raw_* — последние сырые счётчики Xray.

CREATE TABLE IF NOT EXISTS user_server_traffic (
    user_id BIGINT NOT NULL REFERENCES users (id) ON DELETE CASCADE,
    server_id BIGINT NOT NULL REFERENCES servers (id) ON DELETE CASCADE,
    up_bytes BIGINT NOT NULL DEFAULT 0,
    down_bytes BIGINT NOT NULL DEFAULT 0,
    raw_up BIGINT NOT NULL DEFAULT 0,
    raw_down BIGINT NOT NULL DEFAULT 0,
    PRIMARY KEY (user_id, server_id)
);

CREATE INDEX IF NOT EXISTS idx_user_server_traffic_server ON user_server_traffic (server_id);
