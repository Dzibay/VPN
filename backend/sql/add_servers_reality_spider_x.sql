-- REALITY spiderX (путь к dest для «паучка»). Выполнить один раз на существующей БД.
ALTER TABLE servers ADD COLUMN IF NOT EXISTS reality_spider_x TEXT NOT NULL DEFAULT '/';
