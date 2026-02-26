import { useEffect, useState } from 'react'
import { ChatInput } from './components/ChatInput'
import { ConversationHistory } from './components/ConversationHistory'
import { ResultsPanel } from './components/ResultsPanel'
import { SampleQuestions } from './components/SampleQuestions'
import { useChat } from './hooks/useChat'
import { api } from './api/client'
import type { HealthResponse } from './types'

export default function App() {
  const { messages, currentResult, isLoading, sendMessage, clearSession } = useChat()
  const [health, setHealth] = useState<HealthResponse | null>(null)
  const [sidebarOpen, setSidebarOpen] = useState(true)

  // Check backend health on load
  useEffect(() => {
    api.health()
      .then(setHealth)
      .catch(() => setHealth(null))
  }, [])

  return (
    <div className="flex flex-col h-screen bg-gray-50">
      {/* ── Top navigation bar ── */}
      <header className="flex-shrink-0 bg-white border-b border-gray-200 px-4 py-3 flex items-center justify-between shadow-sm z-20">
        <div className="flex items-center gap-3">
          <button
            onClick={() => setSidebarOpen(!sidebarOpen)}
            className="p-1.5 rounded-lg hover:bg-gray-100 text-gray-500 transition-colors lg:hidden"
          >
            <svg className="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 6h16M4 12h16M4 18h16" />
            </svg>
          </button>

          {/* Logo */}
          <div className="flex items-center gap-2">
            <div className="h-8 w-8 rounded-lg bg-gradient-to-br from-blue-500 to-indigo-600 flex items-center justify-center shadow-sm">
              <svg className="h-4 w-4 text-white" fill="currentColor" viewBox="0 0 20 20">
                <path d="M2 11a1 1 0 011-1h2a1 1 0 011 1v5a1 1 0 01-1 1H3a1 1 0 01-1-1v-5zM8 7a1 1 0 011-1h2a1 1 0 011 1v9a1 1 0 01-1 1H9a1 1 0 01-1-1V7zM14 4a1 1 0 011-1h2a1 1 0 011 1v12a1 1 0 01-1 1h-2a1 1 0 01-1-1V4z" />
              </svg>
            </div>
            <div>
              <h1 className="text-sm font-bold text-gray-900 leading-none">OLAP BI Assistant</h1>
              <p className="text-xs text-gray-400 leading-none mt-0.5">Global Retail Sales · Multi-Agent</p>
            </div>
          </div>
        </div>

        <div className="flex items-center gap-3">
          {/* Health indicator */}
          <div className="hidden sm:flex items-center gap-1.5 text-xs">
            <div className={`h-2 w-2 rounded-full ${health?.db_connected ? 'bg-green-400' : 'bg-red-400'}`} />
            <span className="text-gray-500">
              {health?.db_connected
                ? `${(health.db_row_count / 1000).toFixed(0)}K rows`
                : 'DB offline'}
            </span>
          </div>

          {/* Clear session */}
          <button
            onClick={clearSession}
            className="text-xs px-3 py-1.5 rounded-lg border border-gray-200 text-gray-500 hover:bg-gray-50 hover:text-gray-700 transition-colors"
          >
            New Session
          </button>

          {/* API Docs link */}
          <a
            href="http://localhost:8000/docs"
            target="_blank"
            rel="noopener noreferrer"
            className="text-xs px-3 py-1.5 rounded-lg border border-gray-200 text-gray-500 hover:bg-gray-50 transition-colors hidden sm:block"
          >
            API Docs
          </a>
        </div>
      </header>

      {/* ── Main layout ── */}
      <div className="flex flex-1 overflow-hidden">

        {/* ── Left panel: Conversation History ── */}
        <div
          className={`
            flex-shrink-0 bg-white border-r border-gray-200 flex flex-col
            transition-all duration-300
            ${sidebarOpen ? 'w-80 lg:w-96' : 'w-0 overflow-hidden'}
          `}
        >
          {/* Panel header */}
          <div className="flex-shrink-0 px-4 py-3 border-b border-gray-100 flex items-center justify-between">
            <h2 className="text-sm font-semibold text-gray-700">Conversation</h2>
            {messages.length > 0 && (
              <span className="text-xs text-gray-400">{Math.ceil(messages.length / 2)} turn{Math.ceil(messages.length / 2) !== 1 ? 's' : ''}</span>
            )}
          </div>

          {/* Chat history */}
          <div className="flex-1 overflow-hidden">
            <ConversationHistory
              messages={messages}
              onFollowUp={sendMessage}
            />
          </div>
        </div>

        {/* ── Right panel: Results + Chat input ── */}
        <div className="flex-1 flex flex-col overflow-hidden min-w-0">

          {/* Sample questions bar */}
          <div className="flex-shrink-0 px-4 py-2 bg-white border-b border-gray-100 flex items-center gap-3">
            <span className="text-xs text-gray-400 font-medium hidden sm:block whitespace-nowrap">Try:</span>
            <SampleQuestions onSelect={sendMessage} disabled={isLoading} />
          </div>

          {/* Results */}
          <div className="flex-1 overflow-hidden bg-white mx-4 my-3 rounded-xl border border-gray-200 shadow-sm">
            <ResultsPanel result={currentResult} isLoading={isLoading} />
          </div>

          {/* Chat input */}
          <div className="flex-shrink-0 px-4 pb-4">
            <ChatInput onSend={sendMessage} disabled={isLoading} />
            <p className="text-xs text-gray-400 mt-1.5 text-center">
              Supports: Slice · Dice · Drill-Down · Roll-Up · Compare · Pivot · Drill-Through
            </p>
          </div>
        </div>
      </div>
    </div>
  )
}
