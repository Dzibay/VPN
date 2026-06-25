#!/bin/sh
# Миграции один раз до fork uvicorn workers (lifespan в каждом worker → deadlock на DDL).
set -e
python -c "from app.infrastructure.database.schema import ensure_schema; ensure_schema()"
exec uvicorn "$@"
