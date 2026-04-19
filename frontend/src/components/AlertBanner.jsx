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
        <span className="text-2xl">
          {isCritical ? (
            <svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <circle cx="12" cy="12" r="10"/>
              <line x1="12" y1="8" x2="12" y2="12"/>
              <line x1="12" y1="16" x2="12.01" y2="16"/>
            </svg>
          ) : (
            <svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"/>
              <line x1="12" y1="9" x2="12" y2="13"/>
              <line x1="12" y1="17" x2="12.01" y2="17"/>
            </svg>
          )}
        </span>
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
