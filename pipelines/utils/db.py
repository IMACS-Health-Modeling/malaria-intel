"""
Database utility — PostgreSQL connection and helpers.
Connection string from DATABASE_URL env var.
"""

import os
import psycopg2
import psycopg2.extras
from typing import Any

DATABASE_URL = os.environ.get(
    "DATABASE_URL",
    "postgresql://postgres:postgres@localhost:5432/malaria_intel"
)


def get_conn():
    """Open a new PostgreSQL connection."""
    return psycopg2.connect(DATABASE_URL)


def execute(sql: str, params: tuple | None = None) -> None:
    """Execute a single statement."""
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, params)
        conn.commit()


_VALID_ISO3_CACHE: set[str] | None = None


def get_valid_iso3() -> set[str]:
    """Return the set of valid ISO3 codes in dim_country (cached per process)."""
    global _VALID_ISO3_CACHE
    if _VALID_ISO3_CACHE is None:
        try:
            rows = fetchall("SELECT iso3 FROM malaria.dim_country")
            _VALID_ISO3_CACHE = {r["iso3"] for r in rows}
        except Exception:
            _VALID_ISO3_CACHE = set()
    return _VALID_ISO3_CACHE


def filter_valid_iso3(rows: list[tuple], iso3_col: int = 0) -> tuple[list[tuple], int]:
    """
    Filter rows to only those with valid ISO3 codes in dim_country.
    Returns (valid_rows, skipped_count).
    iso3_col is the column index in each tuple that holds the ISO3 code.
    """
    valid = get_valid_iso3()
    if not valid:
        return rows, 0  # No filter if dim_country empty
    good, bad = [], 0
    for row in rows:
        iso3 = row[iso3_col] if iso3_col < len(row) else None
        if iso3 and str(iso3).upper() in valid:
            good.append(row)
        else:
            bad += 1
    return good, bad


def upsert_many(sql: str, rows: list[tuple], page_size: int = 1000) -> int:
    """Bulk upsert using execute_values. Returns rows inserted."""
    if not rows:
        return 0
    inserted = 0
    with get_conn() as conn:
        with conn.cursor() as cur:
            for i in range(0, len(rows), page_size):
                batch = rows[i : i + page_size]
                psycopg2.extras.execute_values(cur, sql, batch)
                inserted += len(batch)
        conn.commit()
    return inserted


def fetchall(sql: str, params: tuple | None = None) -> list[dict]:
    """Return all rows as list of dicts."""
    with get_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(sql, params)
            return [dict(r) for r in cur.fetchall()]


def fetchone(sql: str, params: tuple | None = None) -> dict | None:
    """Return one row as dict, or None."""
    rows = fetchall(sql, params)
    return rows[0] if rows else None


def table_exists(table: str, schema: str = "malaria") -> bool:
    row = fetchone(
        "SELECT 1 FROM information_schema.tables "
        "WHERE table_schema=%s AND table_name=%s",
        (schema, table),
    )
    return row is not None


def init_schema(schema_path: str | None = None) -> None:
    """Run schema.sql to create all tables if they don't exist."""
    from pathlib import Path
    if schema_path is None:
        schema_path = str(Path(__file__).parent.parent / "db" / "schema.sql")
    with open(schema_path) as f:
        sql = f.read()
    execute(sql)
    print("Schema initialised.")
