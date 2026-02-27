"""
API routes:
  POST /chat                    — Main OLAP chat endpoint (Tier 3)
  GET  /api/query/dashboard     — 6 KPI summary values
  GET  /api/query/suggestions   — Example query suggestions
  GET  /api/query/llm-status    — LLM provider status
  POST /api/olap/drill-down     — Direct drill-down
  POST /api/olap/roll-up        — Direct roll-up
  POST /api/olap/slice          — Direct slice
  POST /api/olap/dice           — Direct dice
  POST /api/olap/pivot          — Direct pivot
  POST /api/olap/yoy-growth     — Direct YoY growth
  POST /api/olap/top-n          — Direct top-N ranking
  POST /api/olap/profit-margins — Direct profit margin analysis
  GET  /schema                  — Star schema metadata
  GET  /health                  — Health check
"""

import logging
from typing import Any, Optional

from fastapi import APIRouter, Body, HTTPException
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel

from app.api.schemas import (
    ChatRequest,
    ChatResponse,
    ColumnMeta,
    DataPayload,
    ExecutiveSummary,
    HealthResponse,
    ReportItem,
    SchemaRelationship,
    SchemaResponse,
    TableMeta,
    VisualizationHint,
)
from app.dependencies import execute_query
from app.orchestrator.planner import SCHEMA_SUMMARY, get_planner
from app.orchestrator.session import active_session_count
from app.config import settings

logger = logging.getLogger(__name__)
router = APIRouter()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _sanitize_for_json(data: Any) -> Any:
    """Recursively sanitize data for JSON serialization."""
    if isinstance(data, dict):
        return {k: _sanitize_for_json(v) for k, v in data.items()}
    elif isinstance(data, list):
        return [_sanitize_for_json(item) for item in data]
    elif isinstance(data, (int, float, str, bool, type(None))):
        return data
    else:
        return str(data)


def _make_agent_entities(body: dict[str, Any]) -> dict[str, Any]:
    """Build a minimal entities dict from a direct OLAP endpoint body."""
    entities: dict[str, Any] = {}
    if body.get("dimension"):
        entities["dimensions"] = [body["dimension"]]
    if body.get("measure"):
        entities["measures"] = [body["measure"]]
    if body.get("year"):
        entities["years"] = [int(body["year"])]
    if body.get("year_a") and body.get("year_b"):
        entities["years"] = [int(body["year_a"]), int(body["year_b"])]
    top_n = body.get("top_n") or body.get("n")
    if top_n:
        entities["top_n"] = int(top_n)
    if body.get("region"):
        entities["regions"] = [body["region"]]
    if body.get("category"):
        entities["categories"] = [body["category"]]
    if body.get("filters"):
        entities["filters"] = body["filters"]
    if body.get("kpi_type"):
        entities["kpi_type"] = body["kpi_type"]
    return entities


def _run_direct_olap(intent: str, entities: dict[str, Any], kpi_type: str | None = None) -> dict[str, Any]:
    """Execute a direct OLAP operation bypassing the chat planner."""
    from app.agents.base_agent import AgentInput
    from app.agents.cube_operations import CubeOperationsAgent
    from app.agents.dimension_navigator import DimensionNavigatorAgent
    from app.agents.kpi_calculator import KPICalculatorAgent

    if kpi_type:
        entities["kpi_type"] = kpi_type

    agent_input = AgentInput(
        message="",
        intent=intent,
        entities=entities,
        session_context={"active_filters": {}},
        schema_summary=SCHEMA_SUMMARY,
        page=1,
    )

    if intent in ("drill_down", "roll_up", "dimensions"):
        output = DimensionNavigatorAgent()._safe_execute(agent_input)
    elif intent in ("slice", "dice", "pivot", "drill_through"):
        output = CubeOperationsAgent()._safe_execute(agent_input)
    else:
        output = KPICalculatorAgent()._safe_execute(agent_input)

    data_payload = None
    if output.data:
        data_payload = {
            "columns": output.data.get("columns", []),
            "rows": output.data.get("rows", []),
            "row_count": output.data.get("row_count", 0),
        }

    return {
        "intent": intent,
        "sql_query": output.sql_query,
        "data": data_payload,
        "visualization_hint": output.visualization_hint,
        "follow_up_suggestions": output.follow_up_suggestions,
        "error": output.error,
    }


