# Agent Specifications

## 1. DimensionNavigatorAgent

**File:** `backend/app/agents/dimension_navigator.py`

**Purpose:** Navigate dimension hierarchies. Answer "what exists" questions and move up/down hierarchy levels.

### Supported Operations
| Operation | Description | Example |
|-----------|-------------|---------|
| `drill_down` | Move to finer granularity | Year → Quarter → Month |
| `roll_up` | Move to coarser granularity | Month → Quarter → Year |
| `dimensions` | List available members | "What regions do we have?" |

### Hierarchies Supported
- **Time:** Year → Quarter → Month
- **Geography:** Region → Country
- **Product:** Category → Subcategory → Product Name

### Input
```python
AgentInput(
    intent="drill_down",
    entities={
        "from_level": "year",       # or inferred from context
        "to_level": "quarter",      # or auto-resolved
        "years": [2024],            # filter
        "regions": ["North America"] # filter
    }
)
```

### Output
```python
AgentOutput(
    sql_query="SELECT d.quarter_name, SUM(f.revenue) ... GROUP BY ...",
    data={"columns": ["quarter", "revenue", "profit", ...], "rows": [...], "row_count": 4},
    visualization_hint={"chart_type": "bar", "x_axis": "quarter", "y_axis": "revenue"},
    follow_up_suggestions=["Drill into Q4 by month", "Compare Q4 year over year"]
)
```

---

## 2. CubeOperationsAgent

**File:** `backend/app/agents/cube_operations.py`

**Purpose:** Execute OLAP cube operations on the fact table. The workhorse agent for most queries.

### Supported Operations
| Operation | Description | SQL Pattern |
|-----------|-------------|-------------|
| `slice` | Filter on one dimension | `WHERE region = 'Europe'` |
| `dice` | Filter on multiple dimensions | `WHERE year = 2024 AND category = 'Electronics'` |
| `pivot` | Reshape (DuckDB PIVOT) | `PIVOT ... ON quarter_name USING SUM(revenue)` |
| `drill_through` | Raw rows with pagination | `SELECT * ... LIMIT 20 OFFSET n` |

### Input
```python
AgentInput(
    intent="dice",
    entities={
        "regions": ["Europe"],
        "categories": ["Electronics"],
        "years": [2024],
        "dimensions": ["region", "quarter"],
        "measures": ["revenue", "profit"]
    }
)
```

### Output
```python
AgentOutput(
    sql_query="SELECT g.region, d.quarter_name, SUM(f.revenue) ...",
    data={"columns": ["region", "quarter", "revenue", "profit"], "rows": [...], "row_count": 4},
    visualization_hint={"chart_type": "bar", "x_axis": "quarter", "y_axis": "revenue"},
    follow_up_suggestions=["Compare to previous year", "Drill into top quarter"]
)
```

### Drill-Through Pagination
Drill-through supports `page` parameter (default page_size=20):
- Page 1: `OFFSET 0 LIMIT 20`
- Page 2: `OFFSET 20 LIMIT 20`

---

## 3. KPICalculatorAgent

**File:** `backend/app/agents/kpi_calculator.py`

**Purpose:** Calculate business KPIs using window functions and CTEs.

### Supported KPI Types
| Type | Description | SQL Technique |
|------|-------------|---------------|
| `yoy_growth` | Year-over-Year % change | Self-join on `year / year-1` |
| `mom_growth` | Month-over-Month % change | `LAG()` window function |
| `margin` | Profit margin by dimension | `profit / revenue * 100` |
| `top_n` | Top-N ranking | `RANK() OVER (ORDER BY metric DESC)` |
| `market_share` | % of total by dimension | `SUM(rev) / total_rev * 100` |

### Input
```python
AgentInput(
    intent="compare",
    entities={
        "kpi_type": "yoy_growth",
        "measures": ["revenue"],
        "dimensions": ["region"],
        "years": [2023, 2024]
    }
)
```

### Output
```python
AgentOutput(
    sql_query="WITH yearly AS (...) SELECT curr.year, curr.metric, ...",
    data={"columns": ["region", "year", "current_value", "prior_value", "yoy_growth_pct"], ...},
    visualization_hint={"chart_type": "bar", "x_axis": "year", "y_axis": "yoy_growth_pct"}
)
```

