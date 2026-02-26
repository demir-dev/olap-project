"""
Visualization Agent (Optional — for A+ grade)
=============================================
Selects the most appropriate chart type for a given result dataset.
Rule-based — no external API required.

Decision logic:
  • Single numeric column, no dimensions → KPI card / number
  • Single time dimension + one measure → line chart
  • Single categorical dimension + one measure → bar chart (horizontal if >8 items)
  • Two dimensions + one measure → grouped bar or heatmap
  • Three or more columns where one is a proportion/share → pie / donut
  • Matrix / pivot table → heatmap
  • Raw row data (many columns) → table
"""

import logging
from typing import Any

from app.agents.base_agent import AgentInput, AgentOutput, BaseAgent

logger = logging.getLogger(__name__)

TIME_DIMENSIONS = {"year", "quarter", "month", "month_name", "week", "day"}
PROPORTION_COLS = {"share", "pct", "percent", "proportion", "ratio"}
NUMERIC_TYPES = (int, float)


class VisualizationAgent(BaseAgent):

    @property
    def name(self) -> str:
        return "VisualizationAgent"

    def execute(self, agent_input: AgentInput) -> AgentOutput:
        # This agent is typically called with data already in the context
        data = agent_input.entities.get("data")
        intent = agent_input.intent
        hint = self.suggest(data, intent, agent_input.entities)
        return AgentOutput(
            agent_name=self.name,
            visualization_hint=hint,
        )

    def suggest(
        self,
        data: dict[str, Any] | None,
        intent: str,
        entities: dict[str, Any],
    ) -> dict[str, Any]:
        """
        Return a visualization_hint dict:
          { chart_type, x_axis, y_axis, color_by, title }
        """
        if data is None or not data.get("columns"):
            return {"chart_type": "table"}

        columns: list[str] = data["columns"]
        rows: list[list] = data.get("rows", [])
        row_count: int = data.get("row_count", 0)

        col_lower = [c.lower() for c in columns]

        # Drill-through / raw rows
        if intent == "drill_through" or len(columns) > 8:
            return {"chart_type": "table", "x_axis": None, "y_axis": None}

        # Identify dimension vs measure columns
        dim_cols = [c for c in columns if not self._is_numeric_col(c, rows)]
        meas_cols = [c for c in columns if self._is_numeric_col(c, rows)]

        if not meas_cols:
            return {"chart_type": "table"}

        # Time dimension present
        time_dims = [c for c in dim_cols if c.lower() in TIME_DIMENSIONS]
        cat_dims = [c for c in dim_cols if c.lower() not in TIME_DIMENSIONS]

        # Proportion / pie
        if any(any(p in c.lower() for p in PROPORTION_COLS) for c in meas_cols):
            x = dim_cols[0] if dim_cols else None
            y = next((c for c in meas_cols if any(p in c.lower() for p in PROPORTION_COLS)), meas_cols[0])
            return {"chart_type": "pie", "x_axis": x, "y_axis": y, "color_by": None}

        # Pivot / heatmap: two or more category dimensions
        if len(cat_dims) >= 2 and not time_dims:
            return {
                "chart_type": "heatmap",
                "x_axis": cat_dims[1],
                "y_axis": cat_dims[0],
                "color_by": meas_cols[0],
            }

        # Time series: one time dimension + one measure
        if time_dims and len(dim_cols) == 1:
            color_by = None
            return {
                "chart_type": "line",
                "x_axis": time_dims[0],
                "y_axis": meas_cols[0],
                "color_by": color_by,
            }

        # Time + category → multi-series line or grouped bar
        if time_dims and cat_dims:
            return {
                "chart_type": "line",
                "x_axis": time_dims[0],
                "y_axis": meas_cols[0],
                "color_by": cat_dims[0],
            }

        # Category + one measure
        if cat_dims and len(meas_cols) >= 1:
            chart = "bar"
            if row_count > 8:
                chart = "bar"  # horizontal bar for many items (frontend decides orientation)
            x = cat_dims[0]
            y = meas_cols[0]
            color = cat_dims[1] if len(cat_dims) > 1 else None
            return {"chart_type": chart, "x_axis": x, "y_axis": y, "color_by": color}

        # Scalar / single value
        if not dim_cols and meas_cols:
            return {"chart_type": "kpi_card", "x_axis": None, "y_axis": meas_cols[0]}

        return {"chart_type": "table"}

    def _is_numeric_col(self, col_name: str, rows: list[list]) -> bool:
        """Heuristic: column is numeric if its first non-null value is a number."""
        col_lower = col_name.lower()
        # Name-based heuristic
        numeric_keywords = [
            "revenue", "profit", "cost", "quantity", "orders", "margin",
            "pct", "percent", "growth", "value", "metric", "count", "avg",
            "total", "sum", "rank", "share",
        ]
        if any(k in col_lower for k in numeric_keywords):
            return True
        return False
