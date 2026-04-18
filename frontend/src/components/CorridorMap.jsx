import { useEffect, useRef } from 'react'
import {
  MapContainer, TileLayer, CircleMarker, Marker,
  Tooltip, Popup, Polyline, useMap,
} from 'react-leaflet'
import L from 'leaflet'

// ── Static geo data ────────────────────────────────────────────────────────────
const TEMPLES = [
  { name: 'Ambaji',   pos: [23.7267, 72.8503] },
  { name: 'Dwarka',   pos: [22.2394, 68.9678] },
  { name: 'Somnath',  pos: [20.8880, 70.4013] },
  { name: 'Pavagadh', pos: [22.4673, 73.5315] },
]

const POLICE_STATIONS = [
  { name: 'Ambaji PS',   pos: [23.7234, 72.8476] },
  { name: 'Dwarka PS',   pos: [22.2378, 68.9645] },
  { name: 'Somnath PS',  pos: [20.8901, 70.3989] },
  { name: 'Pavagadh PS', pos: [22.4689, 73.5298] },
]

const CHOKEPOINTS = {
  Ambaji:   [[23.7250, 72.8490], [23.7267, 72.8510], [23.7280, 72.8498]],
  Dwarka:   [[22.2375, 68.9660], [22.2410, 68.9695]],
  Somnath:  [[20.8860, 70.3995], [20.8895, 70.4025]],
  Pavagadh: [[22.4655, 73.5298], [22.4688, 73.5330]],
}

// ── Icon factories ─────────────────────────────────────────────────────────────
function makeTempleIcon(cpi) {
  const color = cpi >= 0.70 ? '#ef4444' : cpi >= 0.40 ? '#f59e0b' : '#fbbf24'
  return new L.DivIcon({
    className: '',
    html: `<div style="font-size:26px;line-height:1;filter:drop-shadow(0 0 4px ${color})">⭐</div>`,
    iconSize: [28, 28],
    iconAnchor: [14, 14],
  })
}

function makePoliceIcon() {
  return new L.DivIcon({
    className: '',
    html: `<div style="font-size:20px;line-height:1;filter:drop-shadow(0 0 3px #3b82f6)">🛡️</div>`,
    iconSize: [22, 22],
    iconAnchor: [11, 11],
  })
}

function makeBusIcon(alertStatus) {
  const colors = { normal: '#22c55e', caution: '#f59e0b', hold: '#ef4444' }
  const color = colors[alertStatus] || '#6b7280'
  return new L.DivIcon({
    className: '',
    html: `<div style="
      background:${color};
      border:2px solid white;
      border-radius:6px;
      width:24px;height:24px;
      display:flex;align-items:center;justify-content:center;
      font-size:13px;
      box-shadow:0 0 6px ${color}88;
    ">🚌</div>`,
    iconSize: [24, 24],
    iconAnchor: [12, 12],
  })
}

function makePulseIcon(color, size = 20) {
  const half = size / 2
  return new L.DivIcon({
    className: '',
    html: `<div style="width:${size}px;height:${size}px;position:relative">
      <div style="
        position:absolute;inset:0;border-radius:50%;
        background:${color};opacity:0.5;
        animation:ping 1s cubic-bezier(0,0,0.2,1) infinite;
      "></div>
      <div style="
        position:absolute;inset:25%;border-radius:50%;
        background:${color};opacity:0.9;
      "></div>
    </div>
    <style>
      @keyframes ping {
        75%,100%{transform:scale(2);opacity:0}
      }
    </style>`,
    iconSize: [size, size],
    iconAnchor: [half, half],
  })
}

// ── Helpers ────────────────────────────────────────────────────────────────────
function cpiColor(cpi) {
  if (cpi == null) return '#6b7280'
  if (cpi >= 0.70) return '#ef4444'
  if (cpi >= 0.40) return '#f59e0b'
  return '#22c55e'
}

function cpiZoneLabel(cpi) {
  if (cpi == null) return 'Unknown'
  if (cpi >= 0.85) return 'CRITICAL'
  if (cpi >= 0.70) return 'HIGH'
  if (cpi >= 0.40) return 'MEDIUM'
  return 'SAFE'
}

// Pressure circle radius in metres: CPI × 5000
function pressureRadius(cpi) {
  return Math.max(500, (cpi || 0) * 5000)
}

// ── Bus route line: current position → destination ────────────────────────────
function BusRouteLine({ bus, destPos }) {
  if (!destPos) return null
  const positions = [[bus.lat, bus.lng], destPos]
  return (
    <Polyline
      positions={positions}
      pathOptions={{ color: '#6b7280', weight: 1.5, dashArray: '5 6', opacity: 0.6 }}
    />
  )
}

