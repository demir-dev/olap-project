"""
Report Generator Agent
======================
Synthesises results from other agents into:
  1. A formatted data table
  2. A plain-English narrative summary (LLM-generated or template-based)
  3. Follow-up question suggestions

This agent is ALWAYS called as the final step in the orchestrator pipeline
to add a narrative to results produced by any other agent.
"""

import logging
from typing import Any

import anthropic

from app.agents.base_agent import AgentInput, AgentOutput, BaseAgent
from app.config import settings

logger = logging.getLogger(__name__)

_anthropic_client: anthropic.Anthropic | None = None


def _get_client() -> anthropic.Anthropic | None:
    global _anthropic_client
    if _anthropic_client is None and settings.anthropic_api_key:
        _anthropic_client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
    return _anthropic_client


class ReportGeneratorAgent(BaseAgent):

    @property
    def name(self) -> str:
        return "ReportGenerator"

    def execute(self, agent_input: AgentInput) -> AgentOutput:
        # This agent usually decorates results already produced by another agent.
        # When called standalone it performs a simple summary query.
        return AgentOutput(agent_name=self.name, narrative="Report generator ready.")

    def generate_narrative(
        self,
        user_question: str,
        intent: str,
        data: dict[str, Any] | None,
        context: dict[str, Any],
    ) -> str:
        """
        Generate a plain-English narrative for the given query results.
        Uses LLM when API key is available, falls back to templates otherwise.
        """
        if data is None or data.get("row_count", 0) == 0:
            return "No data was found for your query. Try broadening the filters or rephrasing the question."

        client = _get_client()
        if client:
            return self._llm_narrative(client, user_question, intent, data)
        else:
            return self._template_narrative(intent, data)

    # ------------------------------------------------------------------
    # LLM-based narrative
    # ------------------------------------------------------------------

    def _llm_narrative(
        self,
        client: anthropic.Anthropic,
        user_question: str,
        intent: str,
        data: dict[str, Any],
    ) -> str:
        columns = data.get("columns", [])
        rows = data.get("rows", [])
        row_count = data.get("row_count", 0)

        # Summarise data for the prompt (top 10 rows to keep tokens low)
        sample_rows = rows[:10]
        table_str = _format_table_for_prompt(columns, sample_rows)

        system_prompt = """You are a concise business intelligence analyst.
Your job is to write a 2-4 sentence plain English summary of query results for a business user.
Rules:
- Focus on the most important insight (biggest number, fastest growth, biggest change).
- Use $ for revenue/profit figures. Round to 1 decimal place (e.g. $1.2M, $450K).
- Use % for margins and growth rates.
- Do NOT repeat the question verbatim.
- Do NOT mention SQL or technical terms.
- Mention if the data shows a clear trend, leader, or anomaly.
- Be direct and professional. No fluff."""

        user_prompt = f"""User asked: "{user_question}"
OLAP operation type: {intent}
Result ({row_count} rows, showing up to 10):

{table_str}

Write a 2-4 sentence business insight summary."""

        try:
            response = client.messages.create(
                model=settings.llm_model,
                max_tokens=256,
                temperature=settings.llm_temperature,
                system=system_prompt,
                messages=[{"role": "user", "content": user_prompt}],
            )
            return response.content[0].text.strip()
        except Exception as exc:
            logger.warning("LLM narrative generation failed: %s", exc)
            return self._template_narrative(intent, data)

    # ------------------------------------------------------------------
    # Template-based fallback narrative
    # ------------------------------------------------------------------

    def _template_narrative(self, intent: str, data: dict[str, Any]) -> str:
        columns = data.get("columns", [])
        rows = data.get("rows", [])
        row_count = data.get("row_count", 0)

        if row_count == 0:
            return "The query returned no results. Try different filters."

        templates = {
            "slice":         f"Filtered view returned {row_count} result(s). "
                             + _top_value_sentence(columns, rows),
            "dice":          f"Multi-dimensional filter returned {row_count} result(s). "
                             + _top_value_sentence(columns, rows),
            "drill_down":    f"Drill-down analysis shows {row_count} detail level(s). "
                             + _top_value_sentence(columns, rows),
            "roll_up":       f"Roll-up summary across {row_count} group(s). "
                             + _top_value_sentence(columns, rows),
            "compare":       f"Comparison across {row_count} period(s). "
                             + _growth_sentence(columns, rows),
            "kpi":           f"KPI analysis across {row_count} dimension member(s). "
                             + _top_value_sentence(columns, rows),
            "pivot":         f"Pivot table showing {row_count} row(s) across multiple dimensions.",
            "drill_through": f"Showing {row_count} raw transaction record(s).",
            "dimensions":    f"Found {row_count} distinct member(s) in this dimension.",
        }

        return templates.get(intent, f"Query returned {row_count} result(s). " + _top_value_sentence(columns, rows))

    def generate_structured_summary(
        self,
        user_question: str,
        intent: str,
        data: dict[str, Any] | None,
        context: dict[str, Any],
    ) -> dict[str, Any]:
        """
        Generate a structured executive summary with highlights and recommendations.
        Returns: {"text": str, "highlights": list[str], "recommendations": list[str]}
        LLM path: sends JSON-only system prompt. Falls back to template + empty lists.
        """
        default_result: dict[str, Any] = {"text": "", "highlights": [], "recommendations": []}

        if data is None or data.get("row_count", 0) == 0:
            default_result["text"] = "No data was found for your query."
            return default_result

        client = _get_client()
        if client:
            return self._llm_structured_summary(client, user_question, intent, data)
        else:
            default_result["text"] = self._template_narrative(intent, data)
            return default_result

    def _llm_structured_summary(
        self,
        client: anthropic.Anthropic,
        user_question: str,
        intent: str,
        data: dict[str, Any],
    ) -> dict[str, Any]:
        columns = data.get("columns", [])
        rows = data.get("rows", [])
        row_count = data.get("row_count", 0)
        sample_rows = rows[:10]
        table_str = _format_table_for_prompt(columns, sample_rows)

        system_prompt = """You are a concise business intelligence analyst.
Return ONLY a JSON object with exactly these keys:
{
  "text": "2-4 sentence plain English summary of the key insight",
  "highlights": ["bullet 1", "bullet 2", "bullet 3"],
  "recommendations": ["recommendation 1", "recommendation 2"]
}
Rules for text: Focus on biggest number, fastest growth, main trend. Use $, %, round to 1 decimal.
Rules for highlights: 2-4 short bullet points with specific numbers from the data.
Rules for recommendations: 1-3 actionable business recommendations based on the data.
Return ONLY the JSON object, no markdown, no extra text."""

        user_prompt = f"""User asked: "{user_question}"
OLAP operation: {intent}
Result ({row_count} rows, showing up to 10):

{table_str}

Return the JSON summary."""

        try:
            response = client.messages.create(
                model=settings.llm_model,
                max_tokens=512,
                temperature=settings.llm_temperature,
                system=system_prompt,
                messages=[{"role": "user", "content": user_prompt}],
            )
            raw = response.content[0].text.strip()
            # Robustly extract JSON
            import json as _json
            import re as _re
            json_match = _re.search(r"\{.*\}", raw, _re.DOTALL)
            if json_match:
                parsed = _json.loads(json_match.group())
                return {
                    "text": str(parsed.get("text", "")),
                    "highlights": list(parsed.get("highlights", [])),
                    "recommendations": list(parsed.get("recommendations", [])),
                }
        except Exception as exc:
            logger.warning("LLM structured summary failed: %s", exc)

        return {"text": self._template_narrative(intent, data), "highlights": [], "recommendations": []}

    def generate_follow_ups(
        self,
        user_question: str,
        intent: str,
        entities: dict[str, Any],
        existing_follow_ups: list[str],
    ) -> list[str]:
        """Enhance or replace follow-up suggestions using LLM if available."""
        if existing_follow_ups:
            return existing_follow_ups[:3]

        client = _get_client()
        if not client:
            return _default_follow_ups(intent)

        try:
            response = client.messages.create(
                model=settings.llm_model,
                max_tokens=200,
                temperature=0.3,
                system="Generate exactly 3 concise follow-up questions for a business intelligence user. Return only the 3 questions, one per line, no numbering, no explanations.",
                messages=[{
                    "role": "user",
                    "content": f"The user just asked: \"{user_question}\" (intent: {intent}). What are 3 logical follow-up questions about this OLAP data?",
                }],
            )
            lines = response.content[0].text.strip().split("\n")
            return [l.strip(" -•123.") for l in lines if l.strip()][:3]
        except Exception:
            return _default_follow_ups(intent)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _format_table_for_prompt(columns: list[str], rows: list[list]) -> str:
    if not columns or not rows:
        return "(empty)"
    header = " | ".join(columns)
    sep = "-" * len(header)
    body = "\n".join(" | ".join(str(v) for v in row) for row in rows[:10])
    return f"{header}\n{sep}\n{body}"


