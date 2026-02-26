"""
Dimension Navigator Agent
=========================
Handles hierarchy navigation: Drill-down and Roll-up operations.

Hierarchies:
  Time:      Year → Quarter → Month
  Geography: Region → Country
  Product:   Category → Subcategory → Product Name

Also answers "what dimensions/members exist?" queries.
"""

import logging
from typing import Any

from app.agents.base_agent import AgentInput, AgentOutput, BaseAgent
from app.dependencies import execute_query

logger = logging.getLogger(__name__)

# Hierarchy level definitions: {level_name: (table_alias, column_name, next_level)}
TIME_HIERARCHY = ["year", "quarter", "month"]
GEO_HIERARCHY  = ["region", "country"]
PROD_HIERARCHY = ["category", "subcategory", "product_name"]

LEVEL_SQL = {
    "year":         ("d", "year",             "d.year"),
    "quarter":      ("d", "quarter_name",      "d.quarter_name"),
    "month":        ("d", "month_name",        "d.month_name"),
    "region":       ("g", "region",            "g.region"),
    "country":      ("g", "country",           "g.country"),
    "category":     ("p", "category",          "p.category"),
    "subcategory":  ("p", "subcategory",       "p.subcategory"),
    "product_name": ("p", "product_name",      "p.product_name"),
    "customer_segment": ("c", "customer_segment", "c.customer_segment"),
}

FILTER_SQL = {
    "region":           "g.region",
    "country":          "g.country",
    "year":             "d.year",
    "quarter":          "d.quarter_name",
    "month":            "d.month_name",
    "category":         "p.category",
    "subcategory":      "p.subcategory",
    "customer_segment": "c.customer_segment",
}

BASE_JOINS = """
FROM fact_sales f
JOIN dim_date      d ON f.date_key     = d.date_key
JOIN dim_geography g ON f.geo_key      = g.geo_key
JOIN dim_product   p ON f.product_key  = p.product_key
JOIN dim_customer  c ON f.customer_key = c.customer_key
"""


def _next_level(hierarchy: list[str], current: str) -> str | None:
    if current in hierarchy:
        idx = hierarchy.index(current)
        return hierarchy[idx + 1] if idx + 1 < len(hierarchy) else None
    return None


def _prev_level(hierarchy: list[str], current: str) -> str | None:
    if current in hierarchy:
        idx = hierarchy.index(current)
        return hierarchy[idx - 1] if idx > 0 else None
    return None


def _which_hierarchy(level: str) -> list[str] | None:
    if level in TIME_HIERARCHY:
        return TIME_HIERARCHY
    if level in GEO_HIERARCHY:
        return GEO_HIERARCHY
    if level in PROD_HIERARCHY:
        return PROD_HIERARCHY
    return None