# ---------------------------------------------------------------------------
# POST /chat
# ---------------------------------------------------------------------------

@router.post("/chat", response_model=ChatResponse, summary="OLAP Chat")
async def chat(request: ChatRequest) -> ChatResponse:
    """
    Main OLAP assistant endpoint. Returns structured result, narrative summary,
    executive summary with highlights/recommendations, and visualization hint.
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

    summary = None
    if result.get("summary"):
        s = result["summary"]
        summary = ExecutiveSummary(
            text=s.get("text", ""),
            highlights=s.get("highlights", []),
            recommendations=s.get("recommendations", []),
        )

    reports = [
        ReportItem(
            title=r.get("title", ""),
            columns=r.get("columns", []),
            rows=r.get("rows", []),
            row_count=r.get("row_count", 0),
            operation=r.get("operation", ""),
        )
        for r in result.get("reports", [])
    ]

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
        summary=summary,
        reports=reports,
        llm_used=result.get("llm_used", False),
    )


# ---------------------------------------------------------------------------
# GET /api/query/dashboard
# ---------------------------------------------------------------------------

@router.get("/api/query/dashboard", tags=["Dashboard"])
async def dashboard_kpis() -> dict[str, Any]:
    """Return 6 aggregate KPI values for the dashboard header cards."""
    sql = """
SELECT
    ROUND(SUM(f.revenue), 2)           AS total_revenue,
    ROUND(SUM(f.profit), 2)            AS total_profit,
    ROUND(AVG(f.profit_margin)*100, 2) AS avg_margin_pct,
    COUNT(f.sale_id)                   AS total_orders,
    SUM(f.quantity)                    AS total_units,
    COUNT(DISTINCT g.country)          AS countries
