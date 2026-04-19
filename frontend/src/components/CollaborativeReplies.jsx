import React, { useState, useEffect } from 'react'

const API = import.meta.env.VITE_API_URL || 'http://localhost:8000'

const ROLE_COLORS = {
  police: '#3B82F6',
  temple: '#8B5CF6',
  gsrtc:  '#F59E0B',
  admin:  '#EF4444'
}

const ROLE_LABELS = {
  police: 'Police',
  temple: 'Temple Trust',
  gsrtc:  'GSRTC',
  admin:  'Admin'
}

const STATUS_COLORS = {
  ACKNOWLEDGED: '#3B82F6',
  IN_PROGRESS:  '#F59E0B',
  COMPLETED:    '#22c55e',
  ESCALATED:    '#EF4444'
}

const ALL_AGENCIES = ['police', 'temple', 'gsrtc']

function RoleIcon({ role, size = 14 }) {
  const icons = {
    police: (
      <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5">
        <path d="M12 2L3 7v5c0 5.25 3.75 10.15 9 11.25C17.25 22.15 21 17.25 21 12V7L12 2z"/>
      </svg>
    ),
    temple: (
      <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5">
        <path d="M3 22V12L12 3l9 9v10"/>
        <path d="M9 22V16h6v6"/>
      </svg>
    ),
    gsrtc: (
      <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5">
        <rect x="1" y="3" width="15" height="13" rx="2"/>
        <path d="M16 8h4l3 3v4h-7V8z"/>
        <circle cx="5.5" cy="18.5" r="2.5"/>
        <circle cx="18.5" cy="18.5" r="2.5"/>
      </svg>
    ),
    admin: (
      <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5">
        <circle cx="12" cy="8" r="4"/>
        <path d="M12 14c-6 0-8 2-8 4v1h16v-1c0-2-2-4-8-4z"/>
      </svg>
    )
  }
  return icons[role] || null
}

function DownloadPDFButton({ alertId }) {
  const [downloading, setDownloading] = useState(false)

  async function handleDownload() {
    setDownloading(true)
    try {
      const url = `${API}/api/report/${alertId}`
      const a = document.createElement('a')
      a.href = url
      a.download = `incident_report_${alertId}.pdf`
      a.target = '_blank'
      document.body.appendChild(a)
      a.click()
      document.body.removeChild(a)
    } catch (e) {
      console.error('[PDF]', e)
    } finally {
      setTimeout(() => setDownloading(false), 2000)
    }
  }

  return (
    <button
      onClick={handleDownload}
      disabled={downloading}
      style={{
        display: 'flex',
        alignItems: 'center',
        gap: '6px',
        background: downloading ? '#1e293b' : '#0f172a',
        color: downloading ? '#64748b' : '#60a5fa',
        border: '1px solid #1e3a5f',
        borderRadius: '6px',
        padding: '6px 12px',
        fontSize: '12px',
        fontWeight: '500',
        cursor: downloading ? 'not-allowed' : 'pointer'
      }}
    >
      <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
        <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/>
        <path d="M7 10l5 5 5-5"/>
        <path d="M12 15V3"/>
      </svg>
      {downloading ? 'Downloading...' : 'Download Report'}
    </button>
  )
}

// ── Agency View ──────────────────────────────────────────────────────────────
// Simple cards showing status of all 3 agencies
function AgencyView({ replies, currentRole, agenciesReplied, agenciesPending, alertId }) {
  return (
    <div>
      <div style={{
        fontSize: '11px', color: '#64748b', fontWeight: '600',
        textTransform: 'uppercase', letterSpacing: '0.06em', marginBottom: '10px'
      }}>
        Agency Response Status
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: '8px', marginBottom: '14px' }}>
        {ALL_AGENCIES.map(agency => {
          const replied = agenciesReplied.includes(agency)
          const reply = replies.find(r => r.role === agency)
          const color = ROLE_COLORS[agency]
          const isMe = agency === currentRole

          return (
            <div key={agency} style={{
              background: replied ? `${color}10` : '#0f172a',
              border: `1px solid ${isMe ? color : replied ? `${color}50` : '#1e293b'}`,
              borderRadius: '8px',
              padding: '10px'
            }}>
              <div style={{
                display: 'flex', alignItems: 'center', gap: '5px',
                color: replied ? color : '#475569', marginBottom: '5px'
              }}>
                <RoleIcon role={agency} />
                <span style={{ fontSize: '11px', fontWeight: '600' }}>
                  {ROLE_LABELS[agency]}
                  {isMe && (
                    <span style={{ color: '#64748b', fontWeight: '400', marginLeft: '3px' }}>(you)</span>
                  )}
                </span>
              </div>

              {replied && reply ? (
                <>
                  <div style={{ fontSize: '11px', color: STATUS_COLORS[reply.status], fontWeight: '600', marginBottom: '3px' }}>
                    {reply.status}
                  </div>
                  <div style={{ fontSize: '11px', color: '#94a3b8', lineHeight: '1.4' }}>
                    {reply.action_taken.slice(0, 60)}{reply.action_taken.length > 60 ? '...' : ''}
                  </div>
                  <div style={{ fontSize: '10px', color: '#475569', marginTop: '4px' }}>
                    {reply.responder_name}{' · '}{new Date(reply.replied_at).toLocaleTimeString()}
                  </div>
                </>
              ) : (
                <div style={{ fontSize: '11px', color: '#334155' }}>Awaiting response...</div>
              )}
            </div>
          )
        })}
      </div>

      <div style={{ display: 'flex', justifyContent: 'flex-end' }}>
        <DownloadPDFButton alertId={alertId} />
      </div>
    </div>
  )
}

