import React, { useState, useEffect, useRef } from 'react'
import { api } from '../utils/auth'

const ROLE_ACTIONS = {
  police: {
    GENUINE_CRUSH: 'Deploying officers to Choke Point B immediately. Estimated deployment time: 4 minutes.',
    BUILDING: 'Monitoring Choke Point B. On standby for deployment.',
    SELF_RESOLVING: 'Observing situation. Ready to deploy if needed.',
    SAFE: 'All clear. Standard monitoring active.'
  },
  gsrtc: {
    GENUINE_CRUSH: 'Holding all incoming buses at 3km checkpoint. No additional dispatches.',
    BUILDING: 'Slowing incoming buses. Monitoring capacity.',
    SELF_RESOLVING: 'Buses on reduced speed. Monitoring situation.',
    SAFE: 'Normal schedule. No holds required.'
  },
  temple: {
    GENUINE_CRUSH: 'Activating darshan hold at inner gate. Redirecting pilgrims to Queue C.',
    BUILDING: 'Preparing darshan hold. Alerting gate staff.',
    SELF_RESOLVING: 'Monitoring crowd. Prepared to activate hold.',
    SAFE: 'Normal operations. Darshan proceeding.'
  },
  admin: {
    GENUINE_CRUSH: 'Coordinating all agency responses. Monitoring situation.',
    BUILDING: 'Alerting all agencies. Monitoring build-up.',
    SELF_RESOLVING: 'Monitoring self-resolution. Agencies on standby.',
    SAFE: 'All systems normal.'
  }
}

const STATUS_OPTIONS = [
  {
    value: 'ACKNOWLEDGED',
    label: 'Acknowledged',
    desc: 'Received alert, taking action',
    color: '#3B82F6',
    svg: (
      <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
        <circle cx="12" cy="12" r="10"/>
        <path d="M9 12l2 2 4-4"/>
      </svg>
    )
  },
  {
    value: 'IN_PROGRESS',
    label: 'In Progress',
    desc: 'Action underway',
    color: '#F59E0B',
    svg: (
      <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
        <circle cx="12" cy="12" r="10"/>
        <path d="M12 6v6l4 2"/>
      </svg>
    )
  },
  {
    value: 'COMPLETED',
    label: 'Completed',
    desc: 'Action completed, situation managed',
    color: '#22c55e',
    svg: (
      <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
        <path d="M20 6L9 17l-5-5"/>
      </svg>
    )
  },
  {
    value: 'ESCALATED',
    label: 'Escalated',
    desc: 'Escalating to higher authority',
    color: '#EF4444',
    svg: (
      <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
        <path d="M12 19V5M5 12l7-7 7 7"/>
      </svg>
    )
  }
]

