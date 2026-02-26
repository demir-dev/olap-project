import { useEffect, useRef } from 'react'
import type { Message } from '../types'

interface ConversationHistoryProps {
  messages: Message[]
  onFollowUp?: (question: string) => void
}

export function ConversationHistory({ messages, onFollowUp }: ConversationHistoryProps) {
  const bottomRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  if (messages.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center h-full text-center p-6 text-gray-400">
        <svg className="h-12 w-12 mb-3 opacity-40" fill="none" viewBox="0 0 24 24" stroke="currentColor">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5}
            d="M8 12h.01M12 12h.01M16 12h.01M21 12c0 4.418-4.03 8-9 8a9.863 9.863 0 01-4.255-.949L3 20l1.395-3.72C3.512 15.042 3 13.574 3 12c0-4.418 4.03-8 9-8s9 3.582 9 8z" />
        </svg>
        <p className="text-sm font-medium">No conversation yet</p>
        <p className="text-xs mt-1">Ask a question using the input below</p>
      </div>
    )
  }

  return (
    <div className="flex flex-col gap-3 overflow-y-auto scrollbar-thin p-3 h-full">
      {messages.map(message => (
        <MessageBubble key={message.id} message={message} onFollowUp={onFollowUp} />
      ))}
      <div ref={bottomRef} />
    </div>
  )
}

function MessageBubble({
  message,
  onFollowUp,
}: {
  message: Message
  onFollowUp?: (question: string) => void
}) {
  const isUser = message.role === 'user'

  if (isUser) {
    return (
      <div className="flex justify-end">
        <div className="max-w-[85%] px-4 py-2.5 rounded-2xl rounded-tr-sm bg-blue-600 text-white text-sm shadow-sm">
          {message.content}
        </div>
      </div>
    )
  }

  return (
    <div className="flex flex-col gap-1">
      {/* Agent badge */}
      {message.response && (
        <div className="flex items-center gap-1.5 px-1">
          <div className="h-6 w-6 rounded-full bg-gradient-to-br from-blue-500 to-indigo-600 flex items-center justify-center">
            <svg className="h-3 w-3 text-white" fill="currentColor" viewBox="0 0 20 20">
              <path d="M9 4.804A7.968 7.968 0 005.5 4c-1.255 0-2.443.29-3.5.804v10A7.969 7.969 0 015.5 14c1.669 0 3.218.51 4.5 1.385A7.962 7.962 0 0114.5 14c1.255 0 2.443.29 3.5.804v-10A7.968 7.968 0 0014.5 4c-1.255 0-2.443.29-3.5.804V12a1 1 0 11-2 0V4.804z" />
            </svg>
          </div>
          <span className="text-xs text-gray-400 font-medium">
            {message.response.agents_used?.join(' + ') || 'Assistant'}
          </span>
          {message.response.intent && (
            <span className="text-xs px-1.5 py-0.5 rounded bg-gray-100 text-gray-500 font-mono">
              {message.response.intent}
            </span>
          )}
          {message.response.latency_ms > 0 && (
            <span className="text-xs text-gray-400 ml-auto">
              {message.response.latency_ms}ms
            </span>
          )}
        </div>
      )}

      {/* Message content */}
      <div className="max-w-[90%] px-4 py-2.5 rounded-2xl rounded-tl-sm bg-white border border-gray-200 text-sm shadow-sm">
        {message.isLoading ? (
          <div className="flex gap-1 items-center py-1">
            <div className="w-2 h-2 bg-blue-400 rounded-full animate-bounce [animation-delay:-0.3s]" />
            <div className="w-2 h-2 bg-blue-400 rounded-full animate-bounce [animation-delay:-0.15s]" />
            <div className="w-2 h-2 bg-blue-400 rounded-full animate-bounce" />
          </div>
        ) : (
          <p className="text-gray-800 leading-relaxed">{message.content}</p>
        )}
      </div>

      {/* Follow-up suggestions */}
      {message.response?.follow_up_suggestions && message.response.follow_up_suggestions.length > 0 && onFollowUp && (
        <div className="flex flex-wrap gap-1.5 px-1 mt-1">
          {message.response.follow_up_suggestions.slice(0, 3).map((q, i) => (
            <button
              key={i}
              onClick={() => onFollowUp(q)}
              className="text-xs px-2.5 py-1 rounded-full border border-gray-200 bg-gray-50 text-gray-600 hover:bg-gray-100 hover:border-gray-300 transition-colors"
            >
              {q}
            </button>
          ))}
        </div>
      )}
    </div>
  )
}
