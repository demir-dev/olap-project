"""
Anomaly Detection Agent (Optional — for A+ grade)
==================================================
Detects statistical outliers in time series data using Z-score analysis
applied entirely in DuckDB (no external libraries required).

Usage: Ask questions like:
  - "Are there any unusual spikes in revenue?"
  - "Detect anomalies in monthly sales"
  - "Which months had abnormal performance?"

Sensitivity levels (Z-score threshold):
  low    → |z| > 3.0 (only extreme outliers)
  medium → |z| > 2.0 (default)
  high   → |z| > 1.5 (more sensitive)
"""

import logging

from app.agents.base_agent import AgentInput, AgentOutput, BaseAgent
from app.dependencies import execute_query

logger = logging.getLogger(__name__)

SENSITIVITY_THRESHOLDS = {
    "low":    3.0,
    "medium": 2.0,
    "high":   1.5,
}

FILTER_SQL = {
    "region":           "g.region",
    "country":          "g.country",
    "year":             "d.year",
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


class AnomalyDetectionAgent(BaseAgent):

    @property
    def name(self) -> str:
        return "AnomalyDetectionAgent"

    def execute(self, agent_input: AgentInput) -> AgentOutput:
        entities = agent_input.entities
        ctx = agent_input.session_context

        measure = (entities.get("measures") or ["revenue"])[0]
        sensitivity = entities.get("sensitivity", "medium")
        threshold = SENSITIVITY_THRESHOLDS.get(sensitivity, 2.0)

        # Filters from context + entities
        filters: dict = dict(ctx.get("active_filters", {}))
        if entities.get("regions"):
            filters["region"] = entities["regions"][0]
        if entities.get("categories"):
            filters["category"] = entities["categories"][0]
        if entities.get("years"):
            filters["year"] = entities["years"][0]

        where_clauses, params = [], []
        for k, v in filters.items():
            col = FILTER_SQL.get(k)
            if col:
                if isinstance(v, list):
                    ph = ", ".join("?" * len(v))
                    where_clauses.append(f"{col} IN ({ph})")
                    params.extend(v)
                else:
                    where_clauses.append(f"{col} = ?")
                    params.append(v)
        where = ("WHERE " + " AND ".join(where_clauses)) if where_clauses else ""

        meas_col = "SUM(f.revenue)" if measure == "revenue" else f"SUM(f.{measure})"

        sql = f"""
WITH monthly AS (
    SELECT
        d.year,
        d.month,
        d.month_name,
        {meas_col} AS metric
    {BASE_JOINS}
    {where}
    GROUP BY d.year, d.month, d.month_name
),
stats AS (
    SELECT
        AVG(metric) AS mean_val,
        STDDEV_POP(metric) AS std_val
    FROM monthly
),
scored AS (
    SELECT
        m.year,
        m.month,
        m.month_name,
        m.metric AS {measure},
        s.mean_val AS global_mean,
        s.std_val AS global_stddev,
        ROUND(
            CASE WHEN s.std_val > 0
                 THEN (m.metric - s.mean_val) / s.std_val
                 ELSE 0
            END, 3
        ) AS z_score,
        CASE
            WHEN s.std_val > 0
                 AND ABS((m.metric - s.mean_val) / s.std_val) > {threshold}
            THEN 'ANOMALY'
            ELSE 'normal'
        END AS status
    FROM monthly m
    CROSS JOIN stats s
)
SELECT *
FROM scored
ORDER BY ABS(z_score) DESC
""".strip()

        try:
            columns, rows = execute_query(sql, params)
        except Exception as exc:
            return AgentOutput(agent_name=self.name, error=str(exc), sql_query=sql)

        anomaly_rows = [r for r in rows if len(r) >= 8 and r[7] == "ANOMALY"]
        normal_count = len(rows) - len(anomaly_rows)

        if not anomaly_rows:
            narrative = (
                f"No anomalies detected in {measure} at {sensitivity} sensitivity "
                f"(threshold: |z| > {threshold}). "
                f"All {len(rows)} months are within normal range."
            )
        else:
            top = anomaly_rows[0]
            direction = "spike" if top[5] > 0 else "drop"  # z_score > 0 = above mean
            narrative = (
                f"Detected {len(anomaly_rows)} anomalous month(s) out of {len(rows)} total. "
                f"Most notable: {top[2]} {top[0]} showed a {direction} "
                f"(z-score: {top[6]:.2f}, {threshold}σ threshold). "
                f"{normal_count} months were within normal range."
            )

        return AgentOutput(
            agent_name=self.name,
            sql_query=sql,
            data=self._make_data_payload(columns, rows),
            narrative=narrative,
            visualization_hint={
                "chart_type": "line",
                "x_axis": "month_name",
                "y_axis": measure,
                "color_by": "status",
            },
            follow_up_suggestions=[
                "Show only the anomalous months",
                "What caused the spike in that period?",
                f"Compare {measure} to the same months in prior years",
            ],
        )