export default function AlertReplyModal({ alert, agency, token, onClose, onReplied }) {
  const surgeType = alert?.surge_type || 'GENUINE_CRUSH'
  const defaultAction = ROLE_ACTIONS[agency]?.[surgeType] ||
                        ROLE_ACTIONS[agency]?.['GENUINE_CRUSH'] ||
                        'Taking immediate action.'

  const [actionText, setActionText] = useState(defaultAction)
  const [status, setStatus] = useState('ACKNOWLEDGED')
  const [notes, setNotes] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [submitted, setSubmitted] = useState(false)
  const [error, setError] = useState('')

  // Timer — always starts at 90
  const [timeLeft, setTimeLeft] = useState(90)
  const alertStartRef = useRef(Date.now())

  useEffect(() => {
    // Reset timer when new alert comes in
    setTimeLeft(90)
    alertStartRef.current = Date.now()
  }, [alert?.alert_id])

  useEffect(() => {
    if (submitted) return
    if (timeLeft <= 0) return

    const interval = setInterval(() => {
      setTimeLeft(prev => {
        if (prev <= 1) {
          clearInterval(interval)
          return 0
        }
        return prev - 1
      })
    }, 1000)

    return () => clearInterval(interval)
  }, [submitted, alert?.alert_id])

  const timerColor = timeLeft > 30
    ? '#22c55e'
    : timeLeft > 10
    ? '#F59E0B'
    : '#EF4444'

  const formatTime = (s) => {
    const m = Math.floor(s / 60)
    const sec = s % 60
    return `${m}:${sec.toString().padStart(2, '0')}`
  }

  const ackTimeSeconds = 90 - timeLeft

  async function handleSubmit() {
    if (!actionText.trim()) {
      setError('Please describe the action being taken')
      return
    }

    setSubmitting(true)
    setError('')

    try {
      await api.post('/api/alert/reply', {
        token,
        alert_id: alert.alert_id,
        corridor: alert.corridor,
        action_taken: actionText,
        status,
        notes,
        ack_time_seconds: ackTimeSeconds
      })

      setSubmitted(true)

    } catch (err) {
      console.error('[REPLY] Error:', err)
      setError(err.response?.data?.detail || 'Failed to submit. Check connection.')
      setSubmitting(false)
    }
  }

  // Submitted confirmation screen
  if (submitted) {
    return (
      <div style={{
        background: '#1e293b',
        borderRadius: '16px',
        padding: '2rem',
        width: '100%',
        maxWidth: '520px',
        textAlign: 'center',
        border: '1px solid #334155'
      }}>
        <div style={{
          width: '52px',
          height: '52px',
          background: '#14532d',
          borderRadius: '50%',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          margin: '0 auto 1rem'
        }}>
          <svg width="26" height="26"
               viewBox="0 0 24 24"
               fill="none"
               stroke="#22c55e"
               strokeWidth="2.5">
            <path d="M20 6L9 17l-5-5"/>
          </svg>
        </div>

        <div style={{
          fontSize: '17px',
          fontWeight: '600',
          color: '#f1f5f9',
          marginBottom: '6px'
        }}>
          Reply Submitted
        </div>

        <div style={{
          fontSize: '12px',
          color: '#64748b',
          marginBottom: '1.5rem'
        }}>
          Response logged for alert{' '}
          {alert?.alert_id}
        </div>

        {/* PDF Download button — only on click */}
        <button
          onClick={async () => {
            const base =
              import.meta.env.VITE_API_URL ||
              'http://localhost:8000'
            const url = `${base}/api/report/${alert?.alert_id}`
            try {
              const res = await fetch(url)
              // Check content type — backend may return JSON if PDF not ready yet
              const contentType = res.headers.get('content-type') || ''
              if (contentType.includes('application/pdf')) {
                const blob = await res.blob()
                const blobUrl = URL.createObjectURL(blob)
                const a = document.createElement('a')
                a.href = blobUrl
                a.download = `incident_report_${alert?.alert_id}.pdf`
                document.body.appendChild(a)
                a.click()
                document.body.removeChild(a)
                setTimeout(() => URL.revokeObjectURL(blobUrl), 5000)
              } else {
                // PDF not generated yet — open JSON report in new tab as fallback
                window.open(url, '_blank')
              }
            } catch (e) {
              window.open(url, '_blank')
            }
          }}
          style={{
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            gap: '8px',
            width: '100%',
            padding: '10px',
            background: '#0f172a',
            color: '#60a5fa',
            border: '1px solid #1e3a5f',
            borderRadius: '8px',
            fontSize: '13px',
            fontWeight: '500',
            cursor: 'pointer',
            marginBottom: '10px'
          }}
        >
          <svg width="14" height="14"
               viewBox="0 0 24 24"
               fill="none"
               stroke="currentColor"
               strokeWidth="2">
            <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/>
            <path d="M7 10l5 5 5-5"/>
            <path d="M12 15V3"/>
          </svg>
          Download Incident Report PDF
        </button>

        <button
          onClick={onReplied}
          style={{
            width: '100%',
            padding: '8px',
            background: 'transparent',
            color: '#64748b',
            border: '1px solid #334155',
            borderRadius: '8px',
            fontSize: '13px',
            cursor: 'pointer'
          }}
        >
          Close
        </button>
      </div>
    )
  }

  return (
    <div style={{
      background: '#1e293b',
      borderRadius: '16px',
      padding: '1.5rem',
      width: '100%',
      maxWidth: '540px',
      border: '1px solid #334155',
      maxHeight: '90vh',
      overflowY: 'auto'
    }}>
      {/* Header */}
      <div style={{
        display: 'flex',
        justifyContent: 'space-between',
        alignItems: 'flex-start',
        marginBottom: '1.25rem'
      }}>
        <div>
          <div style={{
            fontSize: '17px',
            fontWeight: '600',
            color: '#f1f5f9',
            marginBottom: '4px'
          }}>
            Alert Response Required
          </div>
          <div style={{
            fontSize: '12px',
            color: '#94a3b8'
          }}>
            {alert?.corridor} · CPI {alert?.cpi?.toFixed(3)} · {surgeType}
          </div>
        </div>

        {/* Timer */}
        <div style={{
          display: 'flex',
          alignItems: 'center',
          gap: '6px',
          color: timerColor,
          fontSize: '15px',
          fontWeight: '600',
          background: '#0f172a',
          padding: '6px 12px',
          borderRadius: '8px',
          border: `1px solid ${timerColor}40`
        }}>
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke={timerColor} strokeWidth="2">
            <circle cx="12" cy="12" r="10"/>
            <path d="M12 6v6l4 2"/>
          </svg>
          {formatTime(timeLeft)}
        </div>
      </div>

      {/* Action text */}
      <div style={{ marginBottom: '1rem' }}>
        <label style={{
          fontSize: '12px',
          color: '#64748b',
          fontWeight: '500',
          textTransform: 'uppercase',
          letterSpacing: '0.06em',
          display: 'block',
          marginBottom: '6px'
        }}>
          Action Being Taken
        </label>
        <textarea
          value={actionText}
          onChange={e => setActionText(e.target.value)}
          rows={3}
          style={{
            width: '100%',
            background: '#0f172a',
            border: '1px solid #334155',
            borderRadius: '8px',
            padding: '10px 12px',
            color: '#f1f5f9',
            fontSize: '13px',
            resize: 'vertical',
            fontFamily: 'system-ui'
          }}
        />
      </div>

      {/* Status options */}
      <div style={{ marginBottom: '1rem' }}>
        <label style={{
          fontSize: '12px',
          color: '#64748b',
          fontWeight: '500',
          textTransform: 'uppercase',
          letterSpacing: '0.06em',
          display: 'block',
          marginBottom: '8px'
        }}>
          Status
        </label>
        <div style={{
          display: 'grid',
          gridTemplateColumns: '1fr 1fr',
          gap: '8px'
        }}>
          {STATUS_OPTIONS.map(opt => (
            <button
              key={opt.value}
              onClick={() => setStatus(opt.value)}
              style={{
                background: status === opt.value
                  ? `${opt.color}18`
                  : '#0f172a',
                border: `1.5px solid ${status === opt.value
                  ? opt.color
                  : '#334155'}`,
                borderRadius: '8px',
                padding: '10px 12px',
                cursor: 'pointer',
                textAlign: 'left',
                display: 'flex',
                alignItems: 'flex-start',
                gap: '8px',
                color: status === opt.value
                  ? opt.color
                  : '#94a3b8',
                transition: 'all 0.15s'
              }}
            >
              <span style={{ marginTop: '1px', flexShrink: 0 }}>
                {opt.svg}
              </span>
              <span>
                <div style={{
                  fontSize: '13px',
                  fontWeight: '500'
                }}>
                  {opt.label}
                </div>
                <div style={{
                  fontSize: '11px',
                  opacity: 0.7,
                  marginTop: '2px'
                }}>
                  {opt.desc}
                </div>
              </span>
            </button>
          ))}
        </div>
      </div>

      {/* Notes */}
      <div style={{ marginBottom: '1.25rem' }}>
        <label style={{
          fontSize: '12px',
          color: '#64748b',
          fontWeight: '500',
          textTransform: 'uppercase',
          letterSpacing: '0.06em',
          display: 'block',
          marginBottom: '6px'
        }}>
          Additional Notes (Optional)
        </label>
        <textarea
          value={notes}
          onChange={e => setNotes(e.target.value)}
          placeholder="Any additional information or context..."
          rows={2}
          style={{
            width: '100%',
            background: '#0f172a',
            border: '1px solid #334155',
            borderRadius: '8px',
            padding: '10px 12px',
            color: '#f1f5f9',
            fontSize: '13px',
            resize: 'vertical',
            fontFamily: 'system-ui'
          }}
        />
      </div>

      {error && (
        <div style={{
          background: '#7f1d1d',
          color: '#fca5a5',
          padding: '8px 12px',
          borderRadius: '6px',
          fontSize: '12px',
          marginBottom: '1rem'
        }}>
          {error}
        </div>
      )}

      {/* Buttons */}
      <div style={{
        display: 'flex',
        gap: '10px',
        justifyContent: 'flex-end'
      }}>
        <button
          onClick={onClose}
          style={{
            background: 'transparent',
            border: '1px solid #334155',
            color: '#94a3b8',
            borderRadius: '8px',
            padding: '10px 20px',
            fontSize: '13px',
            fontWeight: '500',
            cursor: 'pointer'
          }}
        >
          Cancel
        </button>

        <button
          onClick={handleSubmit}
          disabled={submitting}
          style={{
            background: submitting ? '#374151' : '#2563eb',
            border: 'none',
            color: 'white',
            borderRadius: '8px',
            padding: '10px 20px',
            fontSize: '13px',
            fontWeight: '600',
            cursor: submitting ? 'not-allowed' : 'pointer',
            display: 'flex',
            alignItems: 'center',
            gap: '6px'
          }}
        >
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="white" strokeWidth="2">
            <circle cx="12" cy="12" r="10"/>
            <path d="M9 12l2 2 4-4"/>
          </svg>
          {submitting ? 'Submitting...' : 'Submit Reply'}
        </button>
      </div>
    </div>
  )
}