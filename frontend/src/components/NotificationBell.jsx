import { useState, useRef, useEffect } from 'react'

const API_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000'

/**
 * NotificationBell — bell icon with badge + dropdown list of notifications.
 * Now supports PDF notifications with "Open Report" button.
 *
 * Props:
 *   notifications  — array from useNotifications hook
 *   unreadCount    — number of unread notifications
 *   onMarkRead     — fn(id) to mark a single notification read
 *   onMarkAllRead  — fn() to mark all read
 */
export default function NotificationBell({
  notifications = [],
  unreadCount = 0,
  onMarkRead,
  onMarkAllRead,
}) {
  const [open, setOpen] = useState(false)
  const ref = useRef(null)

  // Close dropdown when clicking outside
  useEffect(() => {
    function handleClick(e) {
      if (ref.current && !ref.current.contains(e.target)) {
        setOpen(false)
      }
    }
    document.addEventListener('mousedown', handleClick)
    return () => document.removeEventListener('mousedown', handleClick)
  }, [])

  const hasCritical = notifications.some((n) => !n.read && n.critical)

  return (
    <div className="relative" ref={ref}>
      {/* Bell button */}
      <button
        onClick={() => setOpen((o) => !o)}
        className="relative p-2 rounded-lg hover:bg-gray-800 transition-colors"
        aria-label="Notifications"
      >
        <span className={`${hasCritical ? 'animate-bounce' : ''}`}>
          <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <path d="M18 8A6 6 0 0 0 6 8c0 7-3 9-3 9h18s-3-2-3-9"/>
            <path d="M13.73 21a2 2 0 0 1-3.46 0"/>
          </svg>
        </span>
        {unreadCount > 0 && (
          <span className={`absolute -top-0.5 -right-0.5 min-w-[18px] h-[18px] rounded-full text-[10px] font-bold flex items-center justify-center px-1 ${
            hasCritical ? 'bg-red-600 animate-pulse' : 'bg-amber-500'
          } text-white`}>
            {unreadCount > 9 ? '9+' : unreadCount}
          </span>
        )}
      </button>

      {/* Dropdown */}
      {open && (
        <div className="absolute right-0 top-full mt-2 w-80 bg-gray-900 border border-gray-700 rounded-xl shadow-2xl z-50 overflow-hidden">
          {/* Header */}
          <div className="flex items-center justify-between px-4 py-3 border-b border-gray-700">
            <span className="text-sm font-bold text-white">Notifications</span>
            {unreadCount > 0 && (
              <button
                onClick={() => { onMarkAllRead?.(); }}
                className="text-xs text-amber-400 hover:text-amber-300 transition-colors"
              >
                Mark all read
              </button>
            )}
          </div>

          {/* List */}
          <div className="max-h-80 overflow-y-auto">
            {notifications.length === 0 ? (
              <div className="px-4 py-6 text-center text-gray-500 text-sm">
                No notifications yet
              </div>
            ) : (
              notifications.slice(0, 10).map((n) => (
                <div key={n.id}>
                  {/* PDF Ready or Call Update Notification */}
                  {(n.type === 'pdf_ready' || n.type === 'call_update') && n.pdf_url && (
                    <div style={{
                      background: '#1e293b',
                      border: '1px solid #ef4444',
                      borderRadius: 8,
                      padding: '12px',
                      margin: '8px',
                      marginBottom: 8
                    }}>
                      <div style={{
                        color: '#ef4444',
                        fontWeight: 600,
                        fontSize: 13,
                        marginBottom: 6
                      }}>
                        {n.type === 'pdf_ready' ? (
                          <span className="flex items-center gap-1.5">
                            <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/><line x1="16" y1="13" x2="8" y2="13"/><line x1="16" y1="17" x2="8" y2="17"/><polyline points="10 9 9 9 8 9"/></svg>
                            Incident Report Ready
                          </span>
                        ) : (
                          <span className="flex items-center gap-1.5">
                            <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M22 16.92v3a2 2 0 0 1-2.18 2 19.79 19.79 0 0 1-8.63-3.07A19.5 19.5 0 0 1 4.69 13.5a19.79 19.79 0 0 1-3.07-8.67A2 2 0 0 1 3.44 2.68h3a2 2 0 0 1 2 1.72c.127.96.361 1.903.7 2.81a2 2 0 0 1-.45 2.11L7.91 10.09a16 16 0 0 0 6 6l1.27-1.27a2 2 0 0 1 2.11-.45c.907.339 1.85.573 2.81.7A2 2 0 0 1 22 16.92z"/></svg>
                            Calls Made
                          </span>
                        )}
                      </div>
                      <div style={{
                        color: '#94a3b8',
                        fontSize: 12,
                        marginBottom: 8
                      }}>
                        {n.corridor} — {n.message}
                      </div>
                      <button
                        onClick={() => {
                          const base = import.meta.env.VITE_API_URL || 'http://localhost:8000'
                          window.open(`${base}${n.pdf_url}`, '_blank')
                          onMarkRead?.(n.id)
                        }}
                        style={{
                          display: 'flex',
                          alignItems: 'center',
                          gap: '6px',
                          background: '#1e3a5f',
                          color: '#60a5fa',
                          border: '1px solid #3B82F6',
                          borderRadius: '6px',
                          padding: '5px 10px',
                          fontSize: '11px',
                          fontWeight: '600',
                          cursor: 'pointer',
                          width: '100%',
                          justifyContent: 'center'
                        }}
                      >
                        <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                          <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/>
                          <path d="M14 2v6h6M16 13H8M16 17H8M10 9H8"/>
                        </svg>
                        Open Incident Report PDF
                      </button>
                    </div>
                  )}

                  {/* Alert Resolved Notification */}
                  {n.type === 'alert_resolved' && (
                    <div style={{
                      background: '#1e293b',
                      border: '1px solid #22c55e',
                      borderRadius: 8,
                      padding: '12px',
                      margin: '8px',
                      marginBottom: 8
                    }}>
                      <div style={{
                        display: 'flex',
                        alignItems: 'center',
                        gap: '8px',
                        color: '#22c55e',
                        fontWeight: 600,
                        fontSize: 13,
                        marginBottom: 6
                      }}>
                        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5">
                          <path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"/>
                          <polyline points="22 4 12 14.01 9 11.01"/>
                        </svg>
                        Alert Resolved
                      </div>
                      <div style={{
                        color: '#94a3b8',
                        fontSize: 12
                      }}>
                        {n.corridor} — {n.message}
                      </div>
                    </div>
                  )}
                  
                  {/* Regular Notification */}
                  {n.type !== 'pdf_ready' && n.type !== 'call_update' && n.type !== 'alert_resolved' && (
                    <button
                      onClick={() => { onMarkRead?.(n.id); }}
                      className={`w-full text-left px-4 py-3 border-b border-gray-800 hover:bg-gray-800 transition-colors ${
                        !n.read ? 'bg-gray-800/60' : ''
                      }`}
                    >
                      <div className="flex items-start gap-2">
                        {!n.read && (
                          <span className={`mt-1 w-2 h-2 rounded-full flex-shrink-0 ${
                            n.critical ? 'bg-red-500' : 'bg-amber-400'
                          }`} />
                        )}
                        <div className={!n.read ? '' : 'ml-4'}>
                          <p className="text-xs text-white leading-snug">{n.message}</p>
                          <p className="text-xs text-gray-500 mt-1">
                            {n.corridor} · {new Date(n.timestamp).toLocaleTimeString()}
                          </p>
                        </div>
                      </div>
                    </button>
                  )}
                </div>
              ))
            )}
          </div>

          {notifications.length > 10 && (
            <div className="px-4 py-2 text-center text-xs text-gray-500 border-t border-gray-700">
              +{notifications.length - 10} older notifications
            </div>
          )}
        </div>
      )}
    </div>
  )
}
