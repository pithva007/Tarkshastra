import { useEffect, useRef } from 'react'
import { MapContainer, TileLayer, Marker, Polyline, Popup } from 'react-leaflet'
import L from 'leaflet'
import { triggerVoiceAlert } from '../utils/voiceAlert'

// ── Icon helpers ───────────────────────────────────────────────────────────────
function makeBusIcon(status) {
  const colors = { normal: '#22c55e', caution: '#f59e0b', hold: '#ef4444' }
  const c = colors[status] || '#6b7280'
  return new L.DivIcon({
    className: '',
    html: `<div style="
      background:${c};border:2px solid white;border-radius:8px;
      width:32px;height:32px;display:flex;align-items:center;
      justify-content:center;font-size:18px;
      box-shadow:0 0 10px ${c}99;
    ">🚌</div>`,
    iconSize: [32, 32],
    iconAnchor: [16, 16],
  })
}

function makeDestIcon() {
  return new L.DivIcon({
    className: '',
    html: `<div style="font-size:28px;line-height:1;filter:drop-shadow(0 0 4px #fbbf24)">⭐</div>`,
    iconSize: [28, 28],
    iconAnchor: [14, 14],
  })
}

// ── Status card config ─────────────────────────────────────────────────────────
const STATUS_CONFIG = {
  normal: {
    bg: 'bg-green-950 border-green-700',
    text: 'text-green-300',
    icon: '✅',
    label: 'PROCEED',
  },
  caution: {
    bg: 'bg-amber-950 border-amber-700',
    text: 'text-amber-300',
    icon: '⚠️',
    label: 'SLOW DOWN',
  },
  hold: {
    bg: 'bg-red-950 border-red-700 animate-pulse',
    text: 'text-red-300',
    icon: '🛑',
    label: 'STOP AT CHECKPOINT',
  },
}

const DEST_POSITIONS = {
  Ambaji:   [23.7267, 72.8503],
  Dwarka:   [22.2394, 68.9678],
  Somnath:  [20.8880, 70.4013],
  Pavagadh: [22.4673, 73.5315],
}

/**
 * DriverDashboard — shown when ?agency=driver
 *
 * Props:
 *   buses        — array of bus objects from bus_update WebSocket message
 *   corridorData — live CPI readings per corridor
 *   driverBusId  — the logged-in driver's bus ID (from localStorage)
 *   driverName   — driver's name
 */