---

## 4. ReportGeneratorAgent

**File:** `backend/app/agents/report_generator.py`

**Purpose:** Convert raw query results into human-readable business narratives. LLM-powered when API key available; template-based fallback otherwise.

### Two Modes

**LLM Mode** (when `ANTHROPIC_API_KEY` is set):
- Uses `claude-3-haiku-20240307`
- System prompt: BI analyst persona, 2–4 sentence constraint
- Input: user question + intent + sample data rows
- Output: Natural language insight (highlights top performer, trend, anomaly)

**Template Mode** (no API key):
- Rule-based narrative templates per intent
- Extracts top value, growth percentage from data
- Generates "The top performer is X with $Y" style summaries

### Usage
```python
narrative = report_generator.generate_narrative(
    user_question="What's revenue by region?",
    intent="slice",
    data={"columns": [...], "rows": [...], "row_count": 4},
    context={}
)
# → "North America leads with $2.1M in revenue (34% of total). Europe follows..."

follow_ups = report_generator.generate_follow_ups(
    user_question=..., intent=..., entities=..., existing_follow_ups=[...]
)
# → ["Drill into North America by country", "Compare YoY", "Show margins"]
```

---

## 5. VisualizationAgent [Optional]

**File:** `backend/app/agents/visualization_agent.py`

**Purpose:** Select the most appropriate chart type based on data shape and query intent.

### Decision Logic
| Condition | Chart Type |
|-----------|-----------|
| Drill-through / >8 columns | `table` |
| Time dimension + 1 measure | `line` |
| Time + category dimension | `line` (multi-series) |
| Category + 1 measure | `bar` |
| 2 category dimensions | `heatmap` |
| Proportion/share column | `pie` |
| No dimensions | `kpi_card` |

### Output
```python
{
    "chart_type": "bar",
    "x_axis": "region",
    "y_axis": "revenue",
    "color_by": None
}
```

---

## 6. AnomalyDetectionAgent [Optional]

**File:** `backend/app/agents/anomaly_detection.py`

**Purpose:** Detect statistically unusual values in time series data using Z-score analysis.

### Method
1. Aggregate metric by year + month
2. Compute global mean and standard deviation (population)
3. Calculate Z-score for each month: `z = (value - mean) / stddev`
4. Flag months where `|z| > threshold` as `ANOMALY`

### Sensitivity Levels
| Level | Z-Score Threshold | Catches |
|-------|-------------------|---------|
| `low` | 3.0σ | Only extreme outliers |
| `medium` | 2.0σ | Standard anomalies (default) |
| `high` | 1.5σ | More sensitive |

### Input
```python
AgentInput(
    intent="anomaly",
    entities={"measures": ["revenue"], "sensitivity": "medium"}
)
```

### Output
```python
AgentOutput(
    data={"columns": ["year","month","month_name","revenue","global_mean","global_stddev","z_score","status"], ...},
    narrative="Detected 3 anomalous months. November 2023 showed a spike (z=2.8σ)...",
    visualization_hint={"chart_type": "line", "x_axis": "month_name", "y_axis": "revenue", "color_by": "status"}
)
```

---

## Orchestrator Routing Matrix

| User Question Pattern | Intent | Primary Agent |
|---|---|---|
| "List all regions / what categories" | `dimensions` | DimensionNavigator |
| "Revenue in North America" | `slice` | CubeOperations |
| "Electronics sales in Europe, 2024" | `dice` | CubeOperations |
| "Break down by month / drill into Q4" | `drill_down` | DimensionNavigator |
| "Roll up to yearly / summarize" | `roll_up` | DimensionNavigator |
| "Compare 2023 vs 2024 / YoY growth" | `compare` | KPICalculator |
| "Top 5 products / best margin" | `kpi` | KPICalculator |
| "Pivot region by quarter" | `pivot` | CubeOperations |
| "Show raw transactions / underlying" | `drill_through` | CubeOperations |
| "Any anomalies / unusual spikes" | `anomaly` | AnomalyDetection |
| Any result → narrative synthesis | — | ReportGenerator (always) |
