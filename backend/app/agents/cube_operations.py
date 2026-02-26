"""
Cube Operations Agent
=====================
Handles OLAP cube operations: Slice, Dice, Pivot, Drill-through.

Slice  : Filter on a single dimension value → aggregate result.
Dice   : Filter on multiple dimension values simultaneously → aggregate result.
Pivot  : Reshape data using DuckDB PIVOT clause (rows ↔ columns).
Drill-Through: Return raw transaction rows with pagination.
"""

import logging
from typing import Any

from app.agents.base_agent import AgentInput, AgentOutput, BaseAgent
from app.config import settings
from app.dependencies import execute_query

logger = logging.getLogger(__name__)

# Mapping from friendly measure names to SQL column expressions
MEASURE_SQL = {
    "revenue":       "SUM(f.revenue)",
    "cost":          "SUM(f.cost)",
    "profit":        "SUM(f.profit)",
    "profit_margin": "ROUND(AVG(f.profit_margin) * 100, 2)",
    "quantity":      "SUM(f.quantity)",
    "orders":        "COUNT(f.sale_id)",
    "avg_order":     "ROUND(AVG(f.revenue), 2)",
}

# Mapping from friendly dimension names to SQL table + column
DIM_SQL = {
    "region":            "g.region",
    "country":           "g.country",
    "year":              "d.year",
    "quarter":           "d.quarter_name",
    "month":             "d.month",
    "month_name":        "d.month_name",
    "category":          "p.category",
    "subcategory":       "p.subcategory",
    "product_name":      "p.product_name",
    "customer_segment":  "c.customer_segment",
    "customer_name":     "c.customer_name",
}

# WHERE clause column for filter resolution
FILTER_SQL = {
    "region":            "g.region",
    "country":           "g.country",
    "year":              "d.year",
    "quarter":           "d.quarter_name",
    "quarter_num":       "d.quarter",
    "month":             "d.month",
    "month_name":        "d.month_name",
    "category":          "p.category",
    "subcategory":       "p.subcategory",
    "customer_segment":  "c.customer_segment",
}

BASE_JOINS = """
FROM fact_sales f
JOIN dim_date      d ON f.date_key     = d.date_key
JOIN dim_geography g ON f.geo_key      = g.geo_key
JOIN dim_product   p ON f.product_key  = p.product_key
JOIN dim_customer  c ON f.customer_key = c.customer_key
"""


def _build_where(filters: dict[str, Any]) -> tuple[str, list]:
    """Build a parameterised WHERE clause from a filters dict."""
    clauses = []
    params = []
    for key, value in filters.items():
        col = FILTER_SQL.get(key)
        if col is None:
            continue
        if isinstance(value, list):
            placeholders = ", ".join("?" * len(value))
            clauses.append(f"{col} IN ({placeholders})")
            params.extend(value)
        else:
            clauses.append(f"{col} = ?")
            params.append(value)
    where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
    return where, params


def _resolve_measures(measures: list[str]) -> list[tuple[str, str]]:
    """Return list of (alias, sql_expr) for requested measures."""
    if not measures:
        measures = ["revenue", "profit", "orders"]
    result = []
    for m in measures:
        key = m.lower().replace(" ", "_")
        expr = MEASURE_SQL.get(key)
        if expr:
            result.append((key, expr))
    if not result:
        result = [("revenue", MEASURE_SQL["revenue"]), ("orders", MEASURE_SQL["orders"])]
    return result


def _resolve_dimensions(dimensions: list[str]) -> list[tuple[str, str]]:
    """Return list of (alias, sql_expr) for requested group-by dimensions."""
    result = []
    for d in dimensions:
        key = d.lower().replace(" ", "_")
        expr = DIM_SQL.get(key)
        if expr:
            result.append((key, expr))
    return result


