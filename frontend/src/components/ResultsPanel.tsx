import { useState } from 'react'
import type { ChatResponse } from '../types'
import { DataTable } from './DataTable'

interface ResultsPanelProps {
  result: ChatResponse | null
  isLoading?: boolean
}

const INTENT_LABELS: Record<string, { label: string; color: string }> = {
  slice:         { label: 'Slice',         color: 'bg-purple-100 text-purple-700' },
  dice:          { label: 'Dice',          color: 'bg-indigo-100 text-indigo-700' },
  drill_down:    { label: 'Drill-Down',    color: 'bg-blue-100 text-blue-700' },
  roll_up:       { label: 'Roll-Up',       color: 'bg-cyan-100 text-cyan-700' },
  compare:       { label: 'Compare',       color: 'bg-green-100 text-green-700' },
  kpi:           { label: 'KPI',           color: 'bg-yellow-100 text-yellow-700' },
  pivot:         { label: 'Pivot',         color: 'bg-orange-100 text-orange-700' },
  drill_through: { label: 'Drill-Through', color: 'bg-red-100 text-red-700' },
  dimensions:    { label: 'Dimensions',    color: 'bg-teal-100 text-teal-700' },
  anomaly:       { label: 'Anomaly',       color: 'bg-rose-100 text-rose-700' },
}

