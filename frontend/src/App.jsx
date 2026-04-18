import React, { useState, useEffect, useRef } from 'react'
import { api } from './utils/auth'

import { useWebSocket } from './hooks/useWebSocket'
import { useNotifications } from './hooks/useNotifications'

import PressureGauge from './components/PressureGauge'
import AgencyPanel from './components/AgencyPanel'
import AlertBanner from './components/AlertBanner'
import ReplayMode from './components/ReplayMode'
import CorridorMap from './components/CorridorMap'
import EventLog from './components/EventLog'
import WhatIfSimulator from './components/WhatIfSimulator'
import CorridorCompare from './components/CorridorCompare'
import NotificationBell from './components/NotificationBell'
import HistoricalPanel from './components/HistoricalPanel'
import AlertReplyModal from './components/AlertReplyModal'
import AdminPanel from './components/AdminPanel'
import PDFViewer from './components/PDFViewer'

const ROLE_COLORS = {
  police: '#3B82F6',
  gsrtc: '#F59E0B',
  temple: '#8B5CF6',
  admin: '#EF4444'
}

const ROLE_TABS = {
  police: ['Dashboard', 'Compare', 'Map', 'History', 'Alerts', 'Events'],
  gsrtc: ['Dashboard', 'Compare', 'Map', 'Buses', 'Alerts', 'Events'],
  temple: ['Dashboard', 'Compare', 'Map', 'History', 'Alerts', 'Events'],
  admin: ['Dashboard', 'Compare', 'Map', 'History', 'Replay', 'Alerts', 'Events', 'Admin']
}