class CubeOperationsAgent(BaseAgent):

    @property
    def name(self) -> str:
        return "CubeOperations"

    def execute(self, agent_input: AgentInput) -> AgentOutput:
        intent = agent_input.intent
        entities = agent_input.entities
        ctx = agent_input.session_context

        # Merge sticky context into filters
        filters = dict(ctx.get("active_filters", {}))
        filters.update(entities.get("filters", {}))

        # Resolve from entities
        if entities.get("regions"):
            filters["region"] = entities["regions"] if len(entities["regions"]) > 1 else entities["regions"][0]
        if entities.get("categories"):
            filters["category"] = entities["categories"] if len(entities["categories"]) > 1 else entities["categories"][0]
        if entities.get("years"):
            filters["year"] = entities["years"] if len(entities["years"]) > 1 else entities["years"][0]
        if entities.get("quarters"):
            q_vals = entities["quarters"]
            filters["quarter"] = [f"Q{q}" for q in q_vals] if len(q_vals) > 1 else f"Q{q_vals[0]}"
        if entities.get("customer_segments"):
            filters["customer_segment"] = entities["customer_segments"][0]

        dimensions = entities.get("dimensions", [])
        measures = entities.get("measures", [])

        if intent == "drill_through":
            return self._drill_through(filters, agent_input.page)
        elif intent == "pivot":
            return self._pivot(entities, filters, dimensions, measures)
        else:
            # slice / dice / general aggregation
            return self._aggregate(filters, dimensions, measures, intent)

    # ------------------------------------------------------------------
    # Slice / Dice
    # ------------------------------------------------------------------

    def _aggregate(
        self,
        filters: dict,
        dimensions: list[str],
        measures: list[str],
        intent: str,
    ) -> AgentOutput:
        # Default dimensions if none requested
        if not dimensions:
            dimensions = self._infer_dimensions(filters)

        dim_pairs = _resolve_dimensions(dimensions)
        meas_pairs = _resolve_measures(measures)

        if not dim_pairs:
            # Scalar aggregation (no GROUP BY)
            select_parts = [f"{expr} AS {alias}" for alias, expr in meas_pairs]
            select_clause = ", ".join(select_parts)
            where, params = _build_where(filters)
            sql = f"SELECT {select_clause} {BASE_JOINS} {where}"
        else:
            dim_select = ", ".join(f"{expr} AS {alias}" for alias, expr in dim_pairs)
            meas_select = ", ".join(f"{expr} AS {alias}" for alias, expr in meas_pairs)
            group_by = ", ".join(str(i + 1) for i in range(len(dim_pairs)))
            where, params = _build_where(filters)

            sql = (
                f"SELECT {dim_select}, {meas_select} "
                f"{BASE_JOINS} "
                f"{where} "
                f"GROUP BY {group_by} "
                f"ORDER BY {group_by}"
            )

        try:
            columns, rows = execute_query(sql, params)
        except Exception as exc:
            return AgentOutput(agent_name=self.name, error=str(exc), sql_query=sql)

        viz = self._suggest_viz(dim_pairs, meas_pairs)
        follow_ups = self._follow_up_suggestions(dimensions, filters, intent)

        return AgentOutput(
            agent_name=self.name,
            sql_query=sql,
            data=self._make_data_payload(columns, rows),
            visualization_hint=viz,
            follow_up_suggestions=follow_ups,
        )

    def _infer_dimensions(self, filters: dict) -> list[str]:
        """Guess sensible default dimensions based on what's NOT already filtered."""
        if "region" not in filters and "country" not in filters:
            return ["region"]
        if "category" not in filters:
            return ["category"]
        if "year" not in filters:
            return ["year"]
        return ["region", "category"]

    # ------------------------------------------------------------------
    # Pivot
    # ------------------------------------------------------------------

    def _pivot(
        self,
        entities: dict,
        filters: dict,
        dimensions: list[str],
        measures: list[str],
    ) -> AgentOutput:
        # Default pivot: region (row) × quarter (column) × revenue (value)
        row_dim = dimensions[0] if dimensions else "region"
        col_dim = dimensions[1] if len(dimensions) > 1 else "quarter"
        meas = measures[0] if measures else "revenue"

        row_col = DIM_SQL.get(row_dim, "g.region")
        pivot_col = DIM_SQL.get(col_dim, "d.quarter_name")
        meas_expr = MEASURE_SQL.get(meas, "SUM(f.revenue)")

        where, params = _build_where(filters)

        sql = f"""
PIVOT (
    SELECT {row_col} AS {row_dim},
           {pivot_col} AS {col_dim},
           {meas_expr} AS {meas}
    {BASE_JOINS}
    {where}
    GROUP BY 1, 2
)
ON {col_dim}
USING SUM({meas})
GROUP BY {row_dim}
ORDER BY {row_dim}
""".strip()

        try:
            columns, rows = execute_query(sql, params)
        except Exception as exc:
            # Fallback: standard aggregation if PIVOT fails
            logger.warning("PIVOT failed (%s), falling back to regular aggregation", exc)
            return self._aggregate(filters, [row_dim, col_dim], [meas], "dice")

        return AgentOutput(
            agent_name=self.name,
            sql_query=sql,
            data=self._make_data_payload(columns, rows),
            visualization_hint={"chart_type": "heatmap", "x_axis": col_dim, "y_axis": row_dim},
            follow_up_suggestions=[
                f"Drill down into the best performing {row_dim}",
                f"Compare year-over-year {meas}",
            ],
        )

    # ------------------------------------------------------------------
    # Drill-through
    # ------------------------------------------------------------------

    def _drill_through(self, filters: dict, page: int) -> AgentOutput:
        page_size = settings.drill_through_page_size
        offset = (page - 1) * page_size
        where, params = _build_where(filters)

        sql = f"""
SELECT
    f.sale_id,
    d.full_date AS order_date,
    d.year,
    d.quarter_name AS quarter,
    d.month_name AS month,
    g.region,
    g.country,
    p.category,
    p.subcategory,
    p.product_name,
    c.customer_name,
    c.customer_segment,
    f.quantity,
    f.unit_price,
    f.revenue,
    f.cost,
    f.profit,
    ROUND(f.profit_margin * 100, 2) AS profit_margin_pct
{BASE_JOINS}
{where}
ORDER BY d.full_date DESC, f.sale_id
LIMIT {page_size} OFFSET {offset}
""".strip()

        try:
            columns, rows = execute_query(sql, params)
        except Exception as exc:
            return AgentOutput(agent_name=self.name, error=str(exc), sql_query=sql)

        return AgentOutput(
            agent_name=self.name,
            sql_query=sql,
            data=self._make_data_payload(columns, rows),
            visualization_hint={"chart_type": "table"},
            follow_up_suggestions=[
                "Roll up to monthly totals",
                "Filter to a specific category",
            ],
        )

    # ------------------------------------------------------------------
    # Visualisation hint helper
    # ------------------------------------------------------------------

    def _suggest_viz(self, dim_pairs, meas_pairs) -> dict:
        dim_keys = [a for a, _ in dim_pairs]
        has_time = any(d in dim_keys for d in ["year", "quarter", "month", "month_name"])
        has_multi_dim = len(dim_pairs) >= 2

        if has_time and len(dim_pairs) == 1:
            chart = "line"
        elif len(dim_pairs) == 0:
            chart = "table"
        elif has_multi_dim:
            chart = "heatmap"
        else:
            chart = "bar"

        return {
            "chart_type": chart,
            "x_axis": dim_keys[0] if dim_keys else None,
            "y_axis": meas_pairs[0][0] if meas_pairs else None,
            "color_by": dim_keys[1] if len(dim_keys) > 1 else None,
        }

    def _follow_up_suggestions(self, dimensions, filters, intent) -> list[str]:
        suggestions = []
        if "year" in dimensions or "year" in filters:
            suggestions.append("Compare this to the previous year")
        if "region" in dimensions:
            suggestions.append("Drill into the top-performing region by country")
        if "category" in dimensions:
            suggestions.append("Break down by subcategory")
        suggestions.append("Show me the underlying transactions")
        return suggestions[:3]
