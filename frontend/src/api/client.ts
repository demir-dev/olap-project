import type { ChatRequest, ChatResponse, HealthResponse, SchemaResponse } from '../types'

// Base URL — in dev mode, Vite proxy forwards /chat → http://localhost:8000/chat
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
}