export default function App() {
  // ── Get auth data ─────────────────────────────
  const token = localStorage.getItem('ts11_token')
  const role = localStorage.getItem('ts11_role')
  const userRaw = localStorage.getItem('ts11_user')
  
  let user = null
  try {
    user = userRaw ? JSON.parse(userRaw) : null
  } catch {
    user = null
  }

  // Read agency from URL
  const params = new URLSearchParams(window.location.search)

  // Use role from localStorage (more reliable than URL param)
  const activeRole = role || 'police'

  // Track alert IDs that have been dismissed or replied
  // Using ref so it persists without causing re-renders
  const dismissedAlerts = useRef(new Set())
  const repliedAlerts = useRef(new Set())

  // Current active modal state
  const [activeAlert, setActiveAlert] = useState(null)
  const [showAlertModal, setShowAlertModal] = useState(false)

  const [activeTab, setActiveTab] = useState('Dashboard')
  const [selectedCorridor, setSelectedCorridor] = useState('Ambaji')
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false)
  const [pdfViewer, setPdfViewer] = useState(null)

  const { corridorData, connectionStatus, busData } = useWebSocket()
  const { notifications, unreadCount, markRead, markAllRead } = useNotifications(corridorData, activeRole)

  // Handle alert reply requirement
  useEffect(() => {
    // Watch for new alerts from WebSocket data
    const checkForAlerts = () => {
      if (!corridorData) return

      Object.values(corridorData).forEach(data => {
        if (!data?.alert_active || !data?.alert_id) return

        const alertId = data.alert_id

        // Skip if already dismissed or replied
        if (dismissedAlerts.current.has(alertId)) return
        if (repliedAlerts.current.has(alertId)) return

        // Skip if modal already showing this exact alert
        if (activeAlert?.alert_id === alertId) return

        // This is a NEW alert — show modal
        console.log('[ALERT] New alert detected:', alertId)
        setActiveAlert({
          alert_id: alertId,
          corridor: data.corridor,
          cpi: data.cpi,
          surge_type: data.surge_type,
          time_to_breach_minutes: data.time_to_breach_minutes,
          ml_confidence: data.ml_confidence,
          flow_rate: data.flow_rate
        })
        setShowAlertModal(true)
      })
    }

    checkForAlerts()
  }, [corridorData, activeAlert])  // Only runs when corridorData changes

  // Handle PDF ready notifications
  useEffect(() => {
    notifications.forEach(notification => {
      if (notification.type === 'pdf_ready' && !notification.read) {
        // Auto-mark as read and show banner
        markRead(notification.id)
      }
    })
  }, [notifications, markRead])

  // Handle Cancel — dismiss this alert_id permanently for this browser session
  function handleAlertCancel() {
    if (activeAlert?.alert_id) {
      dismissedAlerts.current.add(activeAlert.alert_id)
      console.log('[ALERT] Dismissed:', activeAlert.alert_id)
    }
    setShowAlertModal(false)
    setActiveAlert(null)
  }

  // Handle Submit — mark as replied
  function handleAlertReplied() {
    if (activeAlert?.alert_id) {
      repliedAlerts.current.add(activeAlert.alert_id)
      dismissedAlerts.current.add(activeAlert.alert_id)
      console.log('[ALERT] Replied:', activeAlert.alert_id)
    }
    setShowAlertModal(false)
    setActiveAlert(null)
    // Show PDF viewer after reply
    if (activeAlert?.alert_id) {
      setPdfViewer(activeAlert.alert_id)
    }
  }

  const handleLogout = () => {
    if (token) {
      api.post('/api/logout', { token }).catch(() => {})
    }
    localStorage.removeItem('ts11_token')
    localStorage.removeItem('ts11_role')
    localStorage.removeItem('ts11_user')
    setShowAlertModal(false)
    setActiveAlert(null)
    setPdfViewer(null)
    window.location.href = '/'
  }

  const getConnectionStatusColor = () => {
    switch (connectionStatus) {
      case 'connected': return '#22c55e'
      case 'connecting': return '#f59e0b'
      default: return '#ef4444'
    }
  }

  const getConnectionStatusText = () => {
    switch (connectionStatus) {
      case 'connected': return 'Live'
      case 'connecting': return 'Reconnecting...'
      default: return 'Disconnected'
    }
  }

  const userTabs = ROLE_TABS[activeRole] || ROLE_TABS.police
  const accentColor = ROLE_COLORS[activeRole] || ROLE_COLORS.police

  return (
    <div style={{
      minHeight: '100vh',
      background: '#0f172a',
      color: '#f1f5f9'
    }}>
      {/* Alert Banner */}
      <AlertBanner readings={Object.values(corridorData)} />

      {/* Navigation Header */}
      <header style={{
        background: '#1e293b',
        borderBottom: `2px solid ${accentColor}`,
        position: 'sticky',
        top: 0,
        zIndex: 40
      }}>
        <div style={{
          maxWidth: '1400px',
          margin: '0 auto',
          padding: '0 16px',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          height: '64px'
        }}>
          {/* Logo & Title */}
          <div style={{
            display: 'flex',
            alignItems: 'center',
            gap: '16px'
          }}>
            <div>
              <h1 style={{
                fontSize: '18px',
                fontWeight: '700',
                color: '#f1f5f9',
                margin: 0
              }}>
                Stampede Window Predictor
              </h1>
              <p style={{
                fontSize: '12px',
                color: '#94a3b8',
                margin: 0
              }}>
                Gujarat Pilgrimage Corridors
              </p>
            </div>
          </div>

          {/* Right Side Controls */}
          <div style={{
            display: 'flex',
            alignItems: 'center',
            gap: '16px'
          }}>
            {/* Role Badge */}
            <div style={{
              padding: '6px 12px',
              background: `${accentColor}20`,
              color: accentColor,
              borderRadius: '20px',
              fontSize: '12px',
              fontWeight: '600',
              textTransform: 'capitalize',
              border: `1px solid ${accentColor}40`
            }}>
              {activeRole}
            </div>

            {/* User Name */}
            <span style={{
              fontSize: '14px',
              color: '#94a3b8'
            }}>
              {user?.name || 'User'}
            </span>

            {/* Connection Status */}
            <div style={{
              display: 'flex',
              alignItems: 'center',
              gap: '8px',
              fontSize: '12px',
              color: '#94a3b8'
            }}>
              <div style={{
                width: '8px',
                height: '8px',
                borderRadius: '50%',
                background: getConnectionStatusColor()
              }} />
              {getConnectionStatusText()}
            </div>

            {/* Notification Bell */}
            <NotificationBell
              notifications={notifications}
              unreadCount={unreadCount}
              onMarkRead={markRead}
              onMarkAllRead={markAllRead}
              onPDFClick={(alertId) => setPdfViewer(alertId)}
            />

            {/* Mobile Menu Button */}
            <button
              onClick={() => setMobileMenuOpen(!mobileMenuOpen)}
              style={{
                display: 'none',
                padding: '8px',
                background: 'transparent',
                border: 'none',
                color: '#94a3b8',
                cursor: 'pointer'
              }}
            >
              <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5">
                <line x1="3" y1="6" x2="21" y2="6"/>
                <line x1="3" y1="12" x2="21" y2="12"/>
                <line x1="3" y1="18" x2="21" y2="18"/>
              </svg>
            </button>

            {/* Logout Button */}
            <button
              onClick={handleLogout}
              style={{
                padding: '8px 16px',
                background: '#374151',
                color: '#f1f5f9',
                border: 'none',
                borderRadius: '8px',
                fontSize: '14px',
                cursor: 'pointer',
                display: 'flex',
                alignItems: 'center',
                gap: '8px'
              }}
            >
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5">
                <path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4"/>
                <polyline points="16,17 21,12 16,7"/>
                <line x1="21" y1="12" x2="9" y2="12"/>
              </svg>
              Logout
            </button>
          </div>
        </div>

        {/* Tab Navigation */}
        <div style={{
          maxWidth: '1400px',
          margin: '0 auto',
          padding: '0 16px',
          display: 'flex',
          overflowX: 'auto'
        }}>
          {userTabs.map(tab => (
            <button
              key={tab}
              onClick={() => setActiveTab(tab)}
              style={{
                padding: '12px 20px',
                background: 'transparent',
                border: 'none',
                color: activeTab === tab ? accentColor : '#94a3b8',
                fontSize: '14px',
                fontWeight: '500',
                cursor: 'pointer',
                borderBottom: `2px solid ${activeTab === tab ? accentColor : 'transparent'}`,
                whiteSpace: 'nowrap',
                transition: 'all 0.2s ease'
              }}
            >
              {tab}
            </button>
          ))}
        </div>
      </header>

      {/* Main Content */}
      <main style={{
        maxWidth: '1400px',
        margin: '0 auto',
        padding: '24px 16px'
      }}>
        {/* Corridor Selector (except for Events, Compare, Admin) */}
        {!['Events', 'Compare', 'Admin'].includes(activeTab) && (
          <div style={{
            display: 'flex',
            gap: '12px',
            marginBottom: '24px',
            flexWrap: 'wrap'
          }}>
            {['Ambaji', 'Dwarka', 'Somnath', 'Pavagadh'].map(corridor => {
              const data = corridorData[corridor]
              const cpi = data?.cpi || 0
              const isSelected = selectedCorridor === corridor
              
              const getBorderColor = () => {
                if (cpi >= 0.85) return '#ef4444'
                if (cpi >= 0.70) return '#f59e0b'
                if (cpi >= 0.40) return '#22c55e'
                return '#334155'
              }

              return (
                <button
                  key={corridor}
                  onClick={() => setSelectedCorridor(corridor)}
                  style={{
                    flex: '1',
                    minWidth: '120px',
                    padding: '16px',
                    background: isSelected ? '#1e293b' : '#0f172a',
                    border: `2px solid ${isSelected ? accentColor : getBorderColor()}`,
                    borderRadius: '12px',
                    color: '#f1f5f9',
                    cursor: 'pointer',
                    textAlign: 'center',
                    transition: 'all 0.2s ease'
                  }}
                >
                  <div style={{
                    fontSize: '16px',
                    fontWeight: '600',
                    marginBottom: '4px'
                  }}>
                    {corridor}
                  </div>
                  <div style={{
                    fontSize: '14px',
                    fontFamily: 'monospace',
                    color: cpi >= 0.85 ? '#ef4444' : cpi >= 0.70 ? '#f59e0b' : '#22c55e'
                  }}>
                    CPI {cpi.toFixed(3)}
                  </div>
                </button>
              )
            })}
          </div>
        )}

        {/* Tab Content */}
        {activeTab === 'Dashboard' && (
          <div style={{ display: 'grid', gap: '24px' }}>
            {/* Pressure Gauge & Metrics */}
            <div style={{
              display: 'grid',
              gridTemplateColumns: 'repeat(auto-fit, minmax(300px, 1fr))',
              gap: '24px'
            }}>
              <div style={{
                background: '#1e293b',
                border: '1px solid #334155',
                borderRadius: '16px',
                padding: '24px',
                display: 'flex',
                flexDirection: 'column',
                alignItems: 'center'
              }}>
                <PressureGauge
                  cpi={corridorData[selectedCorridor]?.cpi}
                  corridor={selectedCorridor}
                  surgeType={corridorData[selectedCorridor]?.surge_type}
                  timeToBreachMinutes={corridorData[selectedCorridor]?.time_to_breach_minutes}
                />
              </div>

              <div style={{
                display: 'grid',
                gridTemplateColumns: 'repeat(auto-fit, minmax(150px, 1fr))',
                gap: '16px'
              }}>
                {[
                  { label: 'Flow Rate', value: `${Math.round(corridorData[selectedCorridor]?.flow_rate || 0)}/min`, color: '#3b82f6' },
                  { label: 'Transport Burst', value: (corridorData[selectedCorridor]?.transport_burst || 0).toFixed(3), color: '#f59e0b' },
                  { label: 'Chokepoint Density', value: (corridorData[selectedCorridor]?.chokepoint_density || 0).toFixed(3), color: '#8b5cf6' },
                  { label: 'Time to Breach', value: corridorData[selectedCorridor]?.time_to_breach_minutes ? `${Math.round(corridorData[selectedCorridor].time_to_breach_minutes)}min` : '—', color: '#ef4444' }
                ].map(metric => (
                  <div key={metric.label} style={{
                    background: '#1e293b',
                    border: '1px solid #334155',
                    borderRadius: '12px',
                    padding: '16px'
                  }}>
                    <div style={{
                      fontSize: '12px',
                      color: '#94a3b8',
                      marginBottom: '8px',
                      textTransform: 'uppercase',
                      fontWeight: '500'
                    }}>
                      {metric.label}
                    </div>
                    <div style={{
                      fontSize: '20px',
                      fontWeight: '700',
                      color: metric.color,
                      fontFamily: 'monospace'
                    }}>
                      {metric.value}
                    </div>
                  </div>
                ))}
              </div>
            </div>

            {/* Agency Panel */}
            <AgencyPanel
              agency={activeRole}
              corridorData={corridorData}
              selectedCorridor={selectedCorridor}
            />

            {/* What-If Simulator */}
            <WhatIfSimulator />
          </div>
        )}

        {activeTab === 'Compare' && (
          <CorridorCompare
            readings={Object.values(corridorData)}
            onSelect={(corridor) => {
              setSelectedCorridor(corridor)
              setActiveTab('Dashboard')
            }}
          />
        )}

        {activeTab === 'Map' && (
          <CorridorMap
            corridorData={corridorData}
            busData={busData}
          />
        )}

        {activeTab === 'History' && (
          <HistoricalPanel corridor={selectedCorridor} />
        )}

        {activeTab === 'Replay' && activeRole === 'admin' && (
          <ReplayMode />
        )}

        {activeTab === 'Alerts' && (
          <div style={{
            background: '#1e293b',
            border: '1px solid #334155',
            borderRadius: '16px',
            padding: '24px'
          }}>
            <h2 style={{
              fontSize: '20px',
              fontWeight: '600',
              color: '#f1f5f9',
              marginBottom: '16px'
            }}>
              Alert Management
            </h2>
            <p style={{
              color: '#94a3b8',
              marginBottom: '16px'
            }}>
              Active alerts and response status for all corridors.
            </p>
            {/* Alert management content would go here */}
          </div>
        )}

        {activeTab === 'Events' && (
          <EventLog />
        )}

        {activeTab === 'Admin' && activeRole === 'admin' && (
          <AdminPanel token={token} />
        )}

        {activeTab === 'Buses' && activeRole === 'gsrtc' && (
          <div style={{
            background: '#1e293b',
            border: '1px solid #334155',
            borderRadius: '16px',
            padding: '24px'
          }}>
            <h2 style={{
              fontSize: '20px',
              fontWeight: '600',
              color: '#f1f5f9',
              marginBottom: '16px',
              display: 'flex',
              alignItems: 'center',
              gap: '12px'
            }}>
              <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="#f59e0b" strokeWidth="1.5">
                <rect x="1" y="3" width="15" height="13" rx="2"/>
                <path d="M16 8h4l3 3v4h-7V8z"/>
                <circle cx="5.5" cy="18.5" r="2.5"/>
                <circle cx="18.5" cy="18.5" r="2.5"/>
              </svg>
              Bus Fleet Status ({busData.length} buses)
            </h2>
            
            <div style={{
              display: 'grid',
              gridTemplateColumns: 'repeat(auto-fill, minmax(300px, 1fr))',
              gap: '16px'
            }}>
              {busData.map(bus => (
                <div key={bus.id} style={{
                  background: '#0f172a',
                  border: `1px solid ${bus.held ? '#ef4444' : '#334155'}`,
                  borderRadius: '12px',
                  padding: '16px'
                }}>
                  <div style={{
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'space-between',
                    marginBottom: '12px'
                  }}>
                    <h3 style={{
                      fontSize: '16px',
                      fontWeight: '600',
                      color: '#f1f5f9',
                      margin: 0
                    }}>
                      {bus.id}
                    </h3>
                    {bus.held && (
                      <span style={{
                        padding: '4px 8px',
                        background: '#ef444420',
                        color: '#ef4444',
                        borderRadius: '6px',
                        fontSize: '12px',
                        fontWeight: '600'
                      }}>
                        HELD
                      </span>
                    )}
                  </div>
                  
                  <div style={{ fontSize: '14px', color: '#94a3b8', marginBottom: '8px' }}>
                    Driver: {bus.driver}
                  </div>
                  <div style={{ fontSize: '14px', color: '#94a3b8', marginBottom: '8px' }}>
                    Route: {bus.route}
                  </div>
                  <div style={{ fontSize: '14px', color: '#94a3b8', marginBottom: '8px' }}>
                    Passengers: {bus.passengers}/{bus.capacity}
                  </div>
                  <div style={{ fontSize: '14px', color: '#94a3b8', marginBottom: '8px' }}>
                    ETA: {bus.eta_minutes} min ({bus.distance_km} km)
                  </div>
                  <div style={{ fontSize: '14px', color: '#94a3b8' }}>
                    Speed: {bus.speed_kmh} km/h
                  </div>
                  
                  {bus.alert_message && (
                    <div style={{
                      marginTop: '12px',
                      padding: '8px',
                      background: `${bus.alert_status === 'hold' ? '#ef4444' : '#f59e0b'}20`,
                      color: bus.alert_status === 'hold' ? '#ef4444' : '#f59e0b',
                      borderRadius: '6px',
                      fontSize: '12px'
                    }}>
                      {bus.alert_message}
                    </div>
                  )}
                </div>
              ))}
            </div>
          </div>
        )}
      </main>

      {/* Alert Reply Modal */}
      {showAlertModal && activeAlert && (
        <div style={{
          position: 'fixed',
          top: 0,
          left: 0,
          width: '100vw',
          height: '100vh',
          background: 'rgba(0,0,0,0.75)',
          zIndex: 9999,
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          padding: '1rem'
        }}>
          <AlertReplyModal
            alert={activeAlert}
            agency={activeRole}
            token={token}
            onClose={handleAlertCancel}
            onReplied={handleAlertReplied}
          />
        </div>
      )}

      {/* PDF Viewer */}
      {pdfViewer && (
        <PDFViewer
          alertId={pdfViewer}
          onClose={() => setPdfViewer(null)}
        />
      )}

      {/* Mobile responsive styles */}
      <style jsx>{`
        @media (max-width: 768px) {
          header div[style*="display: flex"] {
            flex-wrap: wrap;
            gap: 8px;
          }
          
          header button[style*="display: none"] {
            display: flex !important;
          }
          
          main div[style*="gridTemplateColumns"] {
            grid-template-columns: 1fr !important;
          }
          
          div[style*="flex-wrap: wrap"] {
            flex-direction: column;
          }
          
          div[style*="minWidth: '120px'"] {
            min-width: auto !important;
          }
        }
      `}</style>
    </div>
  )
}