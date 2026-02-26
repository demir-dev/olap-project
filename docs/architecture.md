# Architecture: Multi-Agent OLAP BI Platform

## System Overview

```
┌─────────────────────────────────────────────────────────┐
│              FRONTEND (React + Vite + Tailwind)          │
│  Chat Input │ Conversation History │ Results Panel       │
│             Sample Question Buttons                      │
└──────────────────────┬──────────────────────────────────┘
                       │ HTTP (POST /chat, GET /schema)
┌──────────────────────▼──────────────────────────────────┐
│                 API LAYER (FastAPI)                      │
│         /chat    /schema    /health    /docs             │
└──────────────────────┬──────────────────────────────────┘
                       │
┌──────────────────────▼──────────────────────────────────┐
│           PLANNER / ORCHESTRATOR                         │
│  1. Intent Classification (keyword rules → LLM fallback) │
│  2. Entity Extraction (regions, years, measures, etc.)   │
│  3. Session Context Management (sticky filters)          │
│  4. Agent Routing + Chaining                             │
│  5. Narrative Generation (ReportGenerator)               │
└─────┬──────────┬──────────┬──────────┬──────────────────┘
      │          │          │          │
┌─────▼───┐ ┌───▼───┐ ┌────▼───┐ ┌───▼─────────┐
│Dimension│ │ Cube  │ │  KPI   │ │   Report    │
│Navigator│ │  Ops  │ │Calcul. │ │  Generator  │
│         │ │       │ │        │ │             │
│Drill ↕  │ │Slice  │ │YoY/MoM │ │Narrative    │
│Roll-up  │ │Dice   │ │Margins │ │Tables       │
│Hierarchy│ │Pivot  │ │Top-N   │ │Follow-ups   │
│Nav      │ │Drill- │ │Market  │ │(LLM-powered)│
│         │ │through│ │Share   │ │             │
└─────────┘ └───────┘ └────────┘ └─────────────┘
      │          │          │          │
┌─────▼──────────▼──────────▼──────────▼──────────────────┐
│              DATA ACCESS LAYER                           │
│          DuckDB (thread-safe singleton)                  │
│          execute_query(sql, params) with Lock            │
└──────────────────────┬──────────────────────────────────┘
                       │
┌──────────────────────▼──────────────────────────────────┐
│                STAR SCHEMA (DuckDB)                      │
│                                                          │
│          dim_date ──── fact_sales ──── dim_product       │
│                            │                             │
│          dim_geography ────┘──────── dim_customer        │
└─────────────────────────────────────────────────────────┘
```

## Optional Agents (A+ grade)

```
┌─────────────────────┐  ┌─────────────────────┐
│  Visualization      │  │  Anomaly Detection  │
│  Agent              │  │  Agent              │
│                     │  │                     │
│  Rule-based chart   │  │  Z-score window     │
│  type selection:    │  │  function on        │
│  bar/line/pie/      │  │  monthly revenue.   │
│  heatmap/table      │  │  Flags |z| > 2σ     │
└─────────────────────┘  └─────────────────────┘
```

## Request Flow

```
User: "Compare 2023 vs 2024 revenue by region"

1. POST /chat { message, session_id }
2. Planner.process()
   a. _classify() → keyword match: "vs" → intent="compare"
   b. _extract_entities_regex() → { years: [2023, 2024], dimensions: ["region"] }
   c. _route("compare") → KPICalculatorAgent
3. KPICalculatorAgent._yoy_growth()
   → Builds CTE SQL with self-join on year/year-1, grouped by region
   → execute_query(sql) → columns, rows
4. VisualizationAgent.suggest() → { chart_type: "bar", x_axis: "year", y_axis: "yoy_growth_pct" }
5. ReportGeneratorAgent.generate_narrative()
   → LLM (claude-3-haiku): "Revenue grew 18.4% in North America YoY..."
6. session.update_context({ years: [2023, 2024] })  ← sticky filters
7. Return ChatResponse { data, narrative, viz_hint, follow_ups }
```

## Key Design Decisions

### DuckDB over PostgreSQL
- Zero infrastructure overhead (embedded file)
- Native PIVOT support
- Window functions (LAG, RANK, STDDEV)
- Fast OLAP aggregations on 10K rows (<10ms)
- Requires single-process access (uvicorn --workers 1)

### Rule-based + LLM intent classification
- Keyword rules cover ~80% of queries with 0ms latency
- LLM fallback only for ambiguous queries (~300ms for Haiku)
- Graceful degradation when API key absent

### In-memory sessions
- No Redis/database needed for sessions
- Sticky context (last region/year/category filter persists)
- TTL eviction every 5 minutes

### Agent design (pure Python, no framework)
- No DSPy/LangChain dependencies = fewer version conflicts
- Each agent: SQL builder + formatter + viz hint
- ReportGenerator is the only agent using LLM
- Easy to add new agents by implementing BaseAgent

## Tech Stack

| Layer       | Technology        | Version |
|-------------|-------------------|---------|
| Frontend    | React + Vite      | 18 / 6  |
| Styling     | Tailwind CSS      | 3.4     |
| Backend     | FastAPI           | 0.115   |
| Server      | Uvicorn           | 0.32    |
| Database    | DuckDB            | 1.1     |
| LLM         | Anthropic SDK     | 0.40    |
| Validation  | Pydantic          | 2.10    |
| Container   | Docker / Compose  | latest  |
