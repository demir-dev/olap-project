"""
Shared application dependencies:
- DuckDB singleton connection with thread-safe lock
- Database initialisation (schema + seeding)
"""

import logging
import threading
from pathlib import Path

import duckdb

from app.config import settings

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Thread-safe DuckDB singleton
# ---------------------------------------------------------------------------

_conn: duckdb.DuckDBPyConnection | None = None
_lock = threading.Lock()


def get_connection() -> duckdb.DuckDBPyConnection:
    """Return the global DuckDB connection (not thread-safe on its own – use execute_query)."""
    if _conn is None:
        raise RuntimeError("Database not initialised. Call init_database() first.")
    return _conn


def execute_query(sql: str, params: list | None = None) -> tuple[list[str], list[tuple]]:
    """
    Execute a DuckDB query under the global lock.
    Returns (column_names, rows).
    """
    global _conn
    with _lock:
        try:
            if params:
                result = _conn.execute(sql, params)
            else:
                result = _conn.execute(sql)
            if result.description is None:
                return [], []
            columns = [desc[0] for desc in result.description]
            rows = result.fetchall()
            return columns, rows
        except Exception as exc:
            logger.error("Query failed: %s\nSQL: %s\nParams: %s", exc, sql, params)
            raise


# ---------------------------------------------------------------------------
# Initialisation
# ---------------------------------------------------------------------------

def init_database() -> None:
    """
    Open (or create) the DuckDB file, apply schema DDL, and seed data if the
    fact table is empty.
    Called once at FastAPI startup via the lifespan handler.
    """
    global _conn

    db_path = Path(settings.database_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    logger.info("Opening DuckDB at: %s", db_path.resolve())
    _conn = duckdb.connect(str(db_path))

    # Apply schema DDL
    schema_file = Path(__file__).parent.parent / "data" / "schema.sql"
    logger.info("Applying schema from: %s", schema_file)
    _conn.execute(schema_file.read_text())

    # Seed if empty
    row_count = _conn.execute("SELECT COUNT(*) FROM fact_sales").fetchone()[0]
    if row_count == 0:
        logger.info("fact_sales is empty — generating dataset...")
        _seed_database()
        row_count = _conn.execute("SELECT COUNT(*) FROM fact_sales").fetchone()[0]

    logger.info("Database ready: %d fact_sales rows", row_count)


def _seed_database() -> None:
    """Populate an empty DB by calling generate_dataset functions in-process.

    We must NOT spawn a subprocess here because _conn already holds the DuckDB
    file lock and a second process cannot acquire it simultaneously.
    """
    import random
    import sys
    from pathlib import Path

    # Make the data/ directory importable so we can reuse the builder functions
    data_dir = str(Path(__file__).parent.parent / "data")
    if data_dir not in sys.path:
        sys.path.insert(0, data_dir)

    from generate_dataset import (  # type: ignore[import]
        build_dim_date,
        build_dim_geography,
        build_dim_product,
        build_dim_customer,
        build_fact_sales,
        insert_rows,
    )
    from datetime import date

    rng = random.Random(42)
    start_date = date(2022, 1, 1)
    end_date = date(2024, 12, 31)

    logger.info("Building dimension tables...")
    date_rows = build_dim_date(start_date, end_date)
    geo_rows = build_dim_geography()
    product_rows = build_dim_product()
    customer_rows = build_dim_customer(200)

    logger.info("Building fact_sales (10,000 rows)...")
    fact_rows = build_fact_sales(10_000, date_rows, geo_rows, product_rows, customer_rows, rng)

    logger.info("Inserting into DuckDB...")
    _conn.begin()
    insert_rows(_conn, "dim_date", date_rows)
    insert_rows(_conn, "dim_geography", geo_rows)
    insert_rows(_conn, "dim_product", product_rows)
    insert_rows(_conn, "dim_customer", customer_rows)
    insert_rows(_conn, "fact_sales", fact_rows)
    _conn.commit()
    logger.info("Dataset seeded successfully.")


def close_database() -> None:
    """Close the DuckDB connection. Called at FastAPI shutdown."""
    global _conn
    if _conn is not None:
        _conn.close()
        _conn = None
        logger.info("DuckDB connection closed.")
