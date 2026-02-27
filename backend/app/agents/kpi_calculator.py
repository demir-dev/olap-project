"""
KPI Calculator Agent
====================
Computes business KPIs: Year-over-Year growth, Month-over-Month change,
profit margins, Top-N rankings, and market share.
"""

import logging
from typing import Any

import pandas as pd

from app.agents.base_agent import AgentInput, AgentOutput, BaseAgent
from app.dependencies import execute_query

logger = logging.getLogger(__name__)

FILTER_SQL = {
    "region":           "g.region",
    "country":          "g.country",
    "year":             "d.year",
    "quarter":          "d.quarter_name",
    "month":            "d.month",
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

MEASURE_SQL = {
    "revenue":       "SUM(f.revenue)",
    "profit":        "SUM(f.profit)",
    "cost":          "SUM(f.cost)",
    "quantity":      "SUM(f.quantity)",
    "profit_margin": "ROUND(AVG(f.profit_margin) * 100, 2)",
    "orders":        "COUNT(f.sale_id)",
    "avg_order":     "ROUND(AVG(f.revenue), 2)",
}

DIM_SQL = {
    "region":           "g.region",
    "country":          "g.country",
    "category":         "p.category",
    "subcategory":      "p.subcategory",
    "customer_segment": "c.customer_segment",
    "year":             "d.year",
    "quarter":          "d.quarter_name",
    "month":            "d.month_name",
}


def _build_where(filters: dict) -> tuple[str, list]:
    clauses, params = [], []
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
    return ("WHERE " + " AND ".join(clauses)) if clauses else "", params


class KPICalculatorAgent(BaseAgent):

    @property
    def name(self) -> str:
        return "KPICalculator"

    def execute(self, agent_input: AgentInput) -> AgentOutput:
        entities = agent_input.entities
        ctx = agent_input.session_context

        # Determine KPI type
        kpi_type = entities.get("kpi_type", "")
        intent = agent_input.intent

        if kpi_type in ("compare_periods", "compare_period"):
            return self._compare_periods(entities, ctx)
        elif kpi_type in ("mom_growth", "mom"):
            return self._mom_change(entities, ctx)
        elif intent == "compare":
            # Two specific years → side-by-side delta table; otherwise YoY trend
            if len(entities.get("years", [])) >= 2:
                return self._compare_periods(entities, ctx)
            return self._yoy_growth(entities, ctx)
        elif kpi_type in ("yoy_growth", "yoy"):
            return self._yoy_growth(entities, ctx)
        elif kpi_type in ("top_n", "top", "ranking") or entities.get("top_n"):
            return self._top_n(entities, ctx)
        elif kpi_type == "margin" or "margin" in agent_input.message.lower():
            return self._margin_analysis(entities, ctx)
        elif kpi_type == "market_share":
            return self._market_share(entities, ctx)
        else:
            # Default: YoY if years mentioned, else top-N
            if entities.get("years") and len(entities["years"]) >= 2:
                return self._yoy_growth(entities, ctx)
            elif entities.get("top_n"):
                return self._top_n(entities, ctx)
            else:
                return self._yoy_growth(entities, ctx)

    # ------------------------------------------------------------------
    # Compare Periods (pandas merge-based delta analysis)
    # ------------------------------------------------------------------

    def _compare_periods(self, entities: dict, ctx: dict) -> AgentOutput:
        """Compare two specific years using pandas merge for delta computation."""
        years = entities.get("years", [])
        if len(years) < 2:
            # Fall back to YoY if not enough years specified
            return self._yoy_growth(entities, ctx)

        year_a, year_b = int(years[0]), int(years[1])
        measure = (entities.get("measures") or ["revenue"])[0]
        meas_expr = MEASURE_SQL.get(measure, MEASURE_SQL["revenue"])

        # Determine dimension
        dim_key = "category"
        for candidate in ["region", "category", "customer_segment", "country", "subcategory"]:
            if candidate in entities.get("dimensions", []):
                dim_key = candidate
                break
        dim_expr = DIM_SQL.get(dim_key, "p.category")

        sql_a = f"""
SELECT {dim_expr} AS dimension, {meas_expr} AS value_{year_a}
{BASE_JOINS}
WHERE d.year = {year_a}
GROUP BY {dim_expr}
ORDER BY value_{year_a} DESC
""".strip()

        sql_b = f"""
SELECT {dim_expr} AS dimension, {meas_expr} AS value_{year_b}
{BASE_JOINS}
WHERE d.year = {year_b}
GROUP BY {dim_expr}
ORDER BY value_{year_b} DESC
""".strip()

        try:
            cols_a, rows_a = execute_query(sql_a)
            cols_b, rows_b = execute_query(sql_b)
        except Exception as exc:
            return AgentOutput(agent_name=self.name, error=str(exc), sql_query=sql_a)

        df_a = pd.DataFrame(rows_a, columns=cols_a)
        df_b = pd.DataFrame(rows_b, columns=cols_b)

        df = pd.merge(df_a, df_b, on="dimension", how="outer").fillna(0)
        col_a = f"value_{year_a}"
        col_b = f"value_{year_b}"
        df["delta"] = (df[col_b] - df[col_a]).round(2)
        df["delta_pct"] = df.apply(
            lambda r: round((r[col_b] - r[col_a]) / r[col_a] * 100, 2) if r[col_a] != 0 else 0.0,
            axis=1,
        )
        df = df.sort_values("delta_pct", ascending=False)

        columns = list(df.columns)
        rows = [list(row) for row in df.itertuples(index=False, name=None)]
        combined_sql = f"-- Year A:\n{sql_a}\n-- Year B:\n{sql_b}"

        return AgentOutput(
            agent_name=self.name,
            sql_query=combined_sql,
            data=self._make_data_payload(columns, rows),
            visualization_hint={"chart_type": "bar", "x_axis": "dimension", "y_axis": "delta_pct"},
            follow_up_suggestions=[
                f"Which {dim_key} grew fastest in {year_b}?",
                "Show the absolute delta instead of percentage",
                f"Drill into the top performer in {year_b}",
            ],
        )

    # ------------------------------------------------------------------
    # Year-over-Year Growth
    # ------------------------------------------------------------------

    def _yoy_growth(self, entities: dict, ctx: dict) -> AgentOutput:
        measure = (entities.get("measures") or ["revenue"])[0]
        meas_expr = MEASURE_SQL.get(measure, MEASURE_SQL["revenue"])

        # Dimension to group by
        dim_key = None
        for candidate in ["region", "category", "customer_segment", "country"]:
            if candidate in entities.get("dimensions", []) or candidate in entities.get("filters", {}):
                dim_key = candidate
                break

        filters = dict(ctx.get("active_filters", {}))
        filters.update(entities.get("filters", {}))
        if entities.get("regions"):
            filters["region"] = entities["regions"][0] if len(entities["regions"]) == 1 else entities["regions"]
        if entities.get("categories"):
            filters["category"] = entities["categories"][0] if len(entities["categories"]) == 1 else entities["categories"]

        if dim_key:
            dim_expr = DIM_SQL[dim_key]
            sql = f"""
WITH yearly AS (
    SELECT
        {dim_expr} AS dimension,
        d.year,
        {meas_expr} AS metric
    {BASE_JOINS}
    GROUP BY {dim_expr}, d.year
),
yoy AS (
    SELECT
        curr.dimension,
        curr.year,
        curr.metric AS current_value,
        prev.metric AS prior_value,
        ROUND(
            CASE WHEN prev.metric > 0
                 THEN ((curr.metric - prev.metric) / prev.metric) * 100
                 ELSE NULL
            END, 2
        ) AS yoy_growth_pct
    FROM yearly curr
    LEFT JOIN yearly prev
        ON curr.dimension = prev.dimension AND curr.year = prev.year + 1
)
SELECT * FROM yoy
ORDER BY dimension, year
""".strip()
        else:
            sql = f"""
WITH yearly AS (
    SELECT
        d.year,
        {meas_expr} AS metric
    {BASE_JOINS}
    GROUP BY d.year
)
SELECT
    curr.year,
    curr.metric AS current_value,
    prev.metric AS prior_value,
    ROUND(
        CASE WHEN prev.metric > 0
             THEN ((curr.metric - prev.metric) / prev.metric) * 100
             ELSE NULL
        END, 2
    ) AS yoy_growth_pct
FROM yearly curr
LEFT JOIN yearly prev ON curr.year = prev.year + 1
ORDER BY curr.year
""".strip()

        try:
            columns, rows = execute_query(sql)
        except Exception as exc:
            return AgentOutput(agent_name=self.name, error=str(exc), sql_query=sql)

        follow_ups = [
            "Break down this growth by quarter",
            "Which category had the fastest growth?",
            "Show month-over-month trend for the latest year",
        ]

        return AgentOutput(
            agent_name=self.name,
            sql_query=sql,
            data=self._make_data_payload(columns, rows),
            visualization_hint={"chart_type": "bar", "x_axis": "year", "y_axis": "yoy_growth_pct"},
            follow_up_suggestions=follow_ups,
        )

    # ------------------------------------------------------------------
    # Month-over-Month Change
    # ------------------------------------------------------------------

    def _mom_change(self, entities: dict, ctx: dict) -> AgentOutput:
        measure = (entities.get("measures") or ["revenue"])[0]
        meas_expr = MEASURE_SQL.get(measure, MEASURE_SQL["revenue"])

        filters = dict(ctx.get("active_filters", {}))
        if entities.get("years"):
            filters["year"] = entities["years"][0]
        if entities.get("categories"):
            filters["category"] = entities["categories"][0]
        if entities.get("regions"):
            filters["region"] = entities["regions"][0]

        where, params = _build_where(filters)

        sql = f"""
WITH monthly AS (
    SELECT
        d.year,
        d.month,
        d.month_name,
        {meas_expr} AS metric
    {BASE_JOINS}
    {where}
    GROUP BY d.year, d.month, d.month_name
    ORDER BY d.year, d.month
),
mom AS (
    SELECT
        year,
        month,
        month_name,
        metric AS current_value,
        LAG(metric) OVER (ORDER BY year, month) AS prior_month_value,
        ROUND(
            CASE WHEN LAG(metric) OVER (ORDER BY year, month) > 0
                 THEN ((metric - LAG(metric) OVER (ORDER BY year, month))
                       / LAG(metric) OVER (ORDER BY year, month)) * 100
                 ELSE NULL
            END, 2
        ) AS mom_growth_pct
    FROM monthly
)
SELECT * FROM mom
ORDER BY year, month
""".strip()

        try:
            columns, rows = execute_query(sql, params)
        except Exception as exc:
            return AgentOutput(agent_name=self.name, error=str(exc), sql_query=sql)

        return AgentOutput(
            agent_name=self.name,
            sql_query=sql,
            data=self._make_data_payload(columns, rows),
            visualization_hint={"chart_type": "line", "x_axis": "month_name", "y_axis": "mom_growth_pct"},
            follow_up_suggestions=[
                "Show absolute revenue values by month",
                "Which month had the highest growth?",
                "Compare to the same months last year",
            ],
        )

    # ------------------------------------------------------------------
    # Top-N Rankings
    # ------------------------------------------------------------------

    def _top_n(self, entities: dict, ctx: dict) -> AgentOutput:
        n = entities.get("top_n", 5)
        ascending = entities.get("ascending", False)   # True = bottom-N / worst performers
        measure = (entities.get("measures") or ["revenue"])[0]
        # For "worst margin" → rank by margin ascending
        if ascending and "margin" in str(entities.get("kpi_type", "")) or \
           ascending and "margin" in str(entities.get("measures", [])):
            measure = "profit_margin"
        meas_expr = MEASURE_SQL.get(measure, MEASURE_SQL["revenue"])
        order_dir = "ASC" if ascending else "DESC"
        rank_dir = "ASC" if ascending else "DESC"

        # Dimension to rank by
        dim_key = "region"
        for candidate in ["subcategory", "product_name", "country", "customer_segment", "category", "region"]:
            if candidate in entities.get("dimensions", []):
                dim_key = candidate
                break

        dim_expr = DIM_SQL.get(dim_key, "g.region")

        filters = dict(ctx.get("active_filters", {}))
        filters.update(entities.get("filters", {}))
        if entities.get("regions"):
            filters["region"] = entities["regions"][0]
        if entities.get("years"):
            filters["year"] = entities["years"][0]
        if entities.get("categories"):
            filters["category"] = entities["categories"][0]

        where, params = _build_where(filters)
        n_val = int(n) if isinstance(n, (int, float, str)) else 5

        sql = f"""
SELECT
    {dim_expr} AS {dim_key},
    {meas_expr} AS {measure},
    ROUND({MEASURE_SQL['profit_margin']}, 2) AS profit_margin_pct,
    {MEASURE_SQL['orders']} AS transactions,
    RANK() OVER (ORDER BY {meas_expr} {rank_dir}) AS rank
{BASE_JOINS}
{where}
GROUP BY {dim_expr}
ORDER BY {measure} {order_dir}
LIMIT {n_val}
""".strip()

        try:
            columns, rows = execute_query(sql, params)
        except Exception as exc:
            return AgentOutput(agent_name=self.name, error=str(exc), sql_query=sql)

        label = "bottom" if ascending else "top"
        return AgentOutput(
            agent_name=self.name,
            sql_query=sql,
            data=self._make_data_payload(columns, rows),
            visualization_hint={"chart_type": "bar", "x_axis": dim_key, "y_axis": measure},
            follow_up_suggestions=[
                f"Drill into the {label} {dim_key}",
                f"Show {'top' if ascending else 'bottom'} {n_val} instead",
                f"Compare {label} {dim_key} year over year",
            ],
        )

    # ------------------------------------------------------------------
    # Margin Analysis
    # ------------------------------------------------------------------

    def _margin_analysis(self, entities: dict, ctx: dict) -> AgentOutput:
        dim_key = "category"
        if entities.get("dimensions"):
            dim_key = entities["dimensions"][0]

        dim_expr = DIM_SQL.get(dim_key, "p.category")

        filters = dict(ctx.get("active_filters", {}))
        if entities.get("years"):
            filters["year"] = entities["years"][0]
        if entities.get("regions"):
            filters["region"] = entities["regions"][0]

        where, params = _build_where(filters)

        sql = f"""
SELECT
    {dim_expr} AS {dim_key},
    SUM(f.revenue)  AS total_revenue,
    SUM(f.profit)   AS total_profit,
    ROUND(AVG(f.profit_margin) * 100, 2) AS avg_margin_pct,
    ROUND(SUM(f.profit) / SUM(f.revenue) * 100, 2) AS blended_margin_pct,
    COUNT(f.sale_id) AS transactions
{BASE_JOINS}
{where}
GROUP BY {dim_expr}
ORDER BY blended_margin_pct DESC
""".strip()

        try:
            columns, rows = execute_query(sql, params)
        except Exception as exc:
            return AgentOutput(agent_name=self.name, error=str(exc), sql_query=sql)

        return AgentOutput(
            agent_name=self.name,
            sql_query=sql,
            data=self._make_data_payload(columns, rows),
            visualization_hint={"chart_type": "bar", "x_axis": dim_key, "y_axis": "blended_margin_pct"},
            follow_up_suggestions=[
                "Show margin trend over time",
                "Which subcategory has the lowest margin?",
                "Compare margins by customer segment",
            ],
        )

    # ------------------------------------------------------------------
    # Market Share
    # ------------------------------------------------------------------

    def _market_share(self, entities: dict, ctx: dict) -> AgentOutput:
        dim_key = entities.get("dimensions", ["region"])[0] if entities.get("dimensions") else "region"
        dim_expr = DIM_SQL.get(dim_key, "g.region")

        filters = dict(ctx.get("active_filters", {}))
        if entities.get("years"):
            filters["year"] = entities["years"][0]

        where, params = _build_where(filters)

        sql = f"""
WITH totals AS (
    SELECT {dim_expr} AS dim, SUM(f.revenue) AS rev
    {BASE_JOINS}
    {where}
    GROUP BY {dim_expr}
),
grand AS (SELECT SUM(rev) AS total FROM totals)
SELECT
    t.dim AS {dim_key},
    t.rev AS revenue,
    ROUND(t.rev / g.total * 100, 2) AS market_share_pct
FROM totals t
CROSS JOIN grand g
ORDER BY t.rev DESC
""".strip()

        try:
            columns, rows = execute_query(sql, params)
        except Exception as exc:
            return AgentOutput(agent_name=self.name, error=str(exc), sql_query=sql)

        return AgentOutput(
            agent_name=self.name,
            sql_query=sql,
            data=self._make_data_payload(columns, rows),
            visualization_hint={"chart_type": "pie", "x_axis": dim_key, "y_axis": "market_share_pct"},
            follow_up_suggestions=[
                "How has market share shifted over the years?",
                "Which category is growing its share fastest?",
            ],
        )
