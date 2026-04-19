import React, { useState, useEffect, useRef } from 'react'
import axios from 'axios'

const API = import.meta.env.VITE_API_URL || 'http://localhost:8000'
const ACK_SECONDS = 90

// Agency action text keyed by surge_type
const AGENCY_ACTIONS = {
  police: {
    GENUINE_CRUSH:  (r) => `URGENT: Deploy officers to Choke Point B immediately. Est crowd: ${Math.round(r?.flow_rate ?? 0)} pax/min.`,
    SELF_RESOLVING: ()  => 'CAUTION: Monitor Choke Point B. Surge detected but may self-resolve.',
    SAFE:           ()  => 'Standby — Monitor corridor feeds. All clear.',
  },
  temple: {
    GENUINE_CRUSH:  ()  => 'URGENT: Activate darshan hold at inner gate. Redirect to Queue C.',
    SELF_RESOLVING: ()  => 'CAUTION: Prepare to activate darshan hold if CPI exceeds 0.75.',
    SAFE:           ()  => 'Normal operations. Darshan proceeding normally.',
  },
  gsrtc: {
    GENUINE_CRUSH:  ()  => 'URGENT: Hold ALL incoming buses at 3km checkpoint now.',
    SELF_RESOLVING: ()  => 'CAUTION: Slow incoming buses. Hold if CPI rises above 0.75.',
    SAFE:           ()  => 'Normal schedule. No holds required.',
  },
}

const AGENCY_ICONS = {
  police: (
    <svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M12 2L4 6v6c0 5.25 3.5 10.15 8 11.5C16.5 22.15 20 17.25 20 12V6L12 2z"/>
      <path d="M9 12l2 2 4-4"/>
    </svg>
  ),
  temple: (
    <svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M12 2L2 7h20L12 2z"/>
      <rect x="4" y="7" width="16" height="13"/>
      <rect x="9" y="12" width="6" height="8"/>
      <line x1="12" y1="2" x2="12" y2="7"/>
    </svg>
  ),
  gsrtc: (
    <svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <rect x="1" y="6" width="22" height="13" rx="2"/>
      <path d="M16 6V4a2 2 0 0 0-2-2h-4a2 2 0 0 0-2 2v2"/>
      <circle cx="7" cy="19" r="2"/><circle cx="17" cy="19" r="2"/>
      <line x1="9" y1="19" x2="15" y2="19"/>
    </svg>
  ),
}

const AGENCY_META = {
  police: { label: 'Police Control Room',      color: 'blue'   },
  temple: { label: 'Temple Trust Authority',   color: 'yellow' },
  gsrtc:  { label: 'GSRTC Bus Operations',     color: 'green'  },
}

const BORDER = { blue: 'border-blue-500', yellow: 'border-yellow-500', green: 'border-green-500' }
const BG_ACK = { blue: 'bg-blue-950',     yellow: 'bg-yellow-950',     green: 'bg-green-950'     }

/**
 * Agency-specific alert card with 90-second countdown and acknowledge button.
 *
 * Props:
 *   agency           — 'police' | 'temple' | 'gsrtc'
 *   corridorData     — { Ambaji: {...}, Dwarka: {...}, ... }
 *   selectedCorridor — currently selected corridor name
 */
