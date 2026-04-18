import { useEffect, useRef, useState, useCallback } from 'react'

const WS_URL = import.meta.env.VITE_WS_URL || 'ws://localhost:8000/ws'
const CORRIDORS = ['Ambaji', 'Dwarka', 'Somnath', 'Pavagadh']
const MAX_HISTORY = 60

/**
 * WebSocket hook with exponential backoff reconnection.
 *
 * Returns:
 *   corridorData       — { Ambaji: {...}, Dwarka: {...}, ... } latest reading per corridor
 *   corridorHistory    — { Ambaji: [{cpi, t}, ...], ... } last 60 readings per corridor
 *   connectionStatus   — 'connecting' | 'connected' | 'disconnected'
 *   lastUpdate         — Date of last received message
 */
export function useWebSocket() {
  const wsRef         = useRef(null)
  const unmounted     = useRef(false)
  const retryDelay    = useRef(1000)
  const retryTimer    = useRef(null)
  const retryCount    = useRef(0)

  const [corridorData,    setCorridorData]    = useState({})
  const [corridorHistory, setCorridorHistory] = useState(
    () => Object.fromEntries(CORRIDORS.map((c) => [c, []]))
  )
  const [connectionStatus, setConnectionStatus] = useState('connecting')
  const [lastUpdate,       setLastUpdate]        = useState(null)

  const connect = useCallback(() => {
    if (unmounted.current) return
    setConnectionStatus('connecting')

    let ws
    try {
      ws = new WebSocket(WS_URL)
    } catch (err) {
      console.error('WebSocket construction failed:', err)
      scheduleReconnect()
      return
    }

    wsRef.current = ws

    ws.onopen = () => {
      if (unmounted.current) { ws.close(); return }
      console.log('WebSocket connected ✓')
      retryDelay.current = 1000
      retryCount.current = 0
      setConnectionStatus('connected')
    }

    ws.onmessage = ({ data }) => {
      if (unmounted.current) return
      let parsed
      try {
        parsed = JSON.parse(data)
      } catch {
        return // ignore non-JSON
      }

      // Silently ignore ping frames
      if (parsed.type === 'ping') return

      // Handle single cpi_update
      if (parsed.type === 'cpi_update' && parsed.corridor) {
        console.log('Received:', parsed.corridor, parsed.cpi)
        applyReading(parsed)
        setLastUpdate(new Date())
        return
      }

      // Handle batch (legacy support)
      if (parsed.type === 'cpi_batch' && Array.isArray(parsed.data)) {
        parsed.data.forEach((r) => {
          if (r && r.corridor) {
            console.log('Received:', r.corridor, r.cpi)
            applyReading(r)
          }
        })
        setLastUpdate(new Date())
      }
    }

    ws.onclose = () => {
      if (unmounted.current) return
      setConnectionStatus('disconnected')
      scheduleReconnect()
    }

    ws.onerror = (err) => {
      console.error('WebSocket error:', err)
      ws.close()
    }
  }, []) // eslint-disable-line react-hooks/exhaustive-deps

  function applyReading(reading) {
    setCorridorData((prev) => ({ ...prev, [reading.corridor]: reading }))
    setCorridorHistory((prev) => {
      const existing = prev[reading.corridor] || []
      const entry = { cpi: reading.cpi, t: new Date().toLocaleTimeString() }
      const updated = [...existing, entry].slice(-MAX_HISTORY)
      return { ...prev, [reading.corridor]: updated }
    })
  }

  function scheduleReconnect() {
    if (unmounted.current) return
    retryCount.current += 1
    const delay = Math.min(retryDelay.current, 15000)
    retryTimer.current = setTimeout(() => {
      retryDelay.current = Math.min(retryDelay.current * 2, 15000)
      connect()
    }, delay)
  }

  useEffect(() => {
    unmounted.current = false
    connect()
    return () => {
      unmounted.current = true
      clearTimeout(retryTimer.current)
      if (wsRef.current) {
        wsRef.current.onclose = null // prevent reconnect on intentional close
        wsRef.current.close()
      }
    }
  }, [connect])

  return { corridorData, corridorHistory, connectionStatus, lastUpdate, retryCount: retryCount.current }
}