FROM fact_sales f
JOIN dim_geography g ON f.geo_key = g.geo_key
""".strip()
    try:
        _, rows = execute_query(sql)
        row = rows[0] if rows else [0] * 6
        return {
            "total_revenue":  float(row[0] or 0),
            "total_profit":   float(row[1] or 0),
            "avg_margin_pct": float(row[2] or 0),
            "total_orders":   int(row[3] or 0),
            "total_units":    int(row[4] or 0),
            "countries":      int(row[5] or 0),
        }
    except Exception as exc:
        logger.exception("Dashboard KPI query failed")
        raise HTTPException(status_code=500, detail=str(exc))


# ---------------------------------------------------------------------------
# GET /api/query/suggestions
# ---------------------------------------------------------------------------

@router.get("/api/query/suggestions", tags=["Natural Language Query"])
async def query_suggestions() -> dict[str, Any]:
    """Return example queries to guide the user."""
    return {
        "suggestions": [
            "What is total revenue by region for 2024?",
            "Show YoY growth by category",
            "Top 5 countries by profit",
            "Drill down from year to quarter",
            "Compare 2023 vs 2024 revenue",
            "What is the profit margin by category?",
            "Show monthly revenue trend for 2024",
            "Pivot revenue by region and year",
            "Which customer segment generates the most revenue?",
            "Show revenue share by region",
        ]
    }


# ---------------------------------------------------------------------------
# GET /api/query/llm-status
# ---------------------------------------------------------------------------

@router.get("/api/query/llm-status", tags=["Natural Language Query"])
async def llm_status() -> dict[str, Any]:
    """Check if an LLM provider is enabled."""
    return {
        "llm_enabled": bool(settings.anthropic_api_key),
        "provider": "anthropic" if settings.anthropic_api_key else None,
    }


# ---------------------------------------------------------------------------
# POST /api/olap/* — Direct OLAP operation endpoints
# ---------------------------------------------------------------------------

@router.post("/api/olap/drill-down", tags=["OLAP Operations"])
async def olap_drill_down(body: dict[str, Any] = Body(default={})) -> Response:
    result = _run_direct_olap("drill_down", _make_agent_entities(body))
    return JSONResponse(content=_sanitize_for_json(result))


@router.post("/api/olap/roll-up", tags=["OLAP Operations"])
async def olap_roll_up(body: dict[str, Any] = Body(default={})) -> Response:
    result = _run_direct_olap("roll_up", _make_agent_entities(body))
    return JSONResponse(content=_sanitize_for_json(result))


@router.post("/api/olap/slice", tags=["OLAP Operations"])
async def olap_slice(body: dict[str, Any] = Body(default={})) -> Response:
    result = _run_direct_olap("slice", _make_agent_entities(body))
    return JSONResponse(content=_sanitize_for_json(result))


@router.post("/api/olap/dice", tags=["OLAP Operations"])
async def olap_dice(body: dict[str, Any] = Body(default={})) -> Response:
    result = _run_direct_olap("dice", _make_agent_entities(body))
    return JSONResponse(content=_sanitize_for_json(result))


@router.post("/api/olap/pivot", tags=["OLAP Operations"])
async def olap_pivot(body: dict[str, Any] = Body(default={})) -> Response:
    result = _run_direct_olap("pivot", _make_agent_entities(body))
    return JSONResponse(content=_sanitize_for_json(result))


@router.post("/api/olap/yoy-growth", tags=["OLAP Operations"])
async def olap_yoy_growth(body: dict[str, Any] = Body(default={})) -> Response:
    result = _run_direct_olap("kpi", _make_agent_entities(body), kpi_type="yoy_growth")
    return JSONResponse(content=_sanitize_for_json(result))


@router.post("/api/olap/top-n", tags=["OLAP Operations"])
async def olap_top_n(body: dict[str, Any] = Body(default={})) -> Response:
    entities = _make_agent_entities(body)
    if not entities.get("top_n"):
        entities["top_n"] = 5
    result = _run_direct_olap("kpi", entities, kpi_type="top_n")
    return JSONResponse(content=_sanitize_for_json(result))


@router.post("/api/olap/profit-margins", tags=["OLAP Operations"])
async def olap_profit_margins(body: dict[str, Any] = Body(default={})) -> Response:
    result = _run_direct_olap("kpi", _make_agent_entities(body), kpi_type="margin")
    return JSONResponse(content=_sanitize_for_json(result))


# ---------------------------------------------------------------------------
# GET /schema
# ---------------------------------------------------------------------------

@router.get("/schema", response_model=SchemaResponse, summary="Star Schema Metadata")
async def schema() -> SchemaResponse:
    """Returns the star schema structure."""
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
            cols_result = execute_query(f"DESCRIBE {table_name}")
            columns_list, col_rows = cols_result
            col_meta = [
                ColumnMeta(name=row[0], dtype=str(row[1]), nullable=(row[2] == "YES" if row[2] else True))
                for row in col_rows
            ]
            _, count_rows = execute_query(f"SELECT COUNT(*) FROM {table_name}")
            row_count = count_rows[0][0] if count_rows else 0
            tables[table_name] = TableMeta(columns=col_meta, row_count=row_count, description=description)
        except Exception as exc:
            logger.warning("Could not introspect table %s: %s", table_name, exc)

    relationships = [
        SchemaRelationship(from_table="fact_sales", from_column="date_key",     to_table="dim_date",      to_column="date_key"),
        SchemaRelationship(from_table="fact_sales", from_column="geo_key",      to_table="dim_geography", to_column="geo_key"),
        SchemaRelationship(from_table="fact_sales", from_column="product_key",  to_table="dim_product",   to_column="product_key"),
        SchemaRelationship(from_table="fact_sales", from_column="customer_key", to_table="dim_customer",  to_column="customer_key"),
    ]

    dim_values: dict[str, list[str]] = {}
    dim_queries = {
        "region":           "SELECT DISTINCT region FROM dim_geography ORDER BY region",
        "country":          "SELECT DISTINCT country FROM dim_geography ORDER BY country",
        "category":         "SELECT DISTINCT category FROM dim_product ORDER BY category",
        "subcategory":      "SELECT DISTINCT subcategory FROM dim_product ORDER BY subcategory",
        "customer_segment": "SELECT DISTINCT customer_segment FROM dim_customer ORDER BY customer_segment",
        "year":             "SELECT DISTINCT year FROM dim_date ORDER BY year",
        "quarter_name":     "SELECT DISTINCT quarter_name FROM dim_date ORDER BY quarter_name",
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
