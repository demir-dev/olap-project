import type { ChatRequest, ChatResponse, DashboardKPIs, HealthResponse, SchemaResponse } from '../types'

// Base URL — in dev mode, Vite proxy forwards /chat, /api → http://localhost:8000
// In production Docker, set VITE_API_BASE_URL at build time
const BASE_URL = (import.meta.env.VITE_API_BASE_URL as string) || ''

async function apiFetch<T>(path: string, options?: RequestInit): Promise<T> {
  const url = `${BASE_URL}${path}`
  const response = await fetch(url, {
    headers: {
      'Content-Type': 'application/json',
      ...options?.headers,
    },
    ...options,
  })

  if (!response.ok) {
    let errorDetail = `HTTP ${response.status}`
    try {
      const err = await response.json()
      errorDetail = err.detail || err.error || errorDetail
    } catch {
      // ignore parse error
    }
    throw new Error(errorDetail)
  }

  return response.json() as Promise<T>
}

export const api = {
  chat: (request: ChatRequest): Promise<ChatResponse> =>
    apiFetch<ChatResponse>('/chat', {
      method: 'POST',
      body: JSON.stringify(request),
    }),

  schema: (): Promise<SchemaResponse> =>
    apiFetch<SchemaResponse>('/schema'),

  health: (): Promise<HealthResponse> =>
    apiFetch<HealthResponse>('/health'),

  dashboardKpis: (): Promise<DashboardKPIs> =>
    apiFetch<DashboardKPIs>('/api/query/dashboard'),

  suggestions: (): Promise<{ suggestions: string[] }> =>
    apiFetch<{ suggestions: string[] }>('/api/query/suggestions'),

  olapOperation: (operation: string, body: Record<string, unknown> = {}): Promise<unknown> =>
    apiFetch<unknown>(`/api/olap/${operation}`, {
      method: 'POST',
      body: JSON.stringify(body),
    }),
}
