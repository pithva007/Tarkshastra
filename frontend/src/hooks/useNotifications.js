/**
 * useNotifications — manages in-app and browser push notifications.
 *
 * Listens to WebSocket corridor data and fires notifications when
 * alert_active becomes true. Tracks fired alert IDs to avoid duplicates.
 */
import { useState, useEffect, useRef, useCallback } from 'react'

const MAX_NOTIFICATIONS = 50

/**
 * Build a role-specific notification message.
 */
function buildMessage(role, reading) {
  const { corridor, cpi, surge_type, alert_id, time_to_breach_minutes } = reading
  const ttb = time_to_breach_minutes ? Math.ceil(time_to_breach_minutes) : '?'
  const cpiStr = cpi?.toFixed(2) ?? '?'

  switch (role) {
    case 'driver':
      return `⚠ ALERT: ${corridor} corridor CPI ${cpiStr}. Hold at checkpoint — do NOT proceed to temple. ETA impact: +${ttb} minutes.`
    case 'police':
      return `🚨 URGENT: Crush risk at ${corridor} in ${ttb} minutes. Deploy to Choke Point B immediately. Alert ID: ${alert_id}`
    case 'temple':
      return `🛕 ACTION: Activate darshan hold NOW. CPI: ${cpiStr} — ${surge_type}. Redirect pilgrims to Queue C.`
    case 'gsrtc':
      return `🚌 HOLD BUSES: ${corridor} at capacity. Hold all vehicles at 3km checkpoint. Expected wait: ${ttb} minutes.`
    default:
      return `⚠ ALERT: ${corridor} CPI ${cpiStr} — ${surge_type}`
  }
}

/**
 * Request browser notification permission.
 */
async function requestNotificationPermission() {
  if (!('Notification' in window)) return false
  if (Notification.permission === 'granted') return true
  if (Notification.permission === 'denied') return false
  const result = await Notification.requestPermission()
  return result === 'granted'
}

/**
 * Fire a browser push notification.
 */
function fireBrowserNotification(title, body) {
  if (!('Notification' in window) || Notification.permission !== 'granted') return
  try {
    new Notification(title, {
      body,
      icon: '/favicon.ico',
      badge: '/favicon.ico',
      tag: 'stampede-alert',
      requireInteraction: true,
    })
  } catch {
    // Silently ignore — some browsers block in certain contexts
  }
}

/**
 * @param {object} corridorData  - Live corridor readings from useWebSocket
 * @param {string} agency        - Current user's role/agency
 */
export function useNotifications(corridorData = {}, agency = null) {
  const [notifications, setNotifications] = useState([])
  const [unreadCount, setUnreadCount]     = useState(0)
  const firedAlertIds = useRef(new Set())
  const permissionRequested = useRef(false)

  // Request browser notification permission once
  useEffect(() => {
    if (!permissionRequested.current && agency) {
      permissionRequested.current = true
      requestNotificationPermission()
    }
  }, [agency])

  // Watch for new alerts in corridor data
  useEffect(() => {
    Object.values(corridorData).forEach((reading) => {
      if (!reading?.alert_active || !reading?.alert_id) return
      if (firedAlertIds.current.has(reading.alert_id)) return

      firedAlertIds.current.add(reading.alert_id)

      const message = buildMessage(agency, reading)
      const isCritical = reading.surge_type === 'GENUINE_CRUSH'

      const notification = {
        id:        reading.alert_id + '_' + Date.now(),
        alert_id:  reading.alert_id,
        corridor:  reading.corridor,
        cpi:       reading.cpi,
        surge_type: reading.surge_type,
        message,
        timestamp: new Date().toISOString(),
        read:      false,
        critical:  isCritical,
      }

      setNotifications((prev) => [notification, ...prev].slice(0, MAX_NOTIFICATIONS))
      setUnreadCount((c) => c + 1)

      // Browser push notification
      const title = isCritical
        ? `🚨 CRITICAL: ${reading.corridor}`
        : `⚠ ALERT: ${reading.corridor}`
      fireBrowserNotification(title, message)
    })
  }, [corridorData, agency])

  const markRead = useCallback((notifId) => {
    setNotifications((prev) =>
      prev.map((n) => n.id === notifId ? { ...n, read: true } : n)
    )
    setUnreadCount((c) => Math.max(0, c - 1))
  }, [])

  const markAllRead = useCallback(() => {
    setNotifications((prev) => prev.map((n) => ({ ...n, read: true })))
    setUnreadCount(0)
  }, [])

  const clearAll = useCallback(() => {
    setNotifications([])
    setUnreadCount(0)
  }, [])

  return {
    notifications,
    unreadCount,
    markRead,
    markAllRead,
    clearAll,
  }
}