export default function AgencyPanel({ agency, corridorData, selectedCorridor }) {
  const meta    = AGENCY_META[agency]

  // 'driver' and 'admin' roles don't have agency panels — return nothing
  if (!meta) return null

  const reading = corridorData?.[selectedCorridor] || null

  // Normalise surge type — map legacy types to the three canonical ones
  const rawSurge = reading?.surge_type || 'SAFE'
  const surgeType = (
    rawSurge === 'GENUINE_CRUSH'    ? 'GENUINE_CRUSH'  :
    rawSurge === 'SELF_RESOLVING'   ? 'SELF_RESOLVING' :
    rawSurge === 'PREDICTED_BREACH' ? 'GENUINE_CRUSH'  :
    rawSurge === 'HIGH_PRESSURE'    ? 'SELF_RESOLVING' :
    'SAFE'
  )

  const isActive = reading?.alert_active === true
  const alertId  = reading?.alert_id

  const [acked,    setAcked]   = useState(false)
  const [ackTime,  setAckTime] = useState(null)
  const [secsLeft, setSecsLeft] = useState(ACK_SECONDS)
  const [ackError, setAckError] = useState(null)
  const prevAlertId = useRef(null)
  const timerRef    = useRef(null)

  // Reset when a new alert arrives
  useEffect(() => {
    if (alertId && alertId !== prevAlertId.current) {
      prevAlertId.current = alertId
      setAcked(false)
      setAckTime(null)
      setAckError(null)
      setSecsLeft(ACK_SECONDS)
    }
  }, [alertId])

  // Countdown timer
  useEffect(() => {
    clearInterval(timerRef.current)
    if (!isActive || acked) return
    timerRef.current = setInterval(() => {
      setSecsLeft((s) => {
        if (s <= 1) { clearInterval(timerRef.current); return 0 }
        return s - 1
      })
    }, 1000)
    return () => clearInterval(timerRef.current)
  }, [isActive, acked, alertId])

  const handleAck = async () => {
    if (!alertId) return
    try {
      await axios.post(`${API}/api/ack/${alertId}/${agency}`)
      setAcked(true)
      setAckTime(new Date().toLocaleTimeString())
      clearInterval(timerRef.current)
    } catch {
      setAckError('Ack failed — retry')
    }
  }

  // Get action text
  const actionFn = AGENCY_ACTIONS[agency]?.[surgeType] || AGENCY_ACTIONS[agency]?.SAFE
  const action   = actionFn ? actionFn(reading) : 'Standby — monitoring.'

  const timerPct = (secsLeft / ACK_SECONDS) * 100
  const timerCls = secsLeft > 45 ? 'bg-green-500' : secsLeft > 20 ? 'bg-amber-500' : 'bg-red-600'

  return (
    <div className={`rounded-xl border transition-all duration-300 p-4 ${
      isActive
        ? `${BORDER[meta.color]} ${BG_ACK[meta.color]}`
        : 'border-gray-700 bg-gray-900 opacity-70'
    }`}>

      {/* Header */}
      <div className="flex items-start justify-between mb-3">
        <div className="flex items-center gap-2">
          <span className="text-2xl">{AGENCY_ICONS[agency]}</span>
          <div>
            <p className="font-bold text-sm text-white leading-tight">{meta.label}</p>
            <p className="text-xs text-gray-400 uppercase tracking-wide">{agency}</p>
          </div>
        </div>
        {isActive && <SurgeBadge type={surgeType} />}
      </div>

      {/* Action */}
      <div className={`rounded-lg p-3 mb-3 ${isActive ? 'bg-black/30' : 'bg-gray-800'}`}>
        <p className="text-xs text-gray-400 uppercase tracking-wide mb-1">Required Action</p>
        <p className="text-sm text-white font-medium leading-snug">{action}</p>
      </div>

      {/* Time to breach */}
      {isActive && reading?.time_to_breach_seconds != null && (
        <div className="text-xs text-center mb-3">
          <span className="text-gray-400">Crush risk in </span>
          <span className={`font-bold font-mono text-sm ${reading.time_to_breach_seconds < 120 ? 'text-red-400 animate-pulse' : 'text-amber-300'}`}>
            {Math.floor(reading.time_to_breach_seconds / 60)}m {reading.time_to_breach_seconds % 60 | 0}s
          </span>
        </div>
      )}

      {/* Ack timer + button */}
      {isActive && !acked && (
        <>
          <div className="flex justify-between text-xs text-gray-400 mb-1">
            <span>Acknowledgement required</span>
            <span className={secsLeft <= 15 ? 'text-red-400 font-bold animate-pulse' : ''}>{secsLeft}s</span>
          </div>
          <div className="w-full h-1.5 bg-gray-700 rounded-full mb-3 overflow-hidden">
            <div
              className={`h-full rounded-full transition-all duration-1000 ${timerCls}`}
              style={{ width: `${timerPct}%` }}
            />
          </div>
          {ackError && <p className="text-xs text-red-400 mb-2">{ackError}</p>}
          <button
            onClick={handleAck}
            disabled={secsLeft === 0}
            className={`w-full py-2.5 rounded-lg text-sm font-bold transition-all active:scale-95 ${
              secsLeft === 0
                ? 'bg-red-900 text-red-300 cursor-not-allowed'
                : 'bg-white text-gray-900 hover:bg-gray-100'
            }`}
          >
            {secsLeft === 0 ? (
              <span className="flex items-center justify-center gap-1.5">
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round"><path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"/><line x1="12" y1="9" x2="12" y2="13"/><line x1="12" y1="17" x2="12.01" y2="17"/></svg>
                TIMEOUT — ESCALATING
              </span>
            ) : 'ACKNOWLEDGE & DEPLOY'}
          </button>
        </>
      )}

      {/* Acknowledged */}
      {acked && (
        <div className="flex items-center gap-2 text-green-400 text-sm font-semibold py-1">
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round"><path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"/><polyline points="22 4 12 14.01 9 11.01"/></svg>
          <span>Acknowledged at {ackTime}</span>
        </div>
      )}

      {/* Idle */}
      {!isActive && (
        <p className="text-xs text-gray-500 text-center py-1">Monitoring — No active alert</p>
      )}
    </div>
  )
}

function SurgeBadge({ type }) {
  const cfg = {
    GENUINE_CRUSH:  {
      cls: 'bg-red-900 text-red-300 animate-pulse',
      icon: <svg width="10" height="10" viewBox="0 0 24 24" fill="currentColor"><circle cx="12" cy="12" r="10"/></svg>,
      label: 'CRUSH',
    },
    SELF_RESOLVING: {
      cls: 'bg-blue-900 text-blue-300',
      icon: <svg width="10" height="10" viewBox="0 0 24 24" fill="currentColor"><circle cx="12" cy="12" r="10"/></svg>,
      label: 'RESOLVING',
    },
    SAFE: {
      cls: 'bg-gray-800 text-gray-300',
      icon: <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5"><path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"/><polyline points="22 4 12 14.01 9 11.01"/></svg>,
      label: 'SAFE',
    },
  }
  const { cls, icon, label } = cfg[type] || cfg.SAFE
  return (
    <span className={`inline-flex items-center gap-1 text-xs font-bold px-2 py-1 rounded-full ${cls}`}>
      {icon}{label}
    </span>
  )
}