export function ResultsPanel({ result, isLoading }: ResultsPanelProps) {
  const [showSql, setShowSql] = useState(false)

  if (isLoading) {
    return (
      <div className="flex flex-col h-full items-center justify-center text-gray-400 gap-3">
        <div className="relative h-12 w-12">
          <div className="absolute inset-0 rounded-full border-4 border-blue-200 animate-ping opacity-40" />
          <div className="absolute inset-0 rounded-full border-4 border-blue-500 border-t-transparent animate-spin" />
        </div>
        <p className="text-sm">Analyzing your query...</p>
      </div>
    )
  }

  if (!result) {
    return (
      <div className="flex flex-col h-full items-center justify-center text-center p-8 text-gray-400">
        <div className="w-20 h-20 mb-4 rounded-2xl bg-gradient-to-br from-blue-50 to-indigo-100 flex items-center justify-center">
          <svg className="h-10 w-10 text-blue-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5}
              d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z" />
          </svg>
        </div>
        <h3 className="font-semibold text-gray-600 mb-1">Results will appear here</h3>
        <p className="text-sm">Ask a question to run an OLAP analysis on the Global Retail Sales dataset.</p>

        {/* Dataset overview cards */}
        <div className="grid grid-cols-2 gap-3 mt-6 w-full max-w-sm text-left">
          {[
            { label: 'Total Records', value: '10,000', icon: '📊' },
            { label: 'Time Period', value: '2022–2024', icon: '📅' },
            { label: 'Regions', value: '4 regions', icon: '🌍' },
            { label: 'Categories', value: '4 categories', icon: '📦' },
          ].map(card => (
            <div key={card.label} className="bg-white rounded-xl border border-gray-200 p-3 shadow-sm">
              <div className="text-lg">{card.icon}</div>
              <div className="text-xs text-gray-500 mt-1">{card.label}</div>
              <div className="text-sm font-semibold text-gray-700 mt-0.5">{card.value}</div>
            </div>
          ))}
        </div>

        {/* OLAP operations reference */}
        <div className="mt-6 w-full max-w-sm text-left">
          <p className="text-xs font-medium text-gray-500 mb-2 uppercase tracking-wide">Supported Operations</p>
          <div className="flex flex-wrap gap-1.5">
            {Object.entries(INTENT_LABELS).map(([, { label, color }]) => (
              <span key={label} className={`text-xs px-2 py-0.5 rounded-full font-medium ${color}`}>
                {label}
              </span>
            ))}
          </div>
        </div>
      </div>
    )
  }

  if (result.error) {
    return (
      <div className="p-6">
        <div className="rounded-xl bg-red-50 border border-red-200 p-4">
          <div className="flex items-start gap-3">
            <svg className="h-5 w-5 text-red-500 mt-0.5 flex-shrink-0" fill="currentColor" viewBox="0 0 20 20">
              <path fillRule="evenodd" d="M18 10a8 8 0 11-16 0 8 8 0 0116 0zm-7 4a1 1 0 11-2 0 1 1 0 012 0zm-1-9a1 1 0 00-1 1v4a1 1 0 102 0V6a1 1 0 00-1-1z" clipRule="evenodd" />
            </svg>
            <div>
              <p className="font-medium text-red-700 text-sm">Query Error</p>
              <p className="text-red-600 text-sm mt-1">{result.error}</p>
            </div>
          </div>
        </div>
      </div>
    )
  }

  const intentMeta = INTENT_LABELS[result.intent] || { label: result.intent, color: 'bg-gray-100 text-gray-600' }

  return (
    <div className="flex flex-col h-full overflow-y-auto scrollbar-thin">
      {/* Header */}
      <div className="p-4 border-b border-gray-100 flex-shrink-0">
        <div className="flex items-center justify-between flex-wrap gap-2">
          <div className="flex items-center gap-2">
            <span className={`text-xs font-semibold px-2.5 py-1 rounded-full ${intentMeta.color}`}>
              {intentMeta.label}
            </span>
            {result.agents_used?.map(agent => (
              <span key={agent} className="text-xs px-2 py-0.5 rounded bg-gray-100 text-gray-500">
                {agent}
              </span>
            ))}
          </div>
          <span className="text-xs text-gray-400">{result.latency_ms}ms</span>
        </div>
      </div>

      {/* Narrative */}
      {result.narrative && (
        <div className="px-4 py-3 flex-shrink-0">
          <div className="rounded-xl bg-gradient-to-r from-blue-50 to-indigo-50 border border-blue-100 p-4">
            <div className="flex gap-2">
              <svg className="h-5 w-5 text-blue-500 flex-shrink-0 mt-0.5" fill="currentColor" viewBox="0 0 20 20">
                <path fillRule="evenodd" d="M18 10a8 8 0 11-16 0 8 8 0 0116 0zm-7-4a1 1 0 11-2 0 1 1 0 012 0zM9 9a1 1 0 000 2v3a1 1 0 001 1h1a1 1 0 100-2v-3a1 1 0 00-1-1H9z" clipRule="evenodd" />
              </svg>
              <p className="text-sm text-gray-700 leading-relaxed">{result.narrative}</p>
            </div>
          </div>
        </div>
      )}

      {/* Data table */}
      {result.data && result.data.columns.length > 0 && (
        <div className="px-4 pb-3 flex-shrink-0">
          {/* Visualization hint badge */}
          {result.visualization_hint && result.visualization_hint.chart_type !== 'table' && (
            <div className="mb-2 flex items-center gap-2">
              <span className="text-xs text-gray-400">Suggested visualization:</span>
              <span className="text-xs font-medium text-blue-600 bg-blue-50 px-2 py-0.5 rounded">
                {result.visualization_hint.chart_type} chart
                {result.visualization_hint.x_axis && ` (${result.visualization_hint.x_axis} × ${result.visualization_hint.y_axis})`}
              </span>
            </div>
          )}
          <DataTable
            columns={result.data.columns}
            rows={result.data.rows}
            rowCount={result.data.row_count}
          />
        </div>
      )}

      {/* SQL query (collapsible) */}
      {result.sql_query && (
        <div className="px-4 pb-3 flex-shrink-0">
          <button
            onClick={() => setShowSql(!showSql)}
            className="flex items-center gap-1.5 text-xs text-gray-400 hover:text-gray-600 transition-colors"
          >
            <svg
              className={`h-3.5 w-3.5 transition-transform ${showSql ? 'rotate-90' : ''}`}
              fill="none" viewBox="0 0 24 24" stroke="currentColor"
            >
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" />
            </svg>
            <span className="font-mono">{showSql ? 'Hide' : 'Show'} SQL</span>
          </button>
          {showSql && (
            <pre className="mt-2 p-3 rounded-lg bg-gray-900 text-green-400 text-xs font-mono overflow-x-auto scrollbar-thin whitespace-pre-wrap">
              {result.sql_query}
            </pre>
          )}
        </div>
      )}

      {/* Follow-up suggestions */}
      {result.follow_up_suggestions && result.follow_up_suggestions.length > 0 && (
        <div className="px-4 pb-4 flex-shrink-0 mt-auto">
          <p className="text-xs text-gray-400 mb-2 font-medium uppercase tracking-wide">Suggested follow-ups</p>
          <div className="flex flex-col gap-1.5">
            {result.follow_up_suggestions.map((q, i) => (
              <div key={i} className="text-xs text-gray-500 bg-gray-50 border border-gray-200 rounded-lg px-3 py-2 flex items-center gap-2">
                <span className="text-gray-300">→</span>
                {q}
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}
