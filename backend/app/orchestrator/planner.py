"""
Planner / Orchestrator
======================
The "brain" that:
1. Classifies user intent (2-stage: keyword rules → LLM fallback)
2. Extracts entities (regions, categories, years, measures, etc.)
3. Routes to the appropriate agent(s)
4. Chains agents for complex queries
5. Calls ReportGenerator to add a narrative to every result
6. Manages session context (sticky filters)
"""

import json
import logging
import re
import time
from typing import Any

import anthropic

from app.agents.anomaly_detection import AnomalyDetectionAgent
from app.agents.base_agent import AgentInput, AgentOutput
from app.agents.cube_operations import CubeOperationsAgent
from app.agents.dimension_navigator import DimensionNavigatorAgent
from app.agents.kpi_calculator import KPICalculatorAgent
from app.agents.report_generator import ReportGeneratorAgent
from app.agents.visualization_agent import VisualizationAgent
from app.config import settings
from app.orchestrator.session import (
    ConversationTurn,
    SessionContext,
    get_or_create_session,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Keyword intent rules
# ---------------------------------------------------------------------------

INTENT_KEYWORDS: dict[str, list[str]] = {
    "drill_down": [
        "break down", "drill down", "drill into", "deeper", "granular",
        "by month", "by week", "by day", "more detail", "detailed",
    ],
    "roll_up": [
        "roll up", "summarize", "summarise", "aggregate", "overall",
        "high level", "at year level", "at quarter level",
    ],
    "compare": [
        " vs ", " versus ", "compared to", "year over year", "yoy",
        "month over month", "mom", "growth", "change from", "difference",
        "better than", "worse than",
    ],
    "kpi": [
        "top ", "bottom ", "best ", "worst ", "highest ", "lowest ",
        "margin", "profit margin", "growth rate", "market share",
        "ranking", "ranked", "leading", "lagging",
    ],
    "pivot": [
        "pivot", "cross tab", "as columns", "rotate", "transpose",
        "matrix view", "columns and rows",
    ],
    "drill_through": [
        "raw data", "raw transactions", "underlying", "individual",
        "actual orders", "line items", "show me the records",
        "show transactions", "actual sales",
    ],
    "dimensions": [
        "list all", "what are the", "show all", "available", "which regions",
        "which categories", "what categories", "what segments",
    ],
    "anomaly": [
        "anomal", "unusual", "spike", "outlier", "abnormal",
        "unexpected", "detect", "weird",
    ],
}

# ---------------------------------------------------------------------------
# Schema summary for LLM prompts
# ---------------------------------------------------------------------------

SCHEMA_SUMMARY = """
Star schema tables:
- fact_sales: sale_id, date_key, geo_key, product_key, customer_key,
              quantity, unit_price, unit_cost, revenue, cost, profit, profit_margin
- dim_date:   date_key, full_date, year(2022-2024), quarter(1-4), quarter_name(Q1-Q4),
              month(1-12), month_name, week, day
- dim_geography: geo_key, region(North America|Europe|Asia Pacific|Latin America), country
- dim_product:   product_key, product_name, category(Electronics|Furniture|Office Supplies|Clothing), subcategory
- dim_customer:  customer_key, customer_name, customer_segment(Consumer|Corporate|Home Office|Small Business)

Valid intents: slice, dice, drill_down, roll_up, compare, pivot, drill_through, kpi, dimensions, anomaly, report
""".strip()


# ---------------------------------------------------------------------------
# Planner
# ---------------------------------------------------------------------------

class Planner:

    def __init__(self) -> None:
        self._cube   = CubeOperationsAgent()
        self._nav    = DimensionNavigatorAgent()
        self._kpi    = KPICalculatorAgent()
        self._report = ReportGeneratorAgent()
        self._viz    = VisualizationAgent()
        self._anomaly = AnomalyDetectionAgent()
        self._llm_client: anthropic.Anthropic | None = None
        if settings.anthropic_api_key:
            self._llm_client = anthropic.Anthropic(api_key=settings.anthropic_api_key)

    # ------------------------------------------------------------------
    # Main entry point
    # ------------------------------------------------------------------

    def process(
        self,
        message: str,
        session_id: str | None,
        page: int = 1,
    ) -> dict[str, Any]:
        t0 = time.time()
        session = get_or_create_session(session_id)

        # 1. Classify intent + extract entities
        intent, entities = self._classify(message, session)
        logger.info("[%s] intent=%s entities=%s", session.session_id[:8], intent, entities)

        # 2. Build agent input
        agent_input = AgentInput(
            message=message,
            intent=intent,
            entities=entities,
            session_context={
                **session.resolved_context,
                "active_filters": session.resolved_context.get("active_filters", {}),
                "history_summary": session.get_context_summary(3),
            },
            schema_summary=SCHEMA_SUMMARY,
            page=page,
        )

        # 3. Route to agent(s)
        output, agents_used = self._route(intent, agent_input)

        # 4. Upgrade visualization hint using VisualizationAgent
        if output.data and not output.visualization_hint:
            viz_hint = self._viz.suggest(output.data, intent, entities)
            output.visualization_hint = viz_hint
        elif output.data and output.visualization_hint:
            # Let VisualizationAgent refine
            refined = self._viz.suggest(output.data, intent, entities)
            if refined.get("chart_type") != "table":
                output.visualization_hint = {**refined, **output.visualization_hint}

        # 5. Generate narrative via ReportGenerator
        narrative = self._report.generate_narrative(
            user_question=message,
            intent=intent,
            data=output.data,
            context=session.resolved_context,
        )
        output.narrative = narrative

        # 6. Generate follow-up suggestions
        follow_ups = self._report.generate_follow_ups(
            user_question=message,
            intent=intent,
            entities=entities,
            existing_follow_ups=output.follow_up_suggestions,
        )
        output.follow_up_suggestions = follow_ups

        # 7. Update session context
        session.update_context(entities)
        turn = ConversationTurn(
            turn_id=len(session.turns) + 1,
            message=message,
            intent=intent,
            entities=entities,
            sql_query=output.sql_query,
            data_summary=_summarise_data(output.data),
            narrative=narrative,
        )
        session.add_turn(turn)

        latency_ms = int((time.time() - t0) * 1000)

        return {
            "session_id":           session.session_id,
            "intent":               intent,
            "agents_used":          agents_used,
            "sql_query":            output.sql_query,
            "data":                 output.data,
            "narrative":            output.narrative,
            "visualization_hint":   output.visualization_hint,
            "follow_up_suggestions": output.follow_up_suggestions,
            "error":                output.error,
            "latency_ms":           latency_ms,
        }

    # ------------------------------------------------------------------
    # Intent classification (2-stage)
    # ------------------------------------------------------------------

    def _classify(
        self, message: str, session: SessionContext
    ) -> tuple[str, dict[str, Any]]:
        msg_lower = message.lower()

        # Stage 1: keyword rules
        scores: dict[str, int] = {}
        for intent, keywords in INTENT_KEYWORDS.items():
            score = sum(1 for kw in keywords if kw in msg_lower)
            if score > 0:
                scores[intent] = score

        if scores:
            best_intent = max(scores, key=scores.__getitem__)
            # Only skip LLM if we have a clear winner
            if scores[best_intent] >= 1:
                entities = self._extract_entities_regex(message)
                # Map anomaly → kpi for routing
                if best_intent == "anomaly":
                    entities["kpi_type"] = "anomaly"
                    best_intent = "anomaly"
                return best_intent, entities

        # Stage 2: LLM classification (when keyword matching gives no clear signal)
        if self._llm_client:
            return self._llm_classify(message, session)

        # Fallback: default to dice (most common OLAP operation)
        return "dice", self._extract_entities_regex(message)

    def _extract_entities_regex(self, message: str) -> dict[str, Any]:
        """Fast regex-based entity extraction."""
        msg = message.lower()
        entities: dict[str, Any] = {}

        # Regions
        region_map = {
            "north america": "North America",
            "europe":        "Europe",
            "asia pacific":  "Asia Pacific",
            "latin america": "Latin America",
            "apac":          "Asia Pacific",
            "latam":         "Latin America",
            "emea":          "Europe",
        }
        found_regions = [v for k, v in region_map.items() if k in msg]
        if found_regions:
            entities["regions"] = found_regions

        # Categories
        cat_map = {
            "electronics":     "Electronics",
            "furniture":       "Furniture",
            "office supplies": "Office Supplies",
            "clothing":        "Clothing",
        }
        found_cats = [v for k, v in cat_map.items() if k in msg]
        if found_cats:
            entities["categories"] = found_cats

        # Customer segments
        seg_map = {
            "consumer":       "Consumer",
            "corporate":      "Corporate",
            "home office":    "Home Office",
            "small business": "Small Business",
        }
        found_segs = [v for k, v in seg_map.items() if k in msg]
        if found_segs:
            entities["customer_segments"] = found_segs

        # Years (2020-2030)
        years = re.findall(r"\b(202[0-9])\b", msg)
        if years:
            entities["years"] = [int(y) for y in years]

        # Quarters (Q1-Q4 or "quarter 1" etc.)
        quarters = re.findall(r"q([1-4])\b|quarter\s+([1-4])", msg)
        flat_q = [int(a or b) for a, b in quarters]
        if flat_q:
            entities["quarters"] = flat_q

        # Months (by name)
        month_map = {
            "january":1,"february":2,"march":3,"april":4,"may":5,"june":6,
            "july":7,"august":8,"september":9,"october":10,"november":11,"december":12,
            "jan":1,"feb":2,"mar":3,"apr":4,"jun":6,
            "jul":7,"aug":8,"sep":9,"oct":10,"nov":11,"dec":12,
        }
        found_months = [v for k, v in month_map.items() if k in msg]
        if found_months:
            entities["months"] = found_months

        # Measures
        meas_map = {
            "revenue":       "revenue",
            "profit":        "profit",
            "cost":          "cost",
            "quantity":      "quantity",
            "orders":        "orders",
            "margin":        "profit_margin",
            "profit margin": "profit_margin",
        }
        found_meas = list({v for k, v in meas_map.items() if k in msg})
        if found_meas:
            entities["measures"] = found_meas

        # Dimensions (group-by)
        dim_keywords = {
            "by region":           "region",
            "by country":          "country",
            "by category":         "category",
            "by subcategory":      "subcategory",
            "by product":          "product_name",
            "by segment":          "customer_segment",
            "by customer":         "customer_segment",
            "by quarter":          "quarter",
            "by month":            "month_name",
            "by year":             "year",
        }
        found_dims = list({v for k, v in dim_keywords.items() if k in msg})
        if found_dims:
            entities["dimensions"] = found_dims

        # Top-N
        top_n_match = re.search(r"top\s+(\d+)", msg)
        if top_n_match:
            entities["top_n"] = int(top_n_match.group(1))
            entities.setdefault("dimensions", ["region"])

        # KPI type
        if "yoy" in msg or "year over year" in msg:
            entities["kpi_type"] = "yoy_growth"
        elif "mom" in msg or "month over month" in msg:
            entities["kpi_type"] = "mom_growth"
        elif "margin" in msg:
            entities["kpi_type"] = "margin"
        elif "market share" in msg:
            entities["kpi_type"] = "market_share"

        return entities

    def _llm_classify(
        self, message: str, session: SessionContext
    ) -> tuple[str, dict[str, Any]]:
        """Use Claude Haiku for intent classification + entity extraction."""
        history_ctx = session.get_context_summary(3)
        system = f"""You are an OLAP query classifier. Analyse the user's question and return JSON.

Schema context:
{SCHEMA_SUMMARY}

Recent conversation:
{history_ctx or "(none)"}

Return ONLY valid JSON with this exact structure:
{{
  "intent": "<one of: slice|dice|drill_down|roll_up|compare|pivot|drill_through|kpi|dimensions|anomaly>",
  "entities": {{
    "regions": [],
    "categories": [],
    "years": [],
    "quarters": [],
    "months": [],
    "measures": [],
    "customer_segments": [],
    "dimensions": [],
    "top_n": null,
    "kpi_type": null,
    "filters": {{}}
  }}
}}"""

        try:
            response = self._llm_client.messages.create(
                model=settings.llm_model,
                max_tokens=400,
                temperature=0.0,
                system=system,
                messages=[{"role": "user", "content": message}],
            )
            raw = response.content[0].text.strip()
            # Extract JSON from response
            json_match = re.search(r"\{.*\}", raw, re.DOTALL)
            if json_match:
                parsed = json.loads(json_match.group())
                intent = parsed.get("intent", "dice")
                entities = parsed.get("entities", {})
                return intent, entities
        except Exception as exc:
            logger.warning("LLM classification failed: %s — falling back to regex", exc)

        # Fallback
        return "dice", self._extract_entities_regex(message)

    # ------------------------------------------------------------------
    # Agent routing
    # ------------------------------------------------------------------

    def _route(
        self, intent: str, agent_input: AgentInput
    ) -> tuple[AgentOutput, list[str]]:
        agents_used: list[str] = []

        if intent in ("drill_down", "roll_up"):
            output = self._nav._safe_execute(agent_input)
            agents_used.append(self._nav.name)

        elif intent in ("slice", "dice", "pivot", "drill_through"):
            output = self._cube._safe_execute(agent_input)
            agents_used.append(self._cube.name)

        elif intent in ("compare", "kpi"):
            output = self._kpi._safe_execute(agent_input)
            agents_used.append(self._kpi.name)

        elif intent == "dimensions":
            output = self._nav._safe_execute(agent_input)
            agents_used.append(self._nav.name)

        elif intent == "anomaly":
            output = self._anomaly._safe_execute(agent_input)
            agents_used.append(self._anomaly.name)

        elif intent == "report":
            # Chain: cube + kpi → report generator
            cube_out = self._cube._safe_execute(agent_input)
            agents_used.append(self._cube.name)
            output = cube_out

        else:
            # Default: try cube operations
            output = self._cube._safe_execute(agent_input)
            agents_used.append(self._cube.name)

        agents_used.append(self._report.name)
        return output, agents_used


# ---------------------------------------------------------------------------
# Singleton
# ---------------------------------------------------------------------------

_planner: Planner | None = None


def get_planner() -> Planner:
    global _planner
    if _planner is None:
        _planner = Planner()
    return _planner


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _summarise_data(data: dict[str, Any] | None) -> str:
    if not data or not data.get("rows"):
        return "(no data)"
    row_count = data.get("row_count", 0)
    cols = data.get("columns", [])
    # Show first 3 rows abbreviated
    rows = data.get("rows", [])[:3]
    preview = "; ".join(
        ", ".join(f"{c}={v}" for c, v in zip(cols, row)) for row in rows
    )
    return f"{row_count} rows. Preview: {preview}"
