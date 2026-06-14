"""Общие утилиты ORDER BY для пагинированных списков админки."""

from __future__ import annotations

from typing import Literal

from sqlalchemy import ColumnElement

SortDir = Literal["asc", "desc"]


def order_clause(column: ColumnElement, sort_dir: SortDir) -> ColumnElement:
    """Сортировка с NULL в конце (для nullable столбцов)."""
    if sort_dir == "asc":
        return column.asc().nulls_last()
    return column.desc().nulls_last()