class DimensionNavigatorAgent(BaseAgent):

    @property
    def name(self) -> str:
        return "DimensionNavigator"

    def execute(self, agent_input: AgentInput) -> AgentOutput:
        intent = agent_input.intent
        entities = agent_input.entities
        ctx = agent_input.session_context

        if intent == "dimensions":
            return self._list_members(entities, ctx)
        elif intent == "drill_down":
            return self._drill_down(entities, ctx)
        elif intent == "roll_up":
            return self._roll_up(entities, ctx)
        else:
            # Fallback: list members
            return self._list_members(entities, ctx)

    # ------------------------------------------------------------------
    # List dimension members
    # ------------------------------------------------------------------

    def _list_members(self, entities: dict, ctx: dict) -> AgentOutput:
        dimension = entities.get("dimension", entities.get("dimensions", ["region"]))[0] \
            if isinstance(entities.get("dimensions"), list) else entities.get("dimension", "region")

        level_info = LEVEL_SQL.get(dimension)
        if level_info is None:
            dimension = "region"
            level_info = LEVEL_SQL["region"]

        _, col, full_col = level_info
        sql = f"SELECT DISTINCT {full_col} AS {dimension}, COUNT(f.sale_id) AS transactions {BASE_JOINS} GROUP BY 1 ORDER BY 2 DESC"

        columns, rows = execute_query(sql)
        follow_ups = [
            f"Show revenue by {dimension}",
            f"Which {dimension} has the highest profit margin?",
        ]
        return AgentOutput(
            agent_name=self.name,
            sql_query=sql,
            data=self._make_data_payload(columns, rows),
            visualization_hint={"chart_type": "bar", "x_axis": dimension, "y_axis": "transactions"},
            follow_up_suggestions=follow_ups,
        )

    # ------------------------------------------------------------------
    # Drill-down: go to finer granularity
    # ------------------------------------------------------------------

    def _drill_down(self, entities: dict, ctx: dict) -> AgentOutput:
        # Determine starting level
        from_level = entities.get("from_level") or ctx.get("last_dimension")

        # Detect from context what hierarchy we're in
        if not from_level:
            if entities.get("years") or "year" in ctx.get("active_filters", {}):
                from_level = "year"
            elif entities.get("regions"):
                from_level = "region"
            elif entities.get("categories"):
                from_level = "category"
            else:
                from_level = "year"  # default

        hierarchy = _which_hierarchy(from_level) or TIME_HIERARCHY
        to_level = entities.get("to_level") or _next_level(hierarchy, from_level)

        if to_level is None:
            # Already at finest level
            return AgentOutput(
                agent_name=self.name,
                narrative=f"Already at the finest level of the {from_level} hierarchy.",
                follow_up_suggestions=["Roll up to see the summary", "Compare periods"],
            )

        # Build filters
        filters = dict(ctx.get("active_filters", {}))
        if entities.get("regions"):
            filters["region"] = entities["regions"][0]
        if entities.get("categories"):
            filters["category"] = entities["categories"][0]
        if entities.get("years"):
            filters["year"] = entities["years"][0]
        if entities.get("quarters"):
            filters["quarter"] = f"Q{entities['quarters'][0]}"

        return self._aggregate_at_level(to_level, filters, from_level)

    # ------------------------------------------------------------------
    # Roll-up: go to coarser granularity
    # ------------------------------------------------------------------

    def _roll_up(self, entities: dict, ctx: dict) -> AgentOutput:
        from_level = entities.get("from_level") or ctx.get("last_dimension", "month")
        hierarchy = _which_hierarchy(from_level) or TIME_HIERARCHY
        to_level = entities.get("to_level") or _prev_level(hierarchy, from_level)

        if to_level is None:
            return AgentOutput(
                agent_name=self.name,
                narrative=f"Already at the highest level of the {from_level} hierarchy.",
                follow_up_suggestions=["Drill down for more detail"],
            )

        filters = dict(ctx.get("active_filters", {}))
        return self._aggregate_at_level(to_level, filters, from_level)

    # ------------------------------------------------------------------
    # Common aggregation at a given dimension level
    # ------------------------------------------------------------------

    def _aggregate_at_level(self, level: str, filters: dict, context_level: str) -> AgentOutput:
        level_info = LEVEL_SQL.get(level)
        if level_info is None:
            return AgentOutput(agent_name=self.name, error=f"Unknown dimension level: {level}")

        _, col, full_col = level_info

        # Build WHERE
        where_clauses = []
        params = []
        for k, v in filters.items():
            col_expr = FILTER_SQL.get(k)
            if col_expr:
                if isinstance(v, list):
                    placeholders = ", ".join("?" * len(v))
                    where_clauses.append(f"{col_expr} IN ({placeholders})")
                    params.extend(v)
                else:
                    where_clauses.append(f"{col_expr} = ?")
                    params.append(v)

        where = ("WHERE " + " AND ".join(where_clauses)) if where_clauses else ""

        # Order by natural dimension order
        order_col = full_col
        if level in ["year", "month"]:
            order_col = LEVEL_SQL[level][2].replace("_name", "").replace("quarter_", "quarter")
            if level == "month":
                order_col = "d.month"
            elif level == "year":
                order_col = "d.year"

        sql = f"""
SELECT
    {full_col} AS {level},
    SUM(f.revenue)  AS revenue,
    SUM(f.profit)   AS profit,
    ROUND(AVG(f.profit_margin) * 100, 2) AS profit_margin_pct,
    COUNT(f.sale_id) AS transactions
{BASE_JOINS}
{where}
GROUP BY {full_col}
ORDER BY {order_col if level in ['year','month'] else full_col}
""".strip()

        try:
            columns, rows = execute_query(sql, params)
        except Exception as exc:
            return AgentOutput(agent_name=self.name, error=str(exc), sql_query=sql)

        # Viz suggestion
        hierarchy = _which_hierarchy(level) or TIME_HIERARCHY
        has_time = level in TIME_HIERARCHY
        chart = "line" if has_time else "bar"

        next_lv = _next_level(hierarchy, level)
        follow_ups = []
        if next_lv:
            follow_ups.append(f"Drill down from {level} to {next_lv}")
        follow_ups.append("Compare with the previous period")
        follow_ups.append("Show profit margin trend")

        return AgentOutput(
            agent_name=self.name,
            sql_query=sql,
            data=self._make_data_payload(columns, rows),
            visualization_hint={"chart_type": chart, "x_axis": level, "y_axis": "revenue"},
            follow_up_suggestions=follow_ups[:3],
        )