// ── Admin View ───────────────────────────────────────────────────────────────
// Full detailed table + all reply text + download
function AdminView({ replies, agenciesReplied, agenciesPending, alertId, corridor }) {
  return (
    <div>
      {/* Summary cards */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: '8px', marginBottom: '14px' }}>
        {[
          { label: 'Total Replies',  value: replies.length,           color: '#60a5fa' },
          { label: 'Responded',      value: agenciesReplied.length,   color: '#22c55e' },
          { label: 'Pending',        value: agenciesPending.length,   color: agenciesPending.length > 0 ? '#ef4444' : '#22c55e' },
          {
            label: 'Avg Ack Time',
            value: replies.length > 0
              ? `${Math.round(replies.reduce((a, r) => a + (r.ack_time_seconds || 0), 0) / replies.length)}s`
              : '—',
            color: '#f59e0b'
          }
        ].map(card => (
          <div key={card.label} style={{ background: '#0f172a', borderRadius: '8px', padding: '10px', textAlign: 'center' }}>
            <div style={{ fontSize: '18px', fontWeight: '700', color: card.color }}>{card.value}</div>
            <div style={{ fontSize: '10px', color: '#64748b', marginTop: '2px' }}>{card.label}</div>
          </div>
        ))}
      </div>

      {/* Pending warning */}
      {agenciesPending.length > 0 && (
        <div style={{
          background: '#7f1d1d20', border: '1px solid #ef444440', borderRadius: '6px',
          padding: '8px 12px', marginBottom: '12px', fontSize: '12px', color: '#fca5a5',
          display: 'flex', alignItems: 'center', gap: '6px'
        }}>
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="#ef4444" strokeWidth="2">
            <circle cx="12" cy="12" r="10"/>
            <path d="M12 8v4M12 16h.01"/>
          </svg>
          No response yet from: {agenciesPending.map(r => ROLE_LABELS[r]).join(', ')}
        </div>
      )}

      {/* Full reply details */}
      {replies.length === 0 ? (
        <div style={{ textAlign: 'center', padding: '20px', fontSize: '13px', color: '#475569' }}>
          No agency responses yet
        </div>
      ) : (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '8px', marginBottom: '14px' }}>
          {replies.map((reply, i) => {
            const color = ROLE_COLORS[reply.role] || '#94a3b8'
            return (
              <div key={i} style={{
                background: '#0f172a',
                border: `1px solid ${color}30`,
                borderLeft: `3px solid ${color}`,
                borderRadius: '8px',
                padding: '12px 14px'
              }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '8px' }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: '6px', color }}>
                    <RoleIcon role={reply.role} />
                    <span style={{ fontSize: '13px', fontWeight: '600' }}>{reply.responder_name}</span>
                    <span style={{ fontSize: '11px', color: '#64748b', fontWeight: '400' }}>{reply.unit_id}</span>
                  </div>
                  <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                    <span style={{
                      fontSize: '10px', color: STATUS_COLORS[reply.status],
                      background: `${STATUS_COLORS[reply.status]}20`,
                      padding: '2px 8px', borderRadius: '10px', fontWeight: '600'
                    }}>
                      {reply.status}
                    </span>
                    <span style={{ fontSize: '10px', color: '#475569' }}>Ack: {reply.ack_time_seconds}s</span>
                  </div>
                </div>

                <div style={{ fontSize: '12px', color: '#e2e8f0', lineHeight: '1.5', marginBottom: reply.notes ? '6px' : 0 }}>
                  {reply.action_taken}
                </div>

                {reply.notes && (
                  <div style={{
                    fontSize: '11px', color: '#64748b', fontStyle: 'italic',
                    borderTop: '1px solid #1e293b', paddingTop: '6px', marginTop: '6px'
                  }}>
                    Note: {reply.notes}
                  </div>
                )}

                <div style={{ fontSize: '10px', color: '#334155', marginTop: '6px' }}>
                  Replied at {new Date(reply.replied_at).toLocaleTimeString()}
                </div>
              </div>
            )
          })}
        </div>
      )}

      <div style={{ display: 'flex', justifyContent: 'flex-end', borderTop: '1px solid #1e293b', paddingTop: '12px' }}>
        <DownloadPDFButton alertId={alertId} />
      </div>
    </div>
  )
}