def _top_value_sentence(columns: list[str], rows: list[list]) -> str:
    if not rows:
        return ""
    # Find a numeric column
    label_col = columns[0] if columns else "item"
    value_col_idx = None
    for i, col in enumerate(columns):
        if any(kw in col.lower() for kw in ["revenue", "profit", "orders", "quantity", "metric", "value"]):
            value_col_idx = i
            break
    if value_col_idx is None:
        return ""
    top_row = rows[0]
    label = top_row[0]
    value = top_row[value_col_idx]
    if isinstance(value, (int, float)):
        if "margin" in columns[value_col_idx].lower() or "pct" in columns[value_col_idx].lower():
            return f"The top performer is {label} at {value:.1f}%."
        elif value >= 1_000_000:
            return f"The top performer is {label} with ${value/1_000_000:.1f}M."
        elif value >= 1_000:
            return f"The top performer is {label} with ${value/1_000:.1f}K."
        else:
            return f"The top performer is {label} with {value:,.0f}."
    return f"Leading value: {label}."


def _growth_sentence(columns: list[str], rows: list[list]) -> str:
    # Find a growth_pct column
    for i, col in enumerate(columns):
        if "growth" in col.lower() or "pct" in col.lower():
            vals = [row[i] for row in rows if row[i] is not None]
            if vals:
                latest = vals[-1]
                if isinstance(latest, (int, float)):
                    direction = "grew" if latest > 0 else "declined"
                    return f"Latest period {direction} by {abs(latest):.1f}%."
    return ""


def _default_follow_ups(intent: str) -> list[str]:
    defaults = {
        "slice":         ["Filter by another dimension", "Compare with the previous period", "Show underlying transactions"],
        "dice":          ["Drill down into the top result", "Compare year over year", "Show profit margins"],
        "drill_down":    ["Roll up to see the summary", "Compare periods", "Show top 5 performers"],
        "roll_up":       ["Drill down for more detail", "Compare growth rates", "Filter to a specific region"],
        "compare":       ["Break down growth by region", "Show month-over-month trend", "Which category drove the change?"],
        "kpi":           ["Show trend over time", "Compare across segments", "Break down by subcategory"],
        "pivot":         ["Drill into a cell", "Add another dimension", "Show as a chart"],
        "drill_through": ["Aggregate these transactions", "Filter to a specific customer", "Show totals by category"],
    }
    return defaults.get(intent, ["Show more detail", "Compare periods", "Filter by category"])