export default function DriverDashboard({ buses = [], corridorData = {}, driverBusId, driverName }) {
  const prevStatus = useRef(null)
  const voiceFiredRef = useRef(new Set())

  // Find this driver's bus
  const myBus = buses.find((b) => b.id === driverBusId) || buses[0] || null
  const destCorridor = myBus?.destination
  const destReading  = destCorridor ? corridorData[destCorridor] : null
  const destCpi      = destReading?.cpi ?? null
  const alertStatus  = myBus?.alert_status ?? 'normal'
  const alertId      = destReading?.alert_id

  // Auto-trigger voice when status changes to hold
  useEffect(() => {
    if (alertStatus === 'hold' && prevStatus.current !== 'hold') {
      if (alertId && !voiceFiredRef.current.has(alertId)) {
        voiceFiredRef.current.add(alertId)
        const ttb = destReading?.time_to_breach_minutes ?? 5
        triggerVoiceAlert(destCorridor, destCpi ?? 0.8, Math.ceil(ttb), 'driver')
      }
    }
    prevStatus.current = alertStatus
  }, [alertStatus, alertId])

  const cfg = STATUS_CONFIG[alertStatus] || STATUS_CONFIG.normal
  const destPos = destCorridor ? DEST_POSITIONS[destCorridor] : null

  // Build route line: bus position → destination
  const routeLine = myBus && destPos
    ? [[myBus.lat, myBus.lng], destPos]
    : null

  // Alert history for this route (last 5 alerts from corridorData)
  const recentAlerts = Object.values(corridorData)
    .filter((r) => r.corridor === destCorridor && r.alert_active)
    .slice(0, 5)

  return (
    <div className="space-y-4 max-w-2xl mx-auto">
      {/* Bus identity header */}
      <div className="bg-gray-900 rounded-2xl border border-gray-700 p-4">
        <div className="flex items-center gap-3">
          <span className="text-4xl">🚌</span>
          <div>
            <p className="text-white font-bold text-lg">{myBus?.id ?? driverBusId ?? 'GJ-01-BUS-042'}</p>
            <p className="text-gray-400 text-sm">{driverName ?? myBus?.driver ?? 'Driver'}</p>
            <p className="text-amber-400 text-sm font-medium">{myBus?.route ?? 'Route loading…'}</p>
          </div>
        </div>
      </div>

      {/* Status card */}
      <div className={`rounded-2xl border p-5 ${cfg.bg}`}>
        <div className="flex items-center gap-3 mb-2">
          <span className="text-4xl">{cfg.icon}</span>
          <div>
            <p className={`text-2xl font-black ${cfg.text}`}>{cfg.label}</p>
            <p className="text-gray-300 text-sm">
              {destCorridor} CPI:{' '}
              <span className={`font-mono font-bold ${cfg.text}`}>
                {destCpi != null ? destCpi.toFixed(3) : '…'}
              </span>
              {destReading?.ml_risk_level && (
                <span className="ml-2 text-xs text-gray-400">({destReading.ml_risk_level})</span>
              )}
            </p>
          </div>
        </div>
        {myBus?.alert_message && (
          <p className="text-sm text-gray-300 mt-2 bg-black/20 rounded-lg px-3 py-2">
            {myBus.alert_message}
          </p>
        )}
      </div>

      {/* Stats row */}
      <div className="grid grid-cols-3 gap-3">
        <StatCard label="ETA" value={myBus ? `${myBus.eta_minutes} min` : '—'} />
        <StatCard label="Distance" value={myBus ? `${myBus.distance_km} km` : '—'} />
        <StatCard label="Passengers" value={myBus?.passengers ?? '—'} />
      </div>

      {/* Map */}
      {myBus && (
        <div className="rounded-xl overflow-hidden border border-gray-700" style={{ height: 300 }}>
          <MapContainer
            center={[myBus.lat, myBus.lng]}
            zoom={9}
            style={{ width: '100%', height: '100%' }}
            scrollWheelZoom={false}
          >
            <TileLayer
              attribution='&copy; <a href="https://www.openstreetmap.org/">OpenStreetMap</a>'
              url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
            />
            {/* Bus marker */}
            <Marker position={[myBus.lat, myBus.lng]} icon={makeBusIcon(alertStatus)}>
              <Popup>
                <strong>{myBus.id}</strong><br />
                Speed: {myBus.speed_kmh} km/h<br />
                ETA: {myBus.eta_minutes} min
              </Popup>
            </Marker>
            {/* Destination marker */}
            {destPos && (
              <Marker position={destPos} icon={makeDestIcon()}>
                <Popup><strong>⭐ {destCorridor}</strong></Popup>
              </Marker>
            )}
            {/* Route line */}
            {routeLine && (
              <Polyline
                positions={routeLine}
                pathOptions={{ color: '#f59e0b', weight: 2, dashArray: '6 5', opacity: 0.8 }}
              />
            )}
          </MapContainer>
        </div>
      )}

      {/* Voice alert button */}
      <button
        onClick={() => {
          const ttb = destReading?.time_to_breach_minutes ?? 5
          triggerVoiceAlert(destCorridor ?? 'Ambaji', destCpi ?? 0.7, Math.ceil(ttb), 'driver')
        }}
        className="w-full py-3 rounded-xl bg-gray-800 hover:bg-gray-700 border border-gray-600 text-white text-sm font-semibold transition-colors"
      >
        🔊 Play Voice Alert
      </button>

      {/* Alert history */}
      {recentAlerts.length > 0 && (
        <div className="bg-gray-900 rounded-xl border border-gray-700 p-4">
          <p className="text-xs text-gray-400 uppercase tracking-wide mb-3">Recent Alerts — {destCorridor}</p>
          <div className="space-y-2">
            {recentAlerts.map((r, i) => (
              <div key={i} className="flex items-center gap-2 text-xs">
                <span className="text-red-400">🚨</span>
                <span className="text-gray-300">CPI {r.cpi?.toFixed(3)} · {r.surge_type}</span>
                <span className="text-gray-500 ml-auto">{r.alert_id}</span>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}

function StatCard({ label, value }) {
  return (
    <div className="bg-gray-900 rounded-xl border border-gray-700 p-3 text-center">
      <p className="text-xs text-gray-500 uppercase tracking-wide">{label}</p>
      <p className="text-xl font-bold font-mono text-white mt-1">{value}</p>
    </div>
  )
}
