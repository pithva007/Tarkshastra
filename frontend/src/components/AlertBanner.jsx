import React, { useEffect, useState } from 'react'

/**
 * Full-width top banner that appears when any corridor fires an alert.
 *
 * Props:
 *   readings — array of live CPI reading objects from WebSocket
 */
export default function AlertBanner({ readings = [] }) {
  const [visible, setVisible] = useState(false)
  const [dismissed, setDismissed] = useState(null) // dismissed alert_id

  // Find the most severe active alert across all corridors
  const critical = readings.find((r) => r.surge_type === 'GENUINE_CRUSH' && r.alert_active)
  const high     = readings.find((r) => r.surge_type === 'PREDICTED_BREACH' && r.alert_active)
  const active   = critical || high

  useEffect(() => {
    if (active && active.alert_id !== dismissed) {
      setVisible(true)
    } else {
      setVisible(false)
    }
  }, [active?.alert_id, dismissed])

  if (!visible || !active) return null

  const isCritical = active.surge_type === 'GENUINE_CRUSH'
  const ttbMin = active.time_to_breach_seconds
    ? Math.ceil(active.time_to_breach_seconds / 60)
    : null

  return (
    <div
      className={`fixed top-0 left-0 right-0 z-[9999] flex items-center justify-between px-4 py-3 shadow-2xl
        ${isCritical
          ? 'bg-red-700 animate-pulse'
          : 'bg-amber-600'
        }`}
      role="alert"
    >
      <div className="flex items-center gap-3">
        <span className="text-2xl">{isCritical ? '🚨' : '⚠️'}</span>
        <div>
          <p className="text-white font-bold text-sm leading-tight">
            {isCritical
              ? `CRITICAL — Genuine crush developing: ${active.corridor}`
              : `ALERT — ${active.corridor}: Crush predicted in ${ttbMin ?? '?'} min`
            }
          </p>
          <p className="text-white/80 text-xs">
            CPI {active.cpi?.toFixed(3)} · {active.surge_type} · {active.alert_id}
          </p>
        </div>
      </div>
      <button
        onClick={() => { setDismissed(active.alert_id); setVisible(false) }}
        className="text-white/70 hover:text-white text-xl font-bold leading-none px-2"
        aria-label="Dismiss"
      >
        ×
      </button>
    </div>
  )
}
