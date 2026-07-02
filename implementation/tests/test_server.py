"""Tests for SQLite adapter validation and queries."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from db import SQLiteAdapter, ValidationError
from init_db import create_database


@pytest.fixture
def adapter(tmp_path):
    db_path = tmp_path / "test.db"
    create_database(db_path)
    return SQLiteAdapter(db_path)


def test_list_tables(adapter):
    assert adapter.list_tables() == ["courses", "enrollments", "students"]


def test_search_with_filters(adapter):
    result = adapter.search(
        table="students",
        filters={"cohort": {"eq": "A1"}},
        order_by="score",
        descending=True,
    )
    assert result["total"] == 3
    assert result["rows"][0]["name"] == "Eva Hoang"


def test_insert_returns_row(adapter):
    result = adapter.insert(
        table="students",
        values={"name": "Test User", "cohort": "B2", "score": 66.0},
    )
    assert result["inserted"]["id"] is not None
    assert result["inserted"]["name"] == "Test User"


def test_aggregate_count(adapter):
    result = adapter.aggregate(table="students", metric="count")
    assert result["results"][0]["value"] == 5


def test_aggregate_avg_group_by(adapter):
    result = adapter.aggregate(
        table="students",
        metric="avg",
        column="score",
        group_by="cohort",
    )
    groups = {item["group"]: item["value"] for item in result["results"]}
    assert "A1" in groups
    assert "B2" in groups


def test_unknown_table(adapter):
    with pytest.raises(ValidationError, match="Unknown table"):
        adapter.search(table="does_not_exist")


def test_unknown_column(adapter):
    with pytest.raises(ValidationError, match="Unknown column"):
        adapter.search(table="students", filters={"missing": {"eq": 1}})


def test_unsupported_operator(adapter):
    with pytest.raises(ValidationError, match="Unsupported operator"):
        adapter.search(table="students", filters={"cohort": {"contains": "A1"}})


def test_empty_insert(adapter):
    with pytest.raises(ValidationError, match="cannot be empty"):
        adapter.insert(table="students", values={})


def test_invalid_metric(adapter):
    with pytest.raises(ValidationError, match="Unsupported metric"):
        adapter.aggregate(table="students", metric="median", column="score")
