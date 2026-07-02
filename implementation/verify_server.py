"""Repeatable verification script for the SQLite MCP lab server."""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from db import SQLiteAdapter, ValidationError
from init_db import create_database


def check(name: str, condition: bool, detail: str = "") -> None:
    status = "PASS" if condition else "FAIL"
    suffix = f" - {detail}" if detail else ""
    print(f"[{status}] {name}{suffix}")
    if not condition:
        raise SystemExit(1)


def main() -> None:
    db_path = Path(__file__).resolve().parent / "verify_lab.db"
    create_database(db_path)
    adapter = SQLiteAdapter(db_path)

    tables = adapter.list_tables()
    check("database initialized", set(tables) == {"students", "courses", "enrollments"}, str(tables))

    schema = adapter.get_database_schema()
    check("schema resource data", "students" in schema["tables"])

    cohort_search = adapter.search(
        table="students",
        filters={"cohort": {"eq": "A1"}},
        order_by="score",
        descending=True,
        limit=10,
    )
    check(
        "search with filters and ordering",
        len(cohort_search["rows"]) == 3 and cohort_search["rows"][0]["name"] == "Eva Hoang",
        json.dumps(cohort_search["rows"], ensure_ascii=False),
    )

    inserted = adapter.insert(
        table="students",
        values={"name": "Verify Student", "cohort": "A1", "score": 84.0},
    )
    check(
        "insert returns payload",
        inserted["inserted"]["name"] == "Verify Student" and inserted["inserted"]["id"] is not None,
    )

    avg_by_cohort = adapter.aggregate(
        table="students",
        metric="avg",
        column="score",
        group_by="cohort",
    )
    check(
        "aggregate avg by cohort",
        len(avg_by_cohort["results"]) >= 2,
        json.dumps(avg_by_cohort["results"], ensure_ascii=False),
    )

    count_all = adapter.aggregate(table="students", metric="count")
    check("aggregate count", count_all["results"][0]["value"] >= 6)

    try:
        adapter.search(table="missing_table")
        check("invalid table rejected", False)
    except ValidationError as exc:
        check("invalid table rejected", "Unknown table" in str(exc), str(exc))

    try:
        adapter.search(table="students", filters={"bad_column": {"eq": 1}})
        check("invalid column rejected", False)
    except ValidationError as exc:
        check("invalid column rejected", "Unknown column" in str(exc), str(exc))

    try:
        adapter.aggregate(table="students", metric="median", column="score")
        check("invalid metric rejected", False)
    except ValidationError as exc:
        check("invalid metric rejected", "Unsupported metric" in str(exc), str(exc))

    try:
        adapter.insert(table="students", values={})
        check("empty insert rejected", False)
    except ValidationError as exc:
        check("empty insert rejected", "cannot be empty" in str(exc), str(exc))

    print("\nAll verification checks passed.")


if __name__ == "__main__":
    main()
