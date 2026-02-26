import { useCallback, useEffect, useRef, useState } from 'react'
import { api } from '../api/client'
import type { ChatResponse, Message } from '../types'

const SESSION_KEY = 'olap_session_id'

function makeId(): string {
  return Math.random().toString(36).slice(2) + Date.now().toString(36)
}

export interface UseChatReturn {
  messages: Message[]
  currentResult: ChatResponse | null
  isLoading: boolean
  sessionId: string | null
  sendMessage: (text: string) => Promise<void>
  clearSession: () => void
}

export function useChat(): UseChatReturn {
  const [messages, setMessages] = useState<Message[]>([])
  const [currentResult, setCurrentResult] = useState<ChatResponse | null>(null)
  const [isLoading, setIsLoading] = useState(false)
  const sessionIdRef = useRef<string | null>(null)

  // Restore or create session ID from localStorage
  useEffect(() => {
    const stored = localStorage.getItem(SESSION_KEY)
    if (stored) {
      sessionIdRef.current = stored
    }
  }, [])

  const sendMessage = useCallback(async (text: string) => {
    if (!text.trim() || isLoading) return

    const userMsgId = makeId()
    const assistantMsgId = makeId()

    // Optimistically add user message
    setMessages(prev => [
      ...prev,
      {
        id: userMsgId,
        role: 'user',
        content: text,
        timestamp: new Date(),
      },
    ])

    // Add loading placeholder for assistant
    setMessages(prev => [
      ...prev,
      {
        id: assistantMsgId,
        role: 'assistant',
        content: '',
        timestamp: new Date(),
        isLoading: true,
      },
    ])

    setIsLoading(true)

    try {
      const response = await api.chat({
        message: text,
        session_id: sessionIdRef.current,
      })

      // Persist session ID
      sessionIdRef.current = response.session_id
      localStorage.setItem(SESSION_KEY, response.session_id)

      setCurrentResult(response)

      // Update assistant message with real content
      setMessages(prev =>
        prev.map(m =>
          m.id === assistantMsgId
            ? {
                ...m,
                content: response.narrative || response.error || 'Analysis complete.',
                isLoading: false,
                response,
              }
            : m,
        ),
      )
    } catch (err) {
      const errorMsg = err instanceof Error ? err.message : 'Unknown error'
      setMessages(prev =>
        prev.map(m =>
          m.id === assistantMsgId
            ? {
                ...m,
                content: `Error: ${errorMsg}`,
                isLoading: false,
              }
            : m,
        ),
      )
    } finally {
      setIsLoading(false)
    }
  }, [isLoading])

  const clearSession = useCallback(() => {
    sessionIdRef.current = null
    localStorage.removeItem(SESSION_KEY)
    setMessages([])
    setCurrentResult(null)
  }, [])

  return {
    messages,
    currentResult,
    isLoading,
    sessionId: sessionIdRef.current,
    sendMessage,
    clearSession,
  }
}
