"""FastMCP server exposing SQLite search, insert, aggregate tools and schema resources."""

from __future__ import annotations

import json
from typing import Any

from fastmcp import FastMCP

from db import SQLiteAdapter, ValidationError

mcp = FastMCP("SQLite Lab MCP Server")
adapter = SQLiteAdapter()


def _validation_error(message: str) -> dict[str, str]:
    return {"error": message}


@mcp.tool(name="search")
def search(
    table: str,
    filters: dict[str, Any] | None = None,
    columns: list[str] | None = None,
    limit: int = 20,
    offset: int = 0,
    order_by: str | None = None,
    descending: bool = False,
) -> dict[str, Any]:
    """
    Search rows from a table with optional filters, column selection, ordering, and pagination.

    Filters use operator maps, for example:
    {"cohort": {"eq": "A1"}, "score": {"gte": 80}}
    """
    try:
        return adapter.search(
            table=table,
            columns=columns,
            filters=filters,
            limit=limit,
            offset=offset,
            order_by=order_by,
            descending=descending,
        )
    except ValidationError as exc:
        return _validation_error(str(exc))


@mcp.tool(name="insert")
def insert(table: str, values: dict[str, Any]) -> dict[str, Any]:
    """Insert a row into a table and return the inserted payload."""
    try:
        return adapter.insert(table=table, values=values)
    except ValidationError as exc:
        return _validation_error(str(exc))


@mcp.tool(name="aggregate")
def aggregate(
    table: str,
    metric: str,
    column: str | None = None,
    filters: dict[str, Any] | None = None,
    group_by: str | None = None,
) -> dict[str, Any]:
    """
    Run aggregate metrics on a table.

    Supported metrics: count, avg, sum, min, max.
    """
    try:
        return adapter.aggregate(
            table=table,
            metric=metric,
            column=column,
            filters=filters,
            group_by=group_by,
        )
    except ValidationError as exc:
        return _validation_error(str(exc))


@mcp.resource("schema://database")
def database_schema() -> str:
    """Return the full database schema as JSON."""
    return json.dumps(adapter.get_database_schema(), indent=2)


@mcp.resource("schema://table/{table_name}")
def table_schema(table_name: str) -> str:
    """Return the schema for a single table as JSON."""
    try:
        schema = {
            "table": table_name,
            "columns": adapter.get_table_schema(table_name),
        }
        return json.dumps(schema, indent=2)
    except ValidationError as exc:
        return json.dumps({"error": str(exc)}, indent=2)


if __name__ == "__main__":
    mcp.run()