// ── Main component ─────────────────────────────────────────────────────────────
export default function CorridorMap({ readings = [], buses = [], selected, onSelect }) {
  const byName = Object.fromEntries(readings.map((r) => [r.corridor, r]))
  const destPos = Object.fromEntries(TEMPLES.map((t) => [t.name, t.pos]))

  return (
    <div className="rounded-xl overflow-hidden border border-gray-700" style={{ height: 420 }}>
      <MapContainer
        center={[22.2587, 71.1924]}
        zoom={7}
        style={{ width: '100%', height: '100%' }}
        scrollWheelZoom={false}
      >
        <TileLayer
          attribution='&copy; <a href="https://www.openstreetmap.org/">OpenStreetMap</a>'
          url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
        />

        {/* ── Temple markers ── */}
        {TEMPLES.map((temple) => {
          const r   = byName[temple.name]
          const cpi = r?.cpi ?? 0
          const color = cpiColor(cpi)
          const isSelected = selected === temple.name

          return (
            <Marker
              key={temple.name}
              position={temple.pos}
              icon={makeTempleIcon(cpi)}
              eventHandlers={{ click: () => onSelect?.(temple.name) }}
            >
              <Popup>
                <div style={{ minWidth: 160, fontFamily: 'monospace', fontSize: 12 }}>
                  <strong style={{ fontSize: 14 }}>⭐ {temple.name}</strong>
                  <hr style={{ margin: '4px 0', borderColor: '#ccc' }} />
                  <div>CPI: <strong style={{ color }}>{cpi.toFixed(3)}</strong></div>
                  <div>Zone: <strong>{cpiZoneLabel(cpi)}</strong></div>
                  {r?.surge_type && <div>Surge: {r.surge_type}</div>}
                  {r?.time_to_breach_minutes != null && (
                    <div style={{ color: '#ef4444' }}>
                      ⏱ Breach in {r.time_to_breach_minutes.toFixed(1)} min
                    </div>
                  )}
                  {r?.ml_confidence != null && (
                    <div>ML: {r.ml_confidence}% · {r.ml_risk_level}</div>
                  )}
                </div>
              </Popup>
            </Marker>
          )
        })}

        {/* ── Pressure circles around temples ── */}
        {TEMPLES.map((temple) => {
          const r   = byName[temple.name]
          const cpi = r?.cpi ?? 0
          const color = cpiColor(cpi)
          return (
            <CircleMarker
              key={`pressure-${temple.name}`}
              center={temple.pos}
              radius={Math.max(8, Math.round(cpi * 30))}
              pathOptions={{
                color,
                fillColor: color,
                fillOpacity: 0.12,
                weight: 1.5,
                opacity: 0.4,
              }}
              interactive={false}
            />
          )
        })}

        {/* ── Police station markers ── */}
        {POLICE_STATIONS.map((ps) => (
          <Marker key={ps.name} position={ps.pos} icon={makePoliceIcon()}>
            <Popup>
              <div style={{ fontFamily: 'monospace', fontSize: 12 }}>
                <strong>🛡️ {ps.name}</strong>
                <div style={{ marginTop: 4, color: '#22c55e' }}>Status: Active</div>
              </div>
            </Popup>
          </Marker>
        ))}

        {/* ── Chokepoint markers ── */}
        {Object.entries(CHOKEPOINTS).map(([corridorName, points]) => {
          const r   = byName[corridorName]
          const cpi = r?.cpi ?? 0
          const color = cpiColor(cpi)
          const isPulsing = cpi > 0.70

          return points.map((pos, idx) => (
            <Marker
              key={`choke-${corridorName}-${idx}`}
              position={pos}
              icon={isPulsing ? makePulseIcon(color, 18) : makePulseIcon('#6b7280', 12)}
              interactive={false}
            >
              <Tooltip>
                <span style={{ fontSize: 11 }}>
                  ⚠ Chokepoint {idx + 1} — {corridorName} · CPI {cpi.toFixed(3)}
                </span>
              </Tooltip>
            </Marker>
          ))
        })}

        {/* ── Live bus markers ── */}
        {buses.map((bus) => (
          <Marker
            key={bus.id}
            position={[bus.lat, bus.lng]}
            icon={makeBusIcon(bus.alert_status)}
          >
            <Popup>
              <div style={{ minWidth: 180, fontFamily: 'monospace', fontSize: 12 }}>
                <strong>🚌 {bus.id}</strong>
                <hr style={{ margin: '4px 0', borderColor: '#ccc' }} />
                <div>Driver: {bus.driver}</div>
                <div>Route: {bus.route}</div>
                <div>ETA: {bus.eta_minutes} min</div>
                <div>Distance: {bus.distance_km} km</div>
                <div>Passengers: {bus.passengers}</div>
                <div>Speed: {bus.speed_kmh} km/h</div>
                <div style={{
                  marginTop: 6,
                  color: bus.alert_status === 'hold' ? '#ef4444' : bus.alert_status === 'caution' ? '#f59e0b' : '#22c55e',
                  fontWeight: 'bold',
                }}>
                  {bus.alert_status?.toUpperCase()}: {bus.alert_message}
                </div>
              </div>
            </Popup>
            <BusRouteLine bus={bus} destPos={destPos[bus.destination]} />
          </Marker>
        ))}

      </MapContainer>
    </div>
  )
}
