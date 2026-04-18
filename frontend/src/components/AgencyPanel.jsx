import React, { useState, useEffect, useRef } from 'react'
import axios from 'axios'

const API = import.meta.env.VITE_API_URL || 'http://localhost:8000'
const ACK_SECONDS = 90

const AGENCY_META = {
  police: {
    icon: '🚔',
    label: 'Police Control Room',
    color: 'blue',
    actions: {
      PREDICTED_BREACH: 'Deploy officers to Choke Point B — Est. crowd 4,200 — ETA needed: 8 min',
      GENUINE_CRUSH:    'EMERGENCY: Deploy ALL units to Choke Point B — Crowd crush in progress',
      HIGH_PRESSURE:    'Pre-position 6 officers at main entry gate — Monitor crowd density',
      default:          'Standby — Monitor corridor feeds',
    },
  },
  temple: {
    icon: '🛕',
    label: 'Temple Trust Authority',
    color: 'yellow',
    actions: {
      PREDICTED_BREACH: 'Activate darshan hold at inner gate — Redirect overflow to Queue C',
      GENUINE_CRUSH:    'EMERGENCY: Close inner gate NOW — Halt all entry — Clear choke area',
      HIGH_PRESSURE:    'Slow inner gate entry to 50% — Open auxiliary Queue B',
      default:          'Maintain normal darshan queue flow',
    },
  },
  gsrtc: {
    icon: '🚌',
    label: 'GSRTC Bus Operations',
    color: 'green',
    actions: {
      PREDICTED_BREACH: 'Hold incoming buses at 3km checkpoint — Expected pressure drop: 18% in 12 min',
      GENUINE_CRUSH:    'EMERGENCY: Stop ALL bus services — Divert to alternate drop-point at 5km',
      HIGH_PRESSURE:    'Space bus arrivals to 8-minute intervals — Hold 3 buses at staging area',
      default:          'Maintain normal bus scheduling',
    },
  },
}

const BORDER = {
  blue:   'border-blue-500',
  yellow: 'border-yellow-500',
  green:  'border-green-500',
}
const BG_ACK = {
  blue:   'bg-blue-950',
  yellow: 'bg-yellow-950',
  green:  'bg-green-950',
}

/**
 * Agency-specific alert card with 90-second countdown and acknowledge button.
 *
 * Props:
 *   agency    — 'police' | 'temple' | 'gsrtc'
 *   reading   — live CPI reading for the selected corridor
 *   corridor  — corridor name string
 */
export default function AgencyPanel({ agency, reading, corridor }) {
  const meta = AGENCY_META[agency]
  const surgeType = reading?.surge_type || 'NORMAL'
  const isActive  = reading?.alert_active && surgeType !== 'SELF_RESOLVING'
  const alertId   = reading?.alert_id

  const [acked,      setAcked]     = useState(false)
  const [ackTime,    setAckTime]   = useState(null)
  const [secsLeft,   setSecsLeft]  = useState(ACK_SECONDS)
  const [ackError,   setAckError]  = useState(null)
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

  // Countdown
  useEffect(() => {
    clearInterval(timerRef.current)
    if (!isActive || acked) return
    timerRef.current = setInterval(() => {
      setSecsLeft((s) => (s <= 1 ? (clearInterval(timerRef.current), 0) : s - 1))
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
    } catch (e) {
      setAckError('Ack failed — retry')
    }
  }

  const action = meta.actions[surgeType] || meta.actions.default
  const timerPct = (secsLeft / ACK_SECONDS) * 100
  const timerCls = secsLeft > 45 ? 'bg-green-500' : secsLeft > 20 ? 'bg-amber-500' : 'bg-red-600'

  return (
    <div
      className={`rounded-xl border transition-all duration-300 p-4 ${
        isActive ? `${BORDER[meta.color]} ${BG_ACK[meta.color]}` : 'border-gray-700 bg-gray-900 opacity-70'
      }`}
    >
      {/* Header */}
      <div className="flex items-start justify-between mb-3">
        <div className="flex items-center gap-2">
          <span className="text-2xl">{meta.icon}</span>
          <div>
            <p className="font-bold text-sm text-white leading-tight">{meta.label}</p>
            <p className="text-xs text-gray-400 uppercase tracking-wide">{agency}</p>
          </div>
        </div>
        {isActive && (
          <SurgeBadge type={surgeType} />
        )}
      </div>

      {/* Action */}
      <div className={`rounded-lg p-3 mb-3 ${isActive ? 'bg-black/30' : 'bg-gray-800'}`}>
        <p className="text-xs text-gray-400 uppercase tracking-wide mb-1">Required Action</p>
        <p className="text-sm text-white font-medium leading-snug">{action}</p>
      </div>

      {/* TTB countdown */}
      {isActive && reading?.time_to_breach_seconds != null && (
        <div className="text-xs text-center mb-3">
          <span className="text-gray-400">Crush risk in </span>
          <CrushCountdown seconds={reading.time_to_breach_seconds} />
        </div>
      )}

      {/* Ack timer bar + button */}
      {isActive && !acked && (
        <>
          <div className="flex justify-between text-xs text-gray-400 mb-1">
            <span>Acknowledgement required</span>
            <span className={secsLeft <= 15 ? 'text-red-400 font-bold animate-pulse' : ''}>
              {secsLeft}s
            </span>
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
            {secsLeft === 0 ? '⚠️ TIMEOUT — ESCALATING' : 'ACKNOWLEDGE & DEPLOY'}
          </button>
        </>
      )}

      {/* Acknowledged */}
      {acked && (
        <div className="flex items-center gap-2 text-green-400 text-sm font-semibold py-1">
          <span>✅</span>
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
    GENUINE_CRUSH:    ['bg-red-900 text-red-300', '🔴 CRUSH'],
    PREDICTED_BREACH: ['bg-amber-900 text-amber-300', '⚠️ PREDICTED'],
    HIGH_PRESSURE:    ['bg-orange-900 text-orange-300', '🟠 HIGH'],
    SELF_RESOLVING:   ['bg-blue-900 text-blue-300', '🔵 RESOLVING'],
  }
  const [cls, txt] = cfg[type] || ['bg-gray-800 text-gray-300', type]
  return (
    <span className={`text-xs font-bold px-2 py-1 rounded-full ${cls} ${type === 'GENUINE_CRUSH' ? 'animate-pulse' : ''}`}>
      {txt}
    </span>
  )
}

function CrushCountdown({ seconds }) {
  const [secs, setSecs] = useState(Math.round(seconds))
  useEffect(() => { setSecs(Math.round(seconds)) }, [seconds])
  const m = Math.floor(secs / 60)
  const s = secs % 60
  const urgent = secs < 120
  return (
    <span className={`font-bold font-mono text-sm ${urgent ? 'text-red-400 animate-pulse' : 'text-amber-300'}`}>
      {m}m {s}s
    </span>
  )
}
