import React, { useState, useEffect } from 'react'
import axios from 'axios'

const API = import.meta.env.VITE_API_URL || 'http://localhost:8000'

const ACTION_TEMPLATES = {
  police: {
    GENUINE_CRUSH: "Deploying officers to Choke Point B immediately. Estimated deployment time: 4 minutes.",
    BUILDING: "Monitoring Choke Point B. On standby for deployment."
  },
  gsrtc: {
    GENUINE_CRUSH: "Holding all incoming buses at 3km checkpoint. 8 buses held. No additional dispatches.",
    BUILDING: "Slowing incoming buses. Monitoring capacity."
  },
  temple: {
    GENUINE_CRUSH: "Activating darshan hold at inner gate. Redirecting pilgrims to Queue C.",
    BUILDING: "Preparing darshan hold. Alerting gate staff."
  }
}

const STATUS_OPTIONS = [
  {
    value: 'ACKNOWLEDGED',
    label: 'Acknowledged',
    description: 'Received alert, taking action',
    color: '#3b82f6',
    svg: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
      <path d="M9 12l2 2 4-4"/>
      <circle cx="12" cy="12" r="9"/>
    </svg>`
  },
  {
    value: 'IN_PROGRESS',
    label: 'In Progress',
    description: 'Action underway',
    color: '#f59e0b',
    svg: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
      <circle cx="12" cy="12" r="10"/>
      <polyline points="12,6 12,12 16,14"/>
    </svg>`
  },
  {
    value: 'COMPLETED',
    label: 'Completed',
    description: 'Action completed, situation managed',
    color: '#22c55e',
    svg: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
      <path d="M9 12l2 2 4-4"/>
      <path d="M21 12c0 4.97-4.03 9-9 9s-9-4.03-9-9 4.03-9 9-9c2.35 0 4.48.9 6.08 2.38"/>
      <path d="M17 6l-3 3"/>
    </svg>`
  },
  {
    value: 'ESCALATED',
    label: 'Escalated',
    description: 'Escalating to higher authority',
    color: '#ef4444',
    svg: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
      <line x1="12" y1="19" x2="12" y2="5"/>
      <polyline points="5,12 12,5 19,12"/>
    </svg>`
  }
]

