import React, { useState, useEffect } from 'react'
import axios from 'axios'

const API = import.meta.env.VITE_API_URL || 'http://localhost:8000'

const ROLE_COLORS = {
  police: '#3B82F6',
  gsrtc: '#F59E0B',
  temple: '#8B5CF6',
  admin: '#EF4444'
}

const STATUS_COLORS = {
  ACKNOWLEDGED: '#3b82f6',
  IN_PROGRESS: '#f59e0b',
  COMPLETED: '#22c55e',
  ESCALATED: '#ef4444'
}

export default function AdminPanel({ token }) {
  const [stats, setStats] = useState({})
  const [sessions, setSessions] = useState([])
  const [replies, setReplies] = useState([])
  const [reports, setReports] = useState([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    fetchData()
    const interval = setInterval(fetchData, 30000) // Refresh every 30s
    return () => clearInterval(interval)
  }, [token])

  const fetchData = async () => {
    try {
      const [statsRes, sessionsRes, repliesRes, reportsRes] = await Promise.all([
        axios.get(`${API}/api/admin/stats?token=${token}`),
        axios.get(`${API}/api/admin/sessions?token=${token}`),
        axios.get(`${API}/api/admin/replies?token=${token}`),
        axios.get(`${API}/api/reports`)
      ])

      setStats(statsRes.data)
      setSessions(sessionsRes.data)
      setReplies(repliesRes.data)
      setReports(reportsRes.data)
    } catch (error) {
      console.error('Failed to fetch admin data:', error)
    } finally {
      setLoading(false)
    }
  }

  const formatTime = (timestamp) => {
    return new Date(timestamp * 1000).toLocaleString()
  }

  const formatDuration = (seconds) => {
    if (seconds < 60) return `${seconds}s`
    const minutes = Math.floor(seconds / 60)
    const remainingSeconds = seconds % 60
    return `${minutes}m ${remainingSeconds}s`
  }

  if (loading) {
    return (
      <div style={{
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        height: '400px',
        color: '#94a3b8'
      }}>
        <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
          <path d="M21 12a9 9 0 11-6.219-8.56"/>
        </svg>
        <span style={{ marginLeft: '12px' }}>Loading admin data...</span>
      </div>
    )
  }

  return (
    <div style={{ padding: '24px', maxWidth: '1400px', margin: '0 auto' }}>
      {/* System Stats */}
      <div style={{ marginBottom: '32px' }}>
        <h2 style={{
          fontSize: '24px',
          fontWeight: '600',
          color: '#f1f5f9',
          marginBottom: '16px',
          display: 'flex',
          alignItems: 'center',
          gap: '12px'
        }}>
          <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="#ef4444" strokeWidth="1.5">
            <rect x="3" y="4" width="18" height="18" rx="2" ry="2"/>
            <line x1="16" y1="2" x2="16" y2="6"/>
            <line x1="8" y1="2" x2="8" y2="6"/>
            <line x1="3" y1="10" x2="21" y2="10"/>
            <path d="M8 14h.01"/>
            <path d="M12 14h.01"/>
            <path d="M16 14h.01"/>
            <path d="M8 18h.01"/>
            <path d="M12 18h.01"/>
            <path d="M16 18h.01"/>
          </svg>
          System Statistics
        </h2>

        <div style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))',
          gap: '16px'
        }}>
          {[
            { label: 'Total Alerts', value: stats.total_alerts || 0, color: '#ef4444' },
            { label: 'Total Replies', value: stats.total_replies || 0, color: '#22c55e' },
            { label: 'Total Calls', value: stats.total_calls || 0, color: '#3b82f6' },
            { label: 'PDF Reports', value: stats.total_pdf_reports || 0, color: '#f59e0b' }
          ].map(stat => (
            <div key={stat.label} style={{
              background: '#1e293b',
              border: '1px solid #334155',
              borderRadius: '12px',
              padding: '20px'
            }}>
              <div style={{
                fontSize: '32px',
                fontWeight: '700',
                color: stat.color,
                marginBottom: '4px'
              }}>
                {stat.value}
              </div>
              <div style={{
                fontSize: '14px',
                color: '#94a3b8'
              }}>
                {stat.label}
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* Active Sessions */}
      <div style={{ marginBottom: '32px' }}>
        <h3 style={{
          fontSize: '20px',
          fontWeight: '600',
          color: '#f1f5f9',
          marginBottom: '16px',
          display: 'flex',
          alignItems: 'center',
          gap: '12px'
        }}>
          <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="#22c55e" strokeWidth="1.5">
            <path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"/>
            <circle cx="9" cy="7" r="4"/>
            <path d="M23 21v-2a4 4 0 0 0-3-3.87"/>
            <path d="M16 3.13a4 4 0 0 1 0 7.75"/>
          </svg>
          Active Sessions ({sessions.length})
        </h3>

        <div style={{
          background: '#1e293b',
          border: '1px solid #334155',
          borderRadius: '12px',
          overflow: 'hidden'
        }}>
          <div style={{
            display: 'grid',
            gridTemplateColumns: '1fr 100px 200px 150px',
            gap: '16px',
            padding: '16px',
            background: '#0f172a',
            borderBottom: '1px solid #334155',
            fontSize: '12px',
            fontWeight: '500',
            color: '#94a3b8',
            textTransform: 'uppercase'
          }}>
            <div>Name</div>
            <div>Role</div>
            <div>Unit</div>
            <div>Logged In</div>
          </div>

          {sessions.length === 0 ? (
            <div style={{
              padding: '32px',
              textAlign: 'center',
              color: '#64748b'
            }}>
              No active sessions
            </div>
          ) : (
            sessions.map((session, index) => (
              <div key={index} style={{
                display: 'grid',
                gridTemplateColumns: '1fr 100px 200px 150px',
                gap: '16px',
                padding: '16px',
                borderBottom: index < sessions.length - 1 ? '1px solid #334155' : 'none',
                alignItems: 'center'
              }}>
                <div style={{
                  color: '#f1f5f9',
                  fontWeight: '500'
                }}>
                  {session.name}
                </div>
                <div>
                  <span style={{
                    padding: '4px 8px',
                    background: `${ROLE_COLORS[session.role]}20`,
                    color: ROLE_COLORS[session.role],
                    borderRadius: '6px',
                    fontSize: '12px',
                    fontWeight: '500',
                    textTransform: 'capitalize'
                  }}>
                    {session.role}
                  </span>
                </div>
                <div style={{
                  color: '#94a3b8',
                  fontSize: '14px'
                }}>
                  {session.unit_id}
                </div>
                <div style={{
                  color: '#94a3b8',
                  fontSize: '14px'
                }}>
                  {formatTime(session.logged_in_at)}
                </div>
              </div>
            ))
          )}
        </div>
      </div>

      {/* Alert Replies */}
      <div style={{ marginBottom: '32px' }}>
        <h3 style={{
          fontSize: '20px',
          fontWeight: '600',
          color: '#f1f5f9',
          marginBottom: '16px',
          display: 'flex',
          alignItems: 'center',
          gap: '12px'
        }}>
          <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="#3b82f6" strokeWidth="1.5">
            <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/>
          </svg>
          All Alert Replies ({replies.length})
        </h3>

        <div style={{
          background: '#1e293b',
          border: '1px solid #334155',
          borderRadius: '12px',
          overflow: 'hidden'
        }}>
          <div style={{
            display: 'grid',
            gridTemplateColumns: '120px 100px 120px 80px 150px 1fr 100px 80px',
            gap: '12px',
            padding: '16px',
            background: '#0f172a',
            borderBottom: '1px solid #334155',
            fontSize: '12px',
            fontWeight: '500',
            color: '#94a3b8',
            textTransform: 'uppercase'
          }}>
            <div>Time</div>
            <div>Alert ID</div>
            <div>Corridor</div>
            <div>Role</div>
            <div>Unit</div>
            <div>Action Taken</div>
            <div>Status</div>
            <div>Ack Time</div>
          </div>

          {replies.length === 0 ? (
            <div style={{
              padding: '32px',
              textAlign: 'center',
              color: '#64748b'
            }}>
              No replies yet
            </div>
          ) : (
            <div style={{ maxHeight: '400px', overflow: 'auto' }}>
              {replies.map((reply, index) => (
                <div key={reply.id} style={{
                  display: 'grid',
                  gridTemplateColumns: '120px 100px 120px 80px 150px 1fr 100px 80px',
                  gap: '12px',
                  padding: '16px',
                  borderBottom: index < replies.length - 1 ? '1px solid #334155' : 'none',
                  alignItems: 'center',
                  fontSize: '14px'
                }}>
                  <div style={{ color: '#94a3b8' }}>
                    {new Date(reply.replied_at).toLocaleTimeString()}
                  </div>
                  <div style={{
                    color: '#f1f5f9',
                    fontFamily: 'monospace',
                    fontSize: '12px'
                  }}>
                    {reply.alert_id.slice(-8)}
                  </div>
                  <div style={{ color: '#f1f5f9' }}>
                    {reply.corridor}
                  </div>
                  <div>
                    <span style={{
                      padding: '2px 6px',
                      background: `${ROLE_COLORS[reply.role]}20`,
                      color: ROLE_COLORS[reply.role],
                      borderRadius: '4px',
                      fontSize: '11px',
                      fontWeight: '500',
                      textTransform: 'capitalize'
                    }}>
                      {reply.role}
                    </span>
                  </div>
                  <div style={{
                    color: '#94a3b8',
                    fontSize: '12px'
                  }}>
                    {reply.unit_id}
                  </div>
                  <div style={{
                    color: '#f1f5f9',
                    fontSize: '13px',
                    overflow: 'hidden',
                    textOverflow: 'ellipsis',
                    whiteSpace: 'nowrap'
                  }}>
                    {reply.action_taken}
                  </div>
                  <div>
                    <span style={{
                      padding: '2px 6px',
                      background: `${STATUS_COLORS[reply.status]}20`,
                      color: STATUS_COLORS[reply.status],
                      borderRadius: '4px',
                      fontSize: '11px',
                      fontWeight: '500'
                    }}>
                      {reply.status}
                    </span>
                  </div>
                  <div style={{
                    color: '#94a3b8',
                    fontSize: '12px'
                  }}>
                    {formatDuration(reply.ack_time_seconds)}
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>

      {/* PDF Reports */}
      <div>
        <h3 style={{
          fontSize: '20px',
          fontWeight: '600',
          color: '#f1f5f9',
          marginBottom: '16px',
          display: 'flex',
          alignItems: 'center',
          gap: '12px'
        }}>
          <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="#f59e0b" strokeWidth="1.5">
            <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/>
            <polyline points="14,2 14,8 20,8"/>
            <line x1="16" y1="13" x2="8" y2="13"/>
            <line x1="16" y1="17" x2="8" y2="17"/>
            <polyline points="10,9 9,9 8,9"/>
          </svg>
          PDF Reports ({reports.length})
        </h3>

        <div style={{
          background: '#1e293b',
          border: '1px solid #334155',
          borderRadius: '12px',
          overflow: 'hidden'
        }}>
          <div style={{
            display: 'grid',
            gridTemplateColumns: '150px 120px 150px 100px 120px',
            gap: '16px',
            padding: '16px',
            background: '#0f172a',
            borderBottom: '1px solid #334155',
            fontSize: '12px',
            fontWeight: '500',
            color: '#94a3b8',
            textTransform: 'uppercase'
          }}>
            <div>Alert ID</div>
            <div>Corridor</div>
            <div>Created</div>
            <div>Size</div>
            <div>Download</div>
          </div>

          {reports.length === 0 ? (
            <div style={{
              padding: '32px',
              textAlign: 'center',
              color: '#64748b'
            }}>
              No PDF reports generated yet
            </div>
          ) : (
            reports.map((report, index) => (
              <div key={report.alert_id} style={{
                display: 'grid',
                gridTemplateColumns: '150px 120px 150px 100px 120px',
                gap: '16px',
                padding: '16px',
                borderBottom: index < reports.length - 1 ? '1px solid #334155' : 'none',
                alignItems: 'center'
              }}>
                <div style={{
                  color: '#f1f5f9',
                  fontFamily: 'monospace',
                  fontSize: '13px'
                }}>
                  {report.alert_id}
                </div>
                <div style={{ color: '#94a3b8' }}>
                  {report.corridor || 'Unknown'}
                </div>
                <div style={{
                  color: '#94a3b8',
                  fontSize: '14px'
                }}>
                  {new Date(report.created_at).toLocaleString()}
                </div>
                <div style={{
                  color: '#94a3b8',
                  fontSize: '14px'
                }}>
                  {report.size_kb} KB
                </div>
                <div>
                  <button
                    onClick={() => window.open(`${API}${report.url}`, '_blank')}
                    style={{
                      padding: '6px 12px',
                      background: '#3b82f6',
                      color: 'white',
                      border: 'none',
                      borderRadius: '6px',
                      fontSize: '12px',
                      fontWeight: '500',
                      cursor: 'pointer',
                      display: 'flex',
                      alignItems: 'center',
                      gap: '6px'
                    }}
                  >
                    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5">
                      <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/>
                      <polyline points="7,10 12,15 17,10"/>
                      <line x1="12" y1="15" x2="12" y2="3"/>
                    </svg>
                    Download
                  </button>
                </div>
              </div>
            ))
          )}
        </div>
      </div>
    </div>
  )
}