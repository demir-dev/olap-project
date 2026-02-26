"""
API routes:
  POST /chat    — Main OLAP chat endpoint
  GET  /schema  — Star schema metadata
  GET  /health  — Health check
"""

import logging

from fastapi import APIRouter, HTTPException

from app.api.schemas import (
    ChatRequest,
    ChatResponse,
    ColumnMeta,
    DataPayload,
    HealthResponse,
    SchemaRelationship,
    SchemaResponse,
    TableMeta,
    VisualizationHint,
)
from app.dependencies import execute_query
from app.orchestrator.planner import get_planner
from app.orchestrator.session import active_session_count
from app.config import settings

logger = logging.getLogger(__name__)
router = APIRouter()


# ---------------------------------------------------------------------------
# POST /chat
# ---------------------------------------------------------------------------

@router.post("/chat", response_model=ChatResponse, summary="OLAP Chat")
async def chat(request: ChatRequest) -> ChatResponse:
    """
    Main OLAP assistant endpoint.

    Send a natural language question and receive:
    - Structured result table
    - Plain-English narrative summary
    - Visualization hint
    - Follow-up question suggestions
    """
    try:
        planner = get_planner()
        result = planner.process(
            message=request.message,
            session_id=request.session_id,
            page=request.page,
        )
    except Exception as exc:
        logger.exception("Planner error for message: %s", request.message)
        raise HTTPException(status_code=500, detail=str(exc))

    # Build response
    data_payload = None
    if result.get("data"):
        d = result["data"]
        data_payload = DataPayload(
            columns=d.get("columns", []),
            rows=d.get("rows", []),
            row_count=d.get("row_count", 0),
        )

    viz_hint = None
    if result.get("visualization_hint"):
        vh = result["visualization_hint"]
        viz_hint = VisualizationHint(
            chart_type=vh.get("chart_type", "table"),
            x_axis=vh.get("x_axis") or vh.get("x"),
            y_axis=vh.get("y_axis") or vh.get("y"),
            color_by=vh.get("color_by"),
        )

    return ChatResponse(
        session_id=result["session_id"],
        intent=result["intent"],
        agents_used=result["agents_used"],
        sql_query=result.get("sql_query"),
        data=data_payload,
        narrative=result.get("narrative", ""),
        visualization_hint=viz_hint,
        follow_up_suggestions=result.get("follow_up_suggestions", []),
        error=result.get("error"),
        latency_ms=result.get("latency_ms", 0),
    )


# ---------------------------------------------------------------------------
# GET /schema
# ---------------------------------------------------------------------------

@router.get("/schema", response_model=SchemaResponse, summary="Star Schema Metadata")
async def schema() -> SchemaResponse:
    """
    Returns the star schema structure including:
    - Table definitions with column types and row counts
    - Foreign key relationships
    - Available dimension member values
    - Hierarchy definitions
    """
    tables: dict[str, TableMeta] = {}

    table_descriptions = {
        "fact_sales":    "Central fact table with one row per sales transaction",
        "dim_date":      "Date dimension: year, quarter, month hierarchy",
        "dim_geography": "Geography dimension: region → country hierarchy",
        "dim_product":   "Product dimension: category → subcategory hierarchy",
        "dim_customer":  "Customer dimension: segment classification",
    }

    for table_name, description in table_descriptions.items():
        try:
            # Get column info
            cols_result = execute_query(f"DESCRIBE {table_name}")
            columns_list, col_rows = cols_result

            col_meta = []
            for row in col_rows:
                # DuckDB DESCRIBE returns: column_name, column_type, null, key, default, extra
                col_meta.append(ColumnMeta(
                    name=row[0],
                    dtype=str(row[1]),
                    nullable=(row[2] == "YES" if row[2] else True),
                ))

            # Row count
            _, count_rows = execute_query(f"SELECT COUNT(*) FROM {table_name}")
            row_count = count_rows[0][0] if count_rows else 0

            tables[table_name] = TableMeta(
                columns=col_meta,
                row_count=row_count,
                description=description,
            )
        except Exception as exc:
            logger.warning("Could not introspect table %s: %s", table_name, exc)

    relationships = [
        SchemaRelationship(from_table="fact_sales", from_column="date_key",     to_table="dim_date",     to_column="date_key"),
        SchemaRelationship(from_table="fact_sales", from_column="geo_key",      to_table="dim_geography", to_column="geo_key"),
        SchemaRelationship(from_table="fact_sales", from_column="product_key",  to_table="dim_product",  to_column="product_key"),
        SchemaRelationship(from_table="fact_sales", from_column="customer_key", to_table="dim_customer", to_column="customer_key"),
    ]

    # Dimension member values
    dim_values: dict[str, list[str]] = {}
    dim_queries = {
        "region":            "SELECT DISTINCT region FROM dim_geography ORDER BY region",
        "country":           "SELECT DISTINCT country FROM dim_geography ORDER BY country",
        "category":          "SELECT DISTINCT category FROM dim_product ORDER BY category",
        "subcategory":       "SELECT DISTINCT subcategory FROM dim_product ORDER BY subcategory",
        "customer_segment":  "SELECT DISTINCT customer_segment FROM dim_customer ORDER BY customer_segment",
        "year":              "SELECT DISTINCT year FROM dim_date ORDER BY year",
        "quarter_name":      "SELECT DISTINCT quarter_name FROM dim_date ORDER BY quarter_name",
    }
    for dim_name, sql in dim_queries.items():
        try:
            _, rows = execute_query(sql)
            dim_values[dim_name] = [str(row[0]) for row in rows]
        except Exception:
            dim_values[dim_name] = []

    hierarchies = {
        "time":      ["year", "quarter_name", "month_name"],
        "geography": ["region", "country"],
        "product":   ["category", "subcategory", "product_name"],
    }

    return SchemaResponse(
        tables=tables,
        relationships=relationships,
        dimension_values=dim_values,
        hierarchies=hierarchies,
    )


# ---------------------------------------------------------------------------
# GET /health
# ---------------------------------------------------------------------------

@router.get("/health", response_model=HealthResponse, summary="Health Check")
async def health() -> HealthResponse:
    """Returns backend health status and database connectivity."""
    db_connected = False
    row_count = 0
    try:
        _, rows = execute_query("SELECT COUNT(*) FROM fact_sales")
        row_count = rows[0][0] if rows else 0
        db_connected = True
    except Exception:
        pass

    return HealthResponse(
        status="ok",
        db_connected=db_connected,
        db_row_count=row_count,
        active_sessions=active_session_count(),
        version=settings.app_version,
    )
