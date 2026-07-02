"""SQLite database adapter with validation and safe parameterized queries."""

from __future__ import annotations

import re
import sqlite3
from pathlib import Path
from typing import Any

from init_db import DB_PATH, create_database

IDENTIFIER_PATTERN = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
ALLOWED_METRICS = {"count", "avg", "sum", "min", "max"}
ALLOWED_OPERATORS = {"eq", "ne", "gt", "gte", "lt", "lte", "like", "in"}
OPERATOR_SQL = {
    "eq": "=",
    "ne": "!=",
    "gt": ">",
    "gte": ">=",
    "lt": "<",
    "lte": "<=",
    "like": "LIKE",
    "in": "IN",
}


class ValidationError(Exception):
    """Raised when a request cannot be safely executed."""


class SQLiteAdapter:
    """SQLite access layer with identifier validation and parameterized SQL."""

    def __init__(self, db_path: Path | str | None = None):
        self.db_path = Path(db_path) if db_path else DB_PATH
        if not self.db_path.exists():
            create_database(self.db_path)

    def connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def list_tables(self) -> list[str]:
        with self.connect() as conn:
            rows = conn.execute(
                """
                SELECT name FROM sqlite_master
                WHERE type = 'table' AND name NOT LIKE 'sqlite_%'
                ORDER BY name
                """
            ).fetchall()
        return [row["name"] for row in rows]

    def get_table_schema(self, table: str) -> list[dict[str, Any]]:
        self._validate_table(table)
        with self.connect() as conn:
            rows = conn.execute(f"PRAGMA table_info({self._quote_identifier(table)})").fetchall()
        return [
            {
                "cid": row["cid"],
                "name": row["name"],
                "type": row["type"],
                "notnull": bool(row["notnull"]),
                "default": row["dflt_value"],
                "pk": bool(row["pk"]),
            }
            for row in rows
        ]

    def get_database_schema(self) -> dict[str, Any]:
        schema: dict[str, Any] = {"tables": {}}
        for table in self.list_tables():
            schema["tables"][table] = self.get_table_schema(table)
        return schema

    def search(
        self,
        table: str,
        columns: list[str] | None = None,
        filters: dict[str, Any] | None = None,
        limit: int = 20,
        offset: int = 0,
        order_by: str | None = None,
        descending: bool = False,
    ) -> dict[str, Any]:
        self._validate_table(table)
        table_columns = {col["name"] for col in self.get_table_schema(table)}

        selected = columns or sorted(table_columns)
        if not selected:
            raise ValidationError("No columns available for the requested table.")
        for column in selected:
            self._validate_column(column, table_columns)

        if limit < 1 or limit > 100:
            raise ValidationError("limit must be between 1 and 100.")
        if offset < 0:
            raise ValidationError("offset must be zero or greater.")

        where_sql, params = self._build_filters(filters, table_columns)
        order_sql = ""
        if order_by:
            self._validate_column(order_by, table_columns)
            direction = "DESC" if descending else "ASC"
            order_sql = f" ORDER BY {self._quote_identifier(order_by)} {direction}"

        column_sql = ", ".join(self._quote_identifier(column) for column in selected)
        query = (
            f"SELECT {column_sql} FROM {self._quote_identifier(table)}"
            f"{where_sql}{order_sql} LIMIT ? OFFSET ?"
        )

        with self.connect() as conn:
            rows = conn.execute(query, [*params, limit, offset]).fetchall()
            count_query = f"SELECT COUNT(*) AS total FROM {self._quote_identifier(table)}{where_sql}"
            total = conn.execute(count_query, params).fetchone()["total"]

        return {
            "rows": [dict(row) for row in rows],
            "count": len(rows),
            "total": total,
            "limit": limit,
            "offset": offset,
        }

    def insert(self, table: str, values: dict[str, Any]) -> dict[str, Any]:
        self._validate_table(table)
        if not values:
            raise ValidationError("insert values cannot be empty.")

        table_columns = {col["name"] for col in self.get_table_schema(table)}
        for column in values:
            self._validate_column(column, table_columns)

        columns = list(values.keys())
        placeholders = ", ".join("?" for _ in columns)
        column_sql = ", ".join(self._quote_identifier(column) for column in columns)
        query = (
            f"INSERT INTO {self._quote_identifier(table)} ({column_sql}) "
            f"VALUES ({placeholders})"
        )

        with self.connect() as conn:
            cursor = conn.execute(query, list(values.values()))
            conn.commit()
            row_id = cursor.lastrowid
            if row_id:
                row = conn.execute(
                    f"SELECT * FROM {self._quote_identifier(table)} WHERE rowid = ?",
                    (row_id,),
                ).fetchone()
                return {"inserted": dict(row)}

        return {"inserted": dict(values)}

    def aggregate(
        self,
        table: str,
        metric: str,
        column: str | None = None,
        filters: dict[str, Any] | None = None,
        group_by: str | None = None,
    ) -> dict[str, Any]:
        metric = metric.lower()
        if metric not in ALLOWED_METRICS:
            raise ValidationError(
                f"Unsupported metric '{metric}'. Allowed: {sorted(ALLOWED_METRICS)}"
            )

        self._validate_table(table)
        table_columns = {col["name"] for col in self.get_table_schema(table)}

        if metric != "count" and not column:
            raise ValidationError(f"metric '{metric}' requires a column.")
        if column:
            self._validate_column(column, table_columns)
        if group_by:
            self._validate_column(group_by, table_columns)

        if metric == "count":
            metric_sql = "COUNT(*)"
        else:
            metric_sql = f"{metric.upper()}({self._quote_identifier(column)})"

        select_parts = []
        if group_by:
            select_parts.append(self._quote_identifier(group_by))
        select_parts.append(f"{metric_sql} AS value")
        select_sql = ", ".join(select_parts)

        where_sql, params = self._build_filters(filters, table_columns)
        group_sql = f" GROUP BY {self._quote_identifier(group_by)}" if group_by else ""
        query = (
            f"SELECT {select_sql} FROM {self._quote_identifier(table)}"
            f"{where_sql}{group_sql}"
        )

        with self.connect() as conn:
            rows = conn.execute(query, params).fetchall()

        results = []
        for row in rows:
            item = {"value": row["value"]}
            if group_by:
                item["group"] = row[group_by]
            results.append(item)

        return {"metric": metric, "column": column, "results": results}

    def _build_filters(
        self, filters: dict[str, Any] | None, table_columns: set[str]
    ) -> tuple[str, list[Any]]:
        if not filters:
            return "", []

        clauses: list[str] = []
        params: list[Any] = []

        for column, condition in filters.items():
            self._validate_column(column, table_columns)
            if not isinstance(condition, dict) or not condition:
                raise ValidationError(
                    f"Filter for column '{column}' must be a non-empty operator map."
                )

            for operator, value in condition.items():
                if operator not in ALLOWED_OPERATORS:
                    raise ValidationError(
                        f"Unsupported operator '{operator}'. Allowed: {sorted(ALLOWED_OPERATORS)}"
                    )

                quoted = self._quote_identifier(column)
                if operator == "in":
                    if not isinstance(value, list) or not value:
                        raise ValidationError(
                            f"Operator 'in' for column '{column}' requires a non-empty list."
                        )
                    placeholders = ", ".join("?" for _ in value)
                    clauses.append(f"{quoted} IN ({placeholders})")
                    params.extend(value)
                else:
                    clauses.append(f"{quoted} {OPERATOR_SQL[operator]} ?")
                    params.append(value)

        return " WHERE " + " AND ".join(clauses), params

    def _validate_table(self, table: str) -> None:
        if not isinstance(table, str) or not IDENTIFIER_PATTERN.match(table):
            raise ValidationError(f"Invalid table name: {table!r}")
        if table not in self.list_tables():
            raise ValidationError(f"Unknown table: {table!r}")

    def _validate_column(self, column: str, allowed_columns: set[str]) -> None:
        if not isinstance(column, str) or not IDENTIFIER_PATTERN.match(column):
            raise ValidationError(f"Invalid column name: {column!r}")
        if column not in allowed_columns:
            raise ValidationError(f"Unknown column: {column!r}")

    def _quote_identifier(self, identifier: str) -> str:
        return f'"{identifier.replace(chr(34), chr(34) * 2)}"'
