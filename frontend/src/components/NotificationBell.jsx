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
        <span className={`text-xl ${hasCritical ? 'animate-bounce' : ''}`}>🔔</span>
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
                  {/* PDF Ready Notification */}
                  {n.type === 'pdf_ready' && (
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
                        📄 Incident Report Ready
                      </div>
                      <div style={{
                        color: '#94a3b8',
                        fontSize: 12,
                        marginBottom: 8
                      }}>
                        {n.corridor} — {n.message}
                      </div>
                      <button
                        onClick={() => window.open(`${API_URL}${n.pdf_url}`, '_blank')}
                        style={{
                          background: '#dc2626',
                          color: 'white',
                          border: 'none',
                          borderRadius: 6,
                          padding: '6px 14px',
                          fontSize: 12,
                          fontWeight: 600,
                          cursor: 'pointer',
                          width: '100%'
                        }}
                      >
                        Open PDF Report →
                      </button>
                    </div>
                  )}
                  
                  {/* Regular Notification */}
                  {n.type !== 'pdf_ready' && (
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
