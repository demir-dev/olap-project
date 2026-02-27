// TypeScript interfaces for the OLAP BI Assistant

export interface DataPayload {
  columns: string[]
  rows: (string | number | null)[][]
  row_count: number
}

export interface VisualizationHint {
  chart_type: 'bar' | 'line' | 'pie' | 'heatmap' | 'table' | 'kpi_card'
  x_axis: string | null
  y_axis: string | null
  color_by: string | null
}

export interface ExecutiveSummary {
  text: string
  highlights: string[]
  recommendations: string[]
}

export interface ReportItem {
  title: string
  columns: string[]
  rows: (string | number | null)[][]
  row_count: number
  operation: string
}

export interface DashboardKPIs {
  total_revenue: number
  total_profit: number
  avg_margin_pct: number
  total_orders: number
  total_units: number
  countries: number
}

export interface ChatResponse {
  session_id: string
  intent: string
  agents_used: string[]
  sql_query: string | null
  data: DataPayload | null
  narrative: string
  visualization_hint: VisualizationHint | null
  follow_up_suggestions: string[]
  error: string | null
  latency_ms: number
  summary?: ExecutiveSummary
  reports?: ReportItem[]
  llm_used?: boolean
}

export interface ChatRequest {
  message: string
  session_id: string | null
  page?: number
}

export type MessageRole = 'user' | 'assistant'

export interface Message {
  id: string
  role: MessageRole
  content: string
  timestamp: Date
  response?: ChatResponse
  isLoading?: boolean
}

export interface ColumnMeta {
  name: string
  dtype: string
  nullable: boolean
}

export interface TableMeta {
  columns: ColumnMeta[]
  row_count: number
  description: string
}

export interface SchemaRelationship {
  from_table: string
  from_column: string
  to_table: string
  to_column: string
}

export interface SchemaResponse {
  tables: Record<string, TableMeta>
  relationships: SchemaRelationship[]
  dimension_values: Record<string, string[]>
  hierarchies: Record<string, string[]>
}

export interface HealthResponse {
  status: string
  db_connected: boolean
  db_row_count: number
  active_sessions: number
  version: string
}
