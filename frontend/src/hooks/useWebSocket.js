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
 *   busData            — array of live bus position objects from bus_update messages
 *   connectionStatus   — 'connecting' | 'connected' | 'disconnected'
 *   lastUpdate         — Date of last received message
 *   retryCount         — number of reconnection attempts
 */
export function useWebSocket() {
  const wsRef         = useRef(null)
  const unmounted     = useRef(false)
  const retryDelay    = useRef(1000)
  const retryTimer    = useRef(null)
  const retryCount    = useRef(0)

  const [corridorData, setCorridorData] = useState({
    Ambaji:   {},
    Dwarka:   {},
    Somnath:  {},
    Pavagadh: {}
  })
  const [corridorHistory, setCorridorHistory] = useState(
    () => Object.fromEntries(CORRIDORS.map((c) => [c, []]))
  )
  const [busData,          setBusData]          = useState([])
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
      console.log('WebSocket connected')
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
        return
      }

      if (parsed.type === 'ping') return

      if (parsed.type === 'cpi_update' && parsed.corridor) {
        // Store data for this corridor
        setCorridorData(prev => ({
          ...prev,
          [parsed.corridor]: {
            cpi: parsed.cpi,
            flow_rate: parsed.flow_rate,
            transport_burst: parsed.transport_burst,
            chokepoint_density: parsed.chokepoint_density,
            surge_type: parsed.surge_type,
            corridor_state: parsed.corridor_state,
            time_to_breach_seconds: parsed.time_to_breach_seconds,
            time_to_breach_minutes: parsed.time_to_breach_minutes,
            alert_active: parsed.alert_active,
            alert_id: parsed.alert_id,
            ml_confidence: parsed.ml_confidence,
            ml_risk_level: parsed.ml_risk_level,
            alert_lifecycle_state: parsed.alert_lifecycle_state,
            alert_acknowledged_by: parsed.alert_acknowledged_by || [],
            alert_duration_minutes: parsed.alert_duration_minutes || 0,
            data_source: parsed.data_source,
            vision_active: parsed.vision_active,
            vision_count: parsed.vision_count,
            corridor: parsed.corridor,
            timestamp: parsed.timestamp
          }
        }))

        // Update history for charts
        setCorridorHistory(prev => {
          const key = parsed.corridor
          const existing = prev[key] || []
          const updated = [
            ...existing,
            {
              time: new Date().toLocaleTimeString(),
              cpi: parsed.cpi,
              flow_rate: parsed.flow_rate
            }
          ].slice(-MAX_HISTORY)  // keep last 60 readings
          return { ...prev, [key]: updated }
        })

        setLastUpdate(new Date())
        return
      }

      if (parsed.type === 'bus_update' && Array.isArray(parsed.buses)) {
        setBusData(parsed.buses)
        setLastUpdate(new Date())
        return
      }

      if (parsed.type === 'cpi_batch' && Array.isArray(parsed.data)) {
        parsed.data.forEach((r) => {
          if (r && r.corridor) applyReading(r)
        })
        setLastUpdate(new Date())
        return
      }

      // Forward other message types to window for App.jsx to handle
      if (['alert_resolved', 'pdf_ready', 'call_update', 'vision_progress', 'vision_complete', 'vision_started', 'replies_update', 'ack_timer_started', 'ack_timeout', 'call_suppressed'].includes(parsed.type)) {
        window.dispatchEvent(new CustomEvent('ws_message', { detail: parsed }))
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
    setCorridorData((prev) => ({
      ...prev,
      [reading.corridor]: {
        cpi: reading.cpi,
        flow_rate: reading.flow_rate,
        transport_burst: reading.transport_burst,
        chokepoint_density: reading.chokepoint_density,
        surge_type: reading.surge_type,
        corridor_state: reading.corridor_state,
        time_to_breach_seconds: reading.time_to_breach_seconds,
        time_to_breach_minutes: reading.time_to_breach_minutes,
        alert_active: reading.alert_active,
        alert_id: reading.alert_id,
        ml_confidence: reading.ml_confidence,
        ml_risk_level: reading.ml_risk_level,
        alert_lifecycle_state: reading.alert_lifecycle_state,
        alert_acknowledged_by: reading.alert_acknowledged_by || [],
        alert_duration_minutes: reading.alert_duration_minutes || 0,
        data_source: reading.data_source,
        vision_active: reading.vision_active,
        vision_count: reading.vision_count,
        corridor: reading.corridor,
        timestamp: reading.timestamp
      }
    }))
    setCorridorHistory((prev) => {
      const existing = prev[reading.corridor] || []
      const entry = {
        time: new Date().toLocaleTimeString(),
        cpi: reading.cpi,
        flow_rate: reading.flow_rate
      }
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
        wsRef.current.onclose = null
        wsRef.current.close()
      }
    }
  }, [connect])

  return {
    corridorData,
    corridorHistory,
    busData,
    connectionStatus,
    lastUpdate,
    retryCount: retryCount.current,
  }
}