export default function AlertReplyModal({ alert, agency, token, onClose, onReplied }) {
  const [actionTaken, setActionTaken] = useState('')
  const [status, setStatus] = useState('ACKNOWLEDGED')
  const [notes, setNotes] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [submitted, setSubmitted] = useState(false)
  const [submitTime, setSubmitTime] = useState('')
  const [ackTime, setAckTime] = useState(0)

  useEffect(() => {
    if (alert && agency) {
      // Pre-fill action based on role and surge type
      const template = ACTION_TEMPLATES[agency.role]?.[alert.surge_type] || 
                      `Responding to ${alert.corridor} alert. Taking appropriate action.`
      setActionTaken(template)
    }

    // Start acknowledgment timer
    const startTime = Date.now()
    const timer = setInterval(() => {
      setAckTime(Math.floor((Date.now() - startTime) / 1000))
    }, 1000)

    return () => clearInterval(timer)
  }, [alert, agency])

  const handleSubmit = async (e) => {
    e.preventDefault()
    if (!actionTaken.trim() || submitting) return

    setSubmitting(true)

    try {
      await axios.post(`${API}/api/alert/reply`, {
        token,
        alert_id: alert.alert_id,
        corridor: alert.corridor,
        action_taken: actionTaken,
        status,
        notes: notes.trim(),
        ack_time_seconds: ackTime
      })

      const now = new Date()
      setSubmitTime(now.toLocaleTimeString())
      setSubmitted(true)
      
      if (onReplied) {
        onReplied(alert.alert_id)
      }
    } catch (error) {
      console.error('Failed to submit reply:', error)
      alert('Failed to submit reply. Please try again.')
    } finally {
      setSubmitting(false)
    }
  }

  const handleViewPDF = () => {
    window.open(`${API}/api/report/${alert.alert_id}`, '_blank')
  }

  const selectedStatus = STATUS_OPTIONS.find(s => s.value === status)

  if (submitted) {
    return (
      <div style={{
        position: 'fixed',
        inset: 0,
        background: 'rgba(0, 0, 0, 0.8)',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        zIndex: 1000,
        backdropFilter: 'blur(4px)'
      }}>
        <div style={{
          background: '#1e293b',
          border: '1px solid #334155',
          borderRadius: '16px',
          padding: '32px',
          maxWidth: '400px',
          width: '90%',
          textAlign: 'center'
        }}>
          <div style={{
            width: '64px',
            height: '64px',
            background: '#22c55e',
            borderRadius: '50%',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            margin: '0 auto 24px'
          }}>
            <svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="white" strokeWidth="2">
              <path d="M9 12l2 2 4-4"/>
              <circle cx="12" cy="12" r="9"/>
            </svg>
          </div>

          <h3 style={{
            fontSize: '20px',
            fontWeight: '600',
            color: '#f1f5f9',
            marginBottom: '8px'
          }}>
            Reply Submitted
          </h3>

          <p style={{
            color: '#94a3b8',
            marginBottom: '24px',
            fontSize: '14px'
          }}>
            Reply submitted at {submitTime}
          </p>

          <div style={{
            display: 'flex',
            gap: '12px',
            justifyContent: 'center'
          }}>
            <button
              onClick={handleViewPDF}
              style={{
                padding: '10px 20px',
                background: '#3b82f6',
                color: 'white',
                border: 'none',
                borderRadius: '8px',
                fontSize: '14px',
                fontWeight: '500',
                cursor: 'pointer',
                display: 'flex',
                alignItems: 'center',
                gap: '8px'
              }}
            >
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5">
                <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/>
                <polyline points="14,2 14,8 20,8"/>
                <line x1="16" y1="13" x2="8" y2="13"/>
                <line x1="16" y1="17" x2="8" y2="17"/>
                <polyline points="10,9 9,9 8,9"/>
              </svg>
              View PDF Report
            </button>

            <button
              onClick={onClose}
              style={{
                padding: '10px 20px',
                background: '#374151',
                color: '#f1f5f9',
                border: 'none',
                borderRadius: '8px',
                fontSize: '14px',
                fontWeight: '500',
                cursor: 'pointer'
              }}
            >
              Close
            </button>
          </div>
        </div>
      </div>
    )
  }

  return (
    <div style={{
      position: 'fixed',
      inset: 0,
      background: 'rgba(0, 0, 0, 0.8)',
      display: 'flex',
      alignItems: 'center',
      justifyContent: 'center',
      zIndex: 1000,
      backdropFilter: 'blur(4px)'
    }}>
      <div style={{
        background: '#1e293b',
        border: '1px solid #334155',
        borderRadius: '16px',
        padding: '24px',
        maxWidth: '600px',
        width: '90%',
        maxHeight: '90vh',
        overflow: 'auto'
      }}>
        {/* Header */}
        <div style={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          marginBottom: '24px',
          paddingBottom: '16px',
          borderBottom: '1px solid #334155'
        }}>
          <div>
            <h2 style={{
              fontSize: '20px',
              fontWeight: '600',
              color: '#f1f5f9',
              marginBottom: '4px'
            }}>
              Alert Response Required
            </h2>
            <p style={{
              color: '#94a3b8',
              fontSize: '14px'
            }}>
              {alert.corridor} • CPI {alert.cpi?.toFixed(3)} • {alert.surge_type}
            </p>
          </div>
          
          <div style={{
            display: 'flex',
            alignItems: 'center',
            gap: '12px',
            color: '#94a3b8',
            fontSize: '14px'
          }}>
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5">
              <circle cx="12" cy="12" r="10"/>
              <polyline points="12,6 12,12 16,14"/>
            </svg>
            {Math.floor(ackTime / 60)}:{(ackTime % 60).toString().padStart(2, '0')}
          </div>
        </div>

        <form onSubmit={handleSubmit}>
          {/* Action Taken */}
          <div style={{ marginBottom: '20px' }}>
            <label style={{
              display: 'block',
              fontSize: '14px',
              fontWeight: '500',
              color: '#f1f5f9',
              marginBottom: '8px'
            }}>
              Action Being Taken
            </label>
            <textarea
              value={actionTaken}
              onChange={(e) => setActionTaken(e.target.value)}
              rows={3}
              style={{
                width: '100%',
                padding: '12px',
                background: '#0f172a',
                border: '1px solid #334155',
                borderRadius: '8px',
                color: '#f1f5f9',
                fontSize: '14px',
                resize: 'vertical',
                outline: 'none'
              }}
              placeholder="Describe the action you are taking in response to this alert..."
              required
            />
          </div>

          {/* Status Selection */}
          <div style={{ marginBottom: '20px' }}>
            <label style={{
              display: 'block',
              fontSize: '14px',
              fontWeight: '500',
              color: '#f1f5f9',
              marginBottom: '12px'
            }}>
              Status
            </label>
            <div style={{
              display: 'grid',
              gridTemplateColumns: 'repeat(auto-fit, minmax(140px, 1fr))',
              gap: '8px'
            }}>
              {STATUS_OPTIONS.map(option => (
                <label
                  key={option.value}
                  style={{
                    display: 'flex',
                    alignItems: 'center',
                    gap: '8px',
                    padding: '12px',
                    background: status === option.value ? `${option.color}20` : '#0f172a',
                    border: `1px solid ${status === option.value ? option.color : '#334155'}`,
                    borderRadius: '8px',
                    cursor: 'pointer',
                    transition: 'all 0.2s ease'
                  }}
                >
                  <input
                    type="radio"
                    name="status"
                    value={option.value}
                    checked={status === option.value}
                    onChange={(e) => setStatus(e.target.value)}
                    style={{ display: 'none' }}
                  />
                  <div 
                    style={{ 
                      width: '16px', 
                      height: '16px', 
                      color: option.color,
                      flexShrink: 0
                    }}
                    dangerouslySetInnerHTML={{ __html: option.svg }}
                  />
                  <div>
                    <div style={{
                      fontSize: '12px',
                      fontWeight: '500',
                      color: '#f1f5f9'
                    }}>
                      {option.label}
                    </div>
                    <div style={{
                      fontSize: '10px',
                      color: '#94a3b8'
                    }}>
                      {option.description}
                    </div>
                  </div>
                </label>
              ))}
            </div>
          </div>

          {/* Notes */}
          <div style={{ marginBottom: '24px' }}>
            <label style={{
              display: 'block',
              fontSize: '14px',
              fontWeight: '500',
              color: '#f1f5f9',
              marginBottom: '8px'
            }}>
              Additional Notes (Optional)
            </label>
            <textarea
              value={notes}
              onChange={(e) => setNotes(e.target.value)}
              rows={2}
              style={{
                width: '100%',
                padding: '12px',
                background: '#0f172a',
                border: '1px solid #334155',
                borderRadius: '8px',
                color: '#f1f5f9',
                fontSize: '14px',
                resize: 'vertical',
                outline: 'none'
              }}
              placeholder="Any additional information or context..."
            />
          </div>

          {/* Submit Button */}
          <div style={{
            display: 'flex',
            gap: '12px',
            justifyContent: 'flex-end'
          }}>
            <button
              type="button"
              onClick={onClose}
              disabled={submitting}
              style={{
                padding: '12px 24px',
                background: '#374151',
                color: '#f1f5f9',
                border: 'none',
                borderRadius: '8px',
                fontSize: '14px',
                fontWeight: '500',
                cursor: submitting ? 'not-allowed' : 'pointer',
                opacity: submitting ? 0.5 : 1
              }}
            >
              Cancel
            </button>
            
            <button
              type="submit"
              disabled={submitting || !actionTaken.trim()}
              style={{
                padding: '12px 24px',
                background: submitting || !actionTaken.trim() ? '#64748b' : selectedStatus?.color || '#3b82f6',
                color: 'white',
                border: 'none',
                borderRadius: '8px',
                fontSize: '14px',
                fontWeight: '500',
                cursor: submitting || !actionTaken.trim() ? 'not-allowed' : 'pointer',
                display: 'flex',
                alignItems: 'center',
                gap: '8px'
              }}
            >
              {submitting ? (
                <>
                  <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                    <path d="M21 12a9 9 0 11-6.219-8.56"/>
                  </svg>
                  Submitting...
                </>
              ) : (
                <>
                  <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5">
                    <path d="M9 12l2 2 4-4"/>
                    <circle cx="12" cy="12" r="9"/>
                  </svg>
                  Submit Reply
                </>
              )}
            </button>
          </div>
        </form>
      </div>
    </div>
  )
}