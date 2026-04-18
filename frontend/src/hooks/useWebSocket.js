import { useEffect, useRef, useState, useCallback } from 'react'

const WS_URL = import.meta.env.VITE_WS_URL || 'ws://localhost:8000/ws'

/**
 * Reusable WebSocket hook with automatic exponential-backoff reconnection.
 *
 * Returns:
 *   lastMessage  — last parsed JSON frame (or null)
 *   readyState   — 'connecting' | 'open' | 'closed'
 *   send         — function(string|object) → void
 */
export function useWebSocket() {
  const wsRef       = useRef(null)
  const unmounted   = useRef(false)
  const retryDelay  = useRef(1000)
  const retryTimer  = useRef(null)

  const [lastMessage, setLastMessage] = useState(null)
  const [readyState,  setReadyState]  = useState('connecting')

  const connect = useCallback(() => {
    if (unmounted.current) return
    setReadyState('connecting')

    const ws = new WebSocket(WS_URL)
    wsRef.current = ws

    ws.onopen = () => {
      if (unmounted.current) { ws.close(); return }
      retryDelay.current = 1000          // reset backoff on successful connect
      setReadyState('open')
    }

    ws.onmessage = ({ data }) => {
      if (unmounted.current) return
      try { setLastMessage(JSON.parse(data)) } catch { /* non-JSON — ignore */ }
    }

    ws.onclose = () => {
      if (unmounted.current) return
      setReadyState('closed')
      // Exponential back-off: 1s → 2s → 4s → … capped at 15s
      retryTimer.current = setTimeout(() => {
        retryDelay.current = Math.min(retryDelay.current * 2, 15000)
        connect()
      }, retryDelay.current)
    }

    ws.onerror = () => ws.close()
  }, [])

  useEffect(() => {
    connect()
    return () => {
      unmounted.current = true
      clearTimeout(retryTimer.current)
      wsRef.current?.close()
    }
  }, [connect])

  const send = useCallback((data) => {
    const ws = wsRef.current
    if (ws?.readyState === WebSocket.OPEN) {
      ws.send(typeof data === 'string' ? data : JSON.stringify(data))
    }
  }, [])

  return { lastMessage, readyState, send }
}
