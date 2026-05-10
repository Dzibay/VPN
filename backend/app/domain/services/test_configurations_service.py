"""Загрузка тестовых конфигураций из backend/configurations/test_configurations.json."""

from __future__ import annotations

import json
import logging
from pathlib import Path

from pydantic import ValidationError

from app.domain.models.test_configurations import TestConfigurationItem

log = logging.getLogger(__name__)


def _backend_root() -> Path:
    # backend/app/domain/services/ → …/backend
    return Path(__file__).resolve().parent.parent.parent.parent


def default_test_configurations_json_path() -> Path:
    return _backend_root() / "configurations" / "test_configurations.json"


def load_test_configurations(path: Path | None = None) -> list[TestConfigurationItem]:
    """Читает JSON с диска. Пустой или отсутствующий файл — пустой список."""

    p = path or default_test_configurations_json_path()
    if not p.is_file():
        log.warning("test configurations file missing: %s", p)
        return []

    raw_text = p.read_text(encoding="utf-8")
    stripped = raw_text.strip()
    if not stripped:
        return []

    try:
        data = json.loads(stripped)
    except json.JSONDecodeError as e:
        log.exception("invalid JSON in test configurations file %s", p)
        raise ValueError(f"invalid_test_configurations_json: {e}") from e

    if isinstance(data, dict) and "items" in data:
        data = data["items"]

    if not isinstance(data, list):
        raise ValueError("test_configurations_root_must_be_array_or_items_object")

    items: list[TestConfigurationItem] = []
    for i, row in enumerate(data):
        if not isinstance(row, dict):
            log.warning("skip test configuration entry %s: not an object", i)
            continue
        try:
            items.append(TestConfigurationItem.model_validate(row))
        except ValidationError as err:
            log.warning("skip test configuration entry %s: %s", i, err)

    return items