// ── Main Component ───────────────────────────────────────────────────────────
export default function CollaborativeReplies({ activeAlertId, corridor, currentRole, repliesUpdate }) {
  const [replies, setReplies] = useState([])
  const [agenciesReplied, setAgenciesReplied] = useState([])
  const [agenciesPending, setAgenciesPending] = useState([...ALL_AGENCIES])
  const [loading, setLoading] = useState(false)

  // Fetch on mount or when alert changes
  useEffect(() => {
    if (!activeAlertId) {
      setReplies([])
      setAgenciesReplied([])
      setAgenciesPending([...ALL_AGENCIES])
      return
    }

    async function fetchReplies() {
      setLoading(true)
      try {
        const res = await fetch(`${API}/api/alert/${activeAlertId}/all-replies`)
        const data = await res.json()
        setReplies(data.all_replies || [])
        setAgenciesReplied(data.agencies_replied || [])
        setAgenciesPending(data.agencies_pending || [...ALL_AGENCIES])
      } catch (e) {
        console.error('[REPLIES FETCH]', e)
      } finally {
        setLoading(false)
      }
    }

    fetchReplies()
  }, [activeAlertId])

  // Real-time update from WebSocket
  useEffect(() => {
    if (!repliesUpdate) return
    if (repliesUpdate.alert_id !== activeAlertId) return
    setReplies(repliesUpdate.all_replies || [])
    setAgenciesReplied(repliesUpdate.agencies_replied || [])
    setAgenciesPending(repliesUpdate.agencies_pending || [])
  }, [repliesUpdate, activeAlertId])

  if (!activeAlertId) return null

  const isAdmin = currentRole === 'admin'
  const allResponded = agenciesPending.length === 0

  return (
    <div style={{
      background: '#1e293b',
      border: '1px solid #334155',
      borderRadius: '12px',
      padding: '1rem 1.25rem',
      marginBottom: '1rem'
    }}>
      {/* Header */}
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '14px' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
          <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="#94a3b8" strokeWidth="1.5">
            <path d="M17 21v-2a4 4 0 00-4-4H5a4 4 0 00-4 4v2"/>
            <circle cx="9" cy="7" r="4"/>
            <path d="M23 21v-2a4 4 0 00-3-3.87M16 3.13a4 4 0 0 1 0 7.75"/>
          </svg>
          <span style={{
            fontSize: '12px', fontWeight: '600', color: '#94a3b8',
            textTransform: 'uppercase', letterSpacing: '0.06em'
          }}>
            {isAdmin ? 'All Agency Responses' : 'Collaborative Response'}
          </span>
        </div>

        <div style={{
          display: 'flex', alignItems: 'center', gap: '5px',
          background: allResponded ? '#14532d' : '#0f172a',
          border: `1px solid ${allResponded ? '#16a34a' : '#334155'}`,
          borderRadius: '20px', padding: '3px 10px',
          fontSize: '11px', fontWeight: '600',
          color: allResponded ? '#86efac' : '#64748b'
        }}>
          {allResponded ? (
            <>
              <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="#86efac" strokeWidth="2.5">
                <path d="M20 6L9 17l-5-5"/>
              </svg>
              All responded
            </>
          ) : (
            `${agenciesReplied.length}/3 responded`
          )}
        </div>
      </div>

      {loading ? (
        <div style={{ textAlign: 'center', padding: '16px', fontSize: '12px', color: '#64748b' }}>
          Loading responses...
        </div>
      ) : isAdmin ? (
        <AdminView
          replies={replies}
          agenciesReplied={agenciesReplied}
          agenciesPending={agenciesPending}
          alertId={activeAlertId}
          corridor={corridor}
        />
      ) : (
        <AgencyView
          replies={replies}
          currentRole={currentRole}
          agenciesReplied={agenciesReplied}
          agenciesPending={agenciesPending}
          alertId={activeAlertId}
        />
      )}
    </div>
  )
}
