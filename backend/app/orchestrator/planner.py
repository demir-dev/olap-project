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
        "down to", "drill ",   # "Drill Q4 2024 down to months", "Drill into X"
    ],
    "roll_up": [
        "roll up", "summarize", "summarise", "aggregate", "overall",
        "high level", "at year level", "at quarter level",
    ],
    "compare": [
        " vs ", " versus ", "compared to", "year over year", "yoy",
        "month over month", "mom", "growth", "change from", "difference",
        "better than", "worse than",
        "monthly trend", "monthly revenue", "month by month",  # monthly analysis
        "each month", "trend for 20",                          # "trend for 2024"
    ],
    "kpi": [
        "top ", "bottom ", "best ", "worst", "highest ", "lowest ",  # "worst" no space req
        "margin", "profit margin", "growth rate", "market share",
        "ranking", "ranked", "leading", "lagging",
        "percentage", "share of", "% of",                            # market share triggers
        "most valuable", "most profitable", "least profitable",
        "best performing", "worst performing", "worst-performing",
        "worst-", "most important", "least ", "smallest ",
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
# LLM Tool definitions (Anthropic tool-use format)
# ---------------------------------------------------------------------------

TOOL_DEFINITIONS = [
    {
        "name": "drill_down",
        "description": "Break down data to a more granular level (e.g., year → quarter → month, region → country)",
        "input_schema": {
            "type": "object",
            "properties": {
                "dimension": {"type": "string", "description": "Dimension to drill into"},
                "filters": {"type": "object", "description": "Optional filters"},
            },
            "required": [],
        },
    },
    {
        "name": "roll_up",
        "description": "Aggregate data to a higher level (e.g., month → quarter → year)",
        "input_schema": {
            "type": "object",
            "properties": {
                "dimension": {"type": "string", "description": "Dimension to roll up to"},
                "measure": {"type": "string", "description": "Measure to aggregate"},
            },
            "required": [],
        },
    },
    {
        "name": "slice",
        "description": "Filter the data cube on one dimension value",
        "input_schema": {
            "type": "object",
            "properties": {
                "dimension": {"type": "string", "description": "Dimension to slice on"},
                "value": {"type": "string", "description": "Value to filter to"},
                "measure": {"type": "string", "description": "Measure to show"},
            },
            "required": ["dimension"],
        },
    },
    {
        "name": "dice",
        "description": "Filter the data cube on multiple dimensions simultaneously",
        "input_schema": {
            "type": "object",
            "properties": {
                "filters": {"type": "object", "description": "Dict of dimension→value filters"},
                "measures": {"type": "array", "items": {"type": "string"}, "description": "Measures to show"},
            },
            "required": [],
        },
    },
    {
        "name": "pivot",
        "description": "Rotate the data cube to show dimensions as rows and columns",
        "input_schema": {
            "type": "object",
            "properties": {
                "rows": {"type": "string", "description": "Dimension to use as rows"},
                "columns": {"type": "string", "description": "Dimension to use as columns"},
                "measure": {"type": "string", "description": "Measure to aggregate in cells"},
            },
            "required": [],
        },
    },
    {
        "name": "yoy_growth",
        "description": "Calculate year-over-year growth rates for a measure",
        "input_schema": {
            "type": "object",
            "properties": {
                "measure": {"type": "string", "description": "Measure to compute growth for"},
                "dimension": {"type": "string", "description": "Optional dimension to group by"},
            },
            "required": [],
        },
    },
    {
        "name": "mom_change",
        "description": "Calculate month-over-month change for a measure",
        "input_schema": {
            "type": "object",
            "properties": {
                "measure": {"type": "string", "description": "Measure to compute change for"},
                "year": {"type": "integer", "description": "Year to analyse"},
            },
            "required": [],
        },
    },
    {
        "name": "profit_margins",
        "description": "Analyse profit margins by dimension (category, region, segment)",
        "input_schema": {
            "type": "object",
            "properties": {
                "dimension": {"type": "string", "description": "Dimension to group margins by"},
                "year": {"type": "integer", "description": "Optional year filter"},
            },
            "required": [],
        },
    },
    {
        "name": "top_n",
        "description": "Rank the top N members of a dimension by a measure",
        "input_schema": {
            "type": "object",
            "properties": {
                "n": {"type": "integer", "description": "Number of top items to return"},
                "dimension": {"type": "string", "description": "Dimension to rank"},
                "measure": {"type": "string", "description": "Measure to rank by"},
                "year": {"type": "integer", "description": "Optional year filter"},
            },
            "required": [],
        },
    },
    {
        "name": "compare_periods",
        "description": "Compare two specific years side by side with deltas",
        "input_schema": {
            "type": "object",
            "properties": {
                "year_a": {"type": "integer", "description": "First year to compare"},
                "year_b": {"type": "integer", "description": "Second year to compare"},
                "dimension": {"type": "string", "description": "Dimension to break down by"},
                "measure": {"type": "string", "description": "Measure to compare"},
            },
            "required": ["year_a", "year_b"],
        },
    },
    {
        "name": "revenue_share",
        "description": "Show market share / revenue distribution as percentages across a dimension",
        "input_schema": {
            "type": "object",
            "properties": {
                "dimension": {"type": "string", "description": "Dimension to compute share for"},
                "year": {"type": "integer", "description": "Optional year filter"},
            },
            "required": [],
        },
    },
]

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

        # 2. Build agent input - ensure message is in session context for agents
        agent_input = AgentInput(
            message=message,
            intent=intent,
            entities=entities,
            session_context={
                **session.resolved_context,
                "active_filters": session.resolved_context.get("active_filters", {}),
                "history_summary": session.get_context_summary(3),
                "message": message,  # Include message for entity extraction in agents
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

        # 5. Generate structured summary via ReportGenerator (replaces plain narrative)
        summary_dict = self._report.generate_structured_summary(
            user_question=message,
            intent=intent,
            data=output.data,
            context=session.resolved_context,
        )
        narrative = summary_dict.get("text", "")
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
        # Track dimension level for drill-down/roll-up context
        if intent in ("drill_down", "roll_up") and output.data and output.data.get("columns"):
            # Try to identify the dimension level from the result columns
            for col in output.data.get("columns", []):
                if col in ["year", "quarter", "month", "month_name", "quarter_name", 
                          "region", "country", "category", "subcategory", "product_name"]:
                    entities["dimensions"] = [col]
                    break
        
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

        # Build reports list from agent output
        reports = []
        if output.data and output.data.get("columns"):
            reports.append({
                "title": f"{intent.replace('_', ' ').title()} Results",
                "columns": output.data.get("columns", []),
                "rows": output.data.get("rows", []),
                "row_count": output.data.get("row_count", 0),
                "operation": intent,
            })

        llm_used = bool(self._llm_client)

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
            "summary":              summary_dict,
            "reports":              reports,
            "llm_used":             llm_used,
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
                # "compare" with 2 specific years → side-by-side period comparison
                if best_intent == "compare" and len(entities.get("years", [])) >= 2:
                    entities["kpi_type"] = "compare_periods"
                # monthly keywords → route as "compare" so KPICalculator handles mom_change
                if entities.get("kpi_type") == "mom_growth":
                    best_intent = "kpi"
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
            "revenue":             "revenue",
            "profit":              "profit",
            "cost":                "cost",
            "quantity":            "quantity",
            "orders":              "orders",
            "transactions":        "orders",    # natural language alias
            "transaction":         "orders",
            "sales count":         "orders",
            "margin":              "profit_margin",
            "profit margin":       "profit_margin",
            "average order value": "avg_order",  # ex. 3: avg order value
            "average order":       "avg_order",
            "avg order":           "avg_order",
            "sales":               "revenue",    # "total sales" → revenue
        }
        found_meas = list({v for k, v in meas_map.items() if k in msg})
        if found_meas:
            entities["measures"] = found_meas

        # Dimensions (group-by) — "by X", "per X", "each X", "for each X"
        dim_keywords = {
            "by region":           "region",
            "per region":          "region",
            "each region":         "region",
            "for each region":     "region",
            "by country":          "country",
            "per country":         "country",
            "each country":        "country",
            "by category":         "category",
            "per category":        "category",
            "each category":       "category",
            "for each category":   "category",
            "by subcategory":      "subcategory",
            "per subcategory":     "subcategory",
            "each subcategory":    "subcategory",
            "by product":          "product_name",
            "per product":         "product_name",
            "by segment":          "customer_segment",
            "per segment":         "customer_segment",
            "each segment":        "customer_segment",
            "by customer":         "customer_segment",
            "by quarter":          "quarter",
            "per quarter":         "quarter",
            "by month":            "month_name",
            "per month":           "month_name",
            "by year":             "year",
            "per year":            "year",
            "annually":            "year",
        }
        found_dims = list({v for k, v in dim_keywords.items() if k in msg})
        if found_dims:
            entities["dimensions"] = found_dims

        # Monthly / quarterly time dimension detection (overrides dim_keywords for time)
        if any(kw in msg for kw in [
            "monthly", "by month", "per month", "each month",
            "month by month", "month-by-month", "monthly trend", "monthly revenue",
        ]):
            entities["dimensions"] = ["month_name"]
            entities["kpi_type"] = "mom_growth"

        if any(kw in msg for kw in [
            "quarterly", "by quarter", "per quarter", "each quarter", "quarterly trend",
        ]):
            entities.setdefault("dimensions", ["quarter"])

        # Detect dimension from bare noun/plural (e.g. "top 5 countries", "worst-performing subcategory")
        # Only applied when dim_keywords above didn't already find a dimension
        if not entities.get("dimensions"):
            bare_dim_map = [
                ("countries",          "country"),
                ("subcategories",      "subcategory"),
                ("subcategory",        "subcategory"),
                ("categories",         "category"),
                ("products",           "product_name"),
                ("segments",           "customer_segment"),
                ("customer segments",  "customer_segment"),
            ]
            for kw, dim_val in bare_dim_map:
                if re.search(r"\b" + kw + r"\b", msg):
                    entities["dimensions"] = [dim_val]
                    break

        # Top-N
        top_n_match = re.search(r"top\s+(\d+)", msg)
        if top_n_match:
            entities["top_n"] = int(top_n_match.group(1))
            entities.setdefault("dimensions", ["region"])

        # Bottom-N (worst / least / bottom performers)
        bottom_n_match = re.search(r"bottom\s+(\d+)", msg)
        if bottom_n_match:
            entities["top_n"] = int(bottom_n_match.group(1))
            entities["ascending"] = True
            entities.setdefault("dimensions", ["subcategory"])

        # "worst" with no number → bottom 5 default
        if any(kw in msg for kw in ["worst", "worst-performing", "least profitable",
                                     "worst performing", "lowest margin"]):
            if "top_n" not in entities:
                entities["top_n"] = 5
            entities["ascending"] = True

        # KPI type (only set if not already set by monthly detection above)
        if "kpi_type" not in entities:
            if "yoy" in msg or "year over year" in msg:
                entities["kpi_type"] = "yoy_growth"
            elif "mom" in msg or "month over month" in msg:
                entities["kpi_type"] = "mom_growth"
            elif "margin" in msg:
                entities["kpi_type"] = "margin"
            elif any(kw in msg for kw in [
                "market share", "percentage of revenue", "share of revenue",
                "% of revenue", "percentage of", "what percentage", "what percent",
                "revenue share", "share by",
            ]):
                entities["kpi_type"] = "market_share"
            elif any(kw in msg for kw in [
                "most valuable", "most profitable", "most important",
                "most significant", "which segment", "which customer segment",
            ]):
                entities["kpi_type"] = "top_n"
                entities.setdefault("dimensions", ["customer_segment"])

        return entities

    def _llm_classify(
        self, message: str, session: SessionContext
    ) -> tuple[str, dict[str, Any]]:
        """Use Claude Haiku with tool-calling for intent classification + entity extraction."""
        if not self._llm_client:
            logger.debug("LLM client not available, using regex fallback")
            return "dice", self._extract_entities_regex(message)

        history_ctx = session.get_context_summary(3)
        system = f"""You are an OLAP query classifier. Use the appropriate tool to classify the user's business intelligence question.

Schema:
{SCHEMA_SUMMARY}

Recent conversation:
{history_ctx or "(none)"}

Choose the tool that best matches the user's intent and extract relevant parameters."""

        try:
            response = self._llm_client.messages.create(
                model=settings.llm_model,
                max_tokens=512,
                temperature=0.0,
                system=system,
                tools=TOOL_DEFINITIONS,
                tool_choice={"type": "auto"},
                messages=[{"role": "user", "content": message}],
            )
            # Extract the first tool_use block
            for block in response.content:
                if block.type == "tool_use":
                    intent, entities = self._map_tool_to_intent(block.name, block.input)
                    logger.debug("LLM tool-use classified intent: %s entities: %s", intent, entities)
                    return intent, entities
        except Exception as exc:
            logger.warning("LLM tool-calling failed: %s — falling back to regex", exc)

        # Fallback
        return "dice", self._extract_entities_regex(message)

    def _map_tool_to_intent(
        self, tool_name: str, tool_input: dict[str, Any]
    ) -> tuple[str, dict[str, Any]]:
        """Map LLM tool name + input to (intent, entities) that agents expect."""
        entities = self._extract_entities_regex("")  # start with empty entities

        # Merge common fields from tool_input
        if tool_input.get("dimension"):
            entities["dimensions"] = [tool_input["dimension"]]
        if tool_input.get("measure"):
            entities["measures"] = [tool_input["measure"]]
        if tool_input.get("filters"):
            entities["filters"] = tool_input["filters"]
        if tool_input.get("year"):
            entities["years"] = [int(tool_input["year"])]
        if tool_input.get("year_a") and tool_input.get("year_b"):
            entities["years"] = [int(tool_input["year_a"]), int(tool_input["year_b"])]
        if tool_input.get("n"):
            entities["top_n"] = int(tool_input["n"])
        if tool_input.get("rows"):
            entities.setdefault("dimensions", [tool_input["rows"]])
        if tool_input.get("value"):
            d = tool_input.get("dimension", "region")
            val = tool_input["value"]
            # Cast time dimension values to int to match DuckDB SMALLINT/TINYINT schema
            # (LLM sometimes returns year/month as strings which cause 0-row results)
            if d in ("year", "month", "quarter_num"):
                try:
                    val = int(val)
                except (ValueError, TypeError):
                    pass
            entities.setdefault("filters", {})[d] = val

        # Map tool name → (intent, kpi_type)
        mapping: dict[str, tuple[str, str | None]] = {
            "drill_down":     ("drill_down", None),
            "roll_up":        ("roll_up", None),
            "slice":          ("slice", None),
            "dice":           ("dice", None),
            "pivot":          ("pivot", None),
            "yoy_growth":     ("kpi", "yoy_growth"),
            "mom_change":     ("kpi", "mom_growth"),
            "profit_margins": ("kpi", "margin"),
            "top_n":          ("kpi", "top_n"),
            "compare_periods":("kpi", "compare_periods"),
            "revenue_share":  ("kpi", "market_share"),
        }
        intent, kpi_type = mapping.get(tool_name, ("dice", None))
        if kpi_type:
            entities["kpi_type"] = kpi_type

        return intent, entities

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
