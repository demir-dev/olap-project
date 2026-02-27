"""
Pydantic request/response schemas for the OLAP API.
"""

from typing import Any, Optional
from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Request models
# ---------------------------------------------------------------------------

class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=2000, description="User's natural language question")
    session_id: Optional[str] = Field(None, description="Existing session ID. Omit to start a new session.")
    page: int = Field(default=1, ge=1, description="Page number for drill-through pagination")


# ---------------------------------------------------------------------------
# Response models
# ---------------------------------------------------------------------------

class DataPayload(BaseModel):
    columns: list[str] = Field(default_factory=list, description="Column names in result order")
    rows: list[list[Any]] = Field(default_factory=list, description="Result rows (values match columns order)")
    row_count: int = Field(default=0, description="Total rows returned")


class VisualizationHint(BaseModel):
    chart_type: str = Field(default="table", description="Suggested chart: bar, line, pie, heatmap, table")
    x_axis: Optional[str] = Field(None, description="Suggested X-axis column name")
    y_axis: Optional[str] = Field(None, description="Suggested Y-axis column name")
    color_by: Optional[str] = Field(None, description="Suggested color grouping column")


class ExecutiveSummary(BaseModel):
    text: str = Field(default="")
    highlights: list[str] = Field(default_factory=list)
    recommendations: list[str] = Field(default_factory=list)


class ReportItem(BaseModel):
    title: str = Field(default="")
    columns: list[str] = Field(default_factory=list)
    rows: list[list[Any]] = Field(default_factory=list)
    row_count: int = Field(default=0)
    operation: str = Field(default="")


class ChatResponse(BaseModel):
    session_id: str = Field(..., description="Session ID (new or existing)")
    intent: str = Field(..., description="Detected OLAP intent")
    agents_used: list[str] = Field(default_factory=list, description="Agent names that processed this query")
    sql_query: Optional[str] = Field(None, description="DuckDB SQL that was executed")
    data: Optional[DataPayload] = Field(None, description="Query result data")
    narrative: str = Field(default="", description="Plain English summary of results")
    visualization_hint: Optional[VisualizationHint] = Field(None)
    follow_up_suggestions: list[str] = Field(default_factory=list, description="Suggested follow-up questions")
    error: Optional[str] = Field(None, description="Error message if request failed")
    latency_ms: int = Field(default=0, description="Total processing time in milliseconds")
    summary: Optional[ExecutiveSummary] = Field(None, description="Structured executive summary with highlights and recommendations")
    reports: list[ReportItem] = Field(default_factory=list, description="Structured report items")
    llm_used: bool = Field(default=False, description="Whether LLM was used for classification")


# ---------------------------------------------------------------------------
# Schema endpoint models
# ---------------------------------------------------------------------------

class ColumnMeta(BaseModel):
    name: str
    dtype: str
    nullable: bool = True


class TableMeta(BaseModel):
    columns: list[ColumnMeta]
    row_count: int
    description: str


class SchemaRelationship(BaseModel):
    from_table: str
    from_column: str
    to_table: str
    to_column: str


class SchemaResponse(BaseModel):
    tables: dict[str, TableMeta]
    relationships: list[SchemaRelationship]
    dimension_values: dict[str, list[str]]
    hierarchies: dict[str, list[str]]


# ---------------------------------------------------------------------------
# Health endpoint
# ---------------------------------------------------------------------------

class HealthResponse(BaseModel):
    status: str = "ok"
    db_connected: bool = False
    db_row_count: int = 0
    active_sessions: int = 0
    version: str = "1.0.0"
