# OLAP BI Assistant — Tier 3: Architect

A **Tier 3 (Architect)** Multi-Agent Business Intelligence platform for OLAP analysis on Global Retail Sales data.

## Architecture

```
React + Vite Frontend
        │ HTTP
FastAPI Backend (/chat, /schema, /health)
        │
Planner / Orchestrator
   ├── DimensionNavigatorAgent  (drill-down, roll-up)
   ├── CubeOperationsAgent      (slice, dice, pivot, drill-through)
   ├── KPICalculatorAgent       (YoY, MoM, margins, top-N)
   ├── ReportGeneratorAgent     (LLM narratives)
   ├── VisualizationAgent       (chart type selection)      [optional]
   └── AnomalyDetectionAgent    (Z-score outlier detection) [optional]
        │
DuckDB Star Schema
   fact_sales → dim_date, dim_geography, dim_product, dim_customer
```

## Quick Start

### Option A: Docker Compose (Recommended)

```bash
# 1. Clone and setup
git clone https://github.com/demir-dev/olap-project.git
cd olap-project
cp .env.example .env
# Edit .env → add your ANTHROPIC_API_KEY

# 2. Build and run
make build
make up

# 3. Open browser
# Frontend:  http://localhost:3000
# API Docs:  http://localhost:8000/docs
```

### Option B: Local Development (Windows)

```powershell
# Terminal 1 — Backend
cd backend
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env
# Edit .env → set ANTHROPIC_API_KEY=sk-ant-...
python data/generate_dataset.py
uvicorn app.main:app --reload --port 8000
```

```powershell
# Terminal 2 — Frontend
cd frontend
npm install
npm run dev
# Open http://localhost:5173
```

### Option C: Local Development (macOS / Linux)

```bash
# Terminal 1 — Backend
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# Edit .env → set ANTHROPIC_API_KEY=sk-ant-...
python data/generate_dataset.py
uvicorn app.main:app --reload --port 8000
```

```bash
# Terminal 2 — Frontend
cd frontend
npm install
npm run dev
# Open http://localhost:5173
```

## Environment Variables

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `ANTHROPIC_API_KEY` | Yes | — | Anthropic API key (get at console.anthropic.com) |
| `DATABASE_PATH` | No | `data/olap.duckdb` | DuckDB file path |
| `LLM_MODEL` | No | `claude-3-haiku-20240307` | Anthropic model ID |
| `CORS_ORIGINS` | No | localhost origins | Allowed CORS origins (JSON array) |
| `SESSION_TTL_MINUTES` | No | `30` | Session expiry |
| `LOG_LEVEL` | No | `INFO` | Logging level |

> **Without an API key:** The system still works for all OLAP operations. Intent classification uses keyword rules and narratives use templates. Set `ANTHROPIC_API_KEY` to enable LLM-powered natural language understanding and narrative generation.

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/chat` | OLAP chat — send question, get results |
| `GET` | `/schema` | Star schema metadata + dimension values |
| `GET` | `/health` | Backend health check |
| `GET` | `/docs` | Interactive Swagger UI |

### Example Chat Request

```bash
curl -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "What is total revenue by region for 2024?", "session_id": null}'
```

## OLAP Operations Supported

| Operation | Example Question |
|-----------|-----------------|
| Slice | "Show only 2024 data" |
| Dice | "Electronics sales in Europe for Q4 2024" |
| Drill-Down | "Break down 2024 revenue by quarter, then by month" |
| Roll-Up | "Summarize monthly data at the quarterly level" |
| Compare | "Compare 2023 vs 2024 revenue by region" |
| Pivot | "Pivot region by quarter showing revenue" |
| Drill-Through | "Show me the raw transactions for Electronics in Q4" |
| KPI | "Top 5 countries by profit margin" |
| Anomaly | "Are there any unusual spikes in monthly revenue?" |

## Dataset

**Global Retail Sales** — 10,000 synthetic transactions

- **Time:** January 2022 – December 2024
- **Regions:** North America, Europe, Asia Pacific, Latin America
- **Categories:** Electronics, Furniture, Office Supplies, Clothing
- **Segments:** Consumer, Corporate, Home Office, Small Business
- **Measures:** revenue, cost, profit, profit_margin, quantity

Dataset is auto-generated on first startup. Regenerate manually:
```bash
cd backend && python data/generate_dataset.py
```

## Test Questions

| # | Question | Expected Intent | Expected Result |
|---|----------|----------------|-----------------|
| 1 | "What is total revenue by region?" | `dice` | 4-row table with region totals |
| 2 | "Break down 2024 sales by quarter" | `drill_down` | 4-row quarterly breakdown |
| 3 | "Compare 2023 vs 2024 revenue" | `compare` | YoY growth percentages |
| 4 | "Show top 5 countries by profit margin" | `kpi` | 5-row ranked table |
| 5 | "Show me Electronics sales in Europe by month" | `dice` | 12-row monthly breakdown |

## Project Structure

```
olap-project/
├── backend/
│   ├── app/
│   │   ├── main.py              # FastAPI entry point
│   │   ├── config.py            # Settings (env vars)
│   │   ├── dependencies.py      # DuckDB singleton
│   │   ├── api/
│   │   │   ├── routes.py        # /chat, /schema, /health
│   │   │   └── schemas.py       # Pydantic models
│   │   ├── orchestrator/
│   │   │   ├── planner.py       # Intent + routing
│   │   │   └── session.py       # Session context
│   │   └── agents/
│   │       ├── base_agent.py
│   │       ├── dimension_navigator.py
│   │       ├── cube_operations.py
│   │       ├── kpi_calculator.py
│   │       ├── report_generator.py
│   │       ├── visualization_agent.py
│   │       └── anomaly_detection.py
│   ├── data/
│   │   ├── schema.sql           # DuckDB DDL
│   │   └── generate_dataset.py  # Dataset generator
│   └── requirements.txt
├── frontend/
│   ├── src/
│   │   ├── App.tsx
│   │   ├── components/          # Chat, Results, Table, etc.
│   │   ├── hooks/useChat.ts
│   │   ├── api/client.ts
│   │   └── types.ts
│   └── package.json
├── docs/
│   ├── architecture.md          # System design
│   └── agent_specs.md           # Agent I/O specs
├── docker-compose.yml
├── Makefile
└── README.md
```

## Grading Compliance (Tier 3)

| Criterion | Implemented |
|-----------|------------|
| DimensionNavigator Agent | ✅ drill-down, roll-up, hierarchy navigation |
| CubeOperations Agent | ✅ slice, dice, pivot, drill-through (paginated) |
| KPICalculator Agent | ✅ YoY, MoM, margins, top-N, market share |
| ReportGenerator Agent | ✅ LLM narratives + template fallback |
| VisualizationAgent (optional) | ✅ Rule-based chart type selection |
| AnomalyDetectionAgent (optional) | ✅ Z-score window function detection |
| Planner / Orchestrator | ✅ Keyword rules + LLM fallback + session context |
| FastAPI + OpenAPI | ✅ /chat, /schema, /health, /docs |
| DuckDB Star Schema | ✅ fact_sales + 4 dimension tables |
| React Frontend | ✅ Chat + history + results + sample questions |
| Docker Compose | ✅ docker-compose.yml + Makefile |
| Session Context | ✅ In-memory with sticky filters + TTL |
| All 7 OLAP Operations | ✅ slice/dice/drill/rollup/pivot/compare/drill-through |
