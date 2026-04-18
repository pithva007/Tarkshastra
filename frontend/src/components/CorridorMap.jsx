import React from 'react'
import { MapContainer, TileLayer, CircleMarker, Marker, Tooltip } from 'react-leaflet'
import L from 'leaflet'

const CORRIDOR_GEO = {
  Ambaji: {
    center: [23.7267, 72.8503],
    chokepoints: [
      [23.7250, 72.8490],
      [23.7267, 72.8510],
      [23.7280, 72.8498],
    ],
  },
  Dwarka: {
    center: [22.2394, 68.9678],
    chokepoints: [
      [22.2375, 68.9660],
      [22.2410, 68.9695],
    ],
  },
  Somnath: {
    center: [20.8880, 70.4013],
    chokepoints: [
      [20.8860, 70.3995],
      [20.8895, 70.4025],
    ],
  },
  Pavagadh: {
    center: [22.4673, 73.5315],
    chokepoints: [
      [22.4655, 73.5298],
      [22.4688, 73.5330],
    ],
  },
}

// Creates a DivIcon with a pulsing ring (uses Tailwind animate-ping)
function makePulseIcon(color, sizePx) {
  const half = sizePx / 2
  return new L.DivIcon({
    className: '',
    html: `<div style="width:${sizePx}px;height:${sizePx}px;position:relative">
      <div class="animate-ping" style="
        position:absolute;inset:0;border-radius:50%;
        background:${color};opacity:0.55;
      "></div>
      <div style="
        position:absolute;inset:30%;border-radius:50%;
        background:${color};opacity:0.9;
      "></div>
    </div>`,
    iconSize:   [sizePx, sizePx],
    iconAnchor: [half, half],
  })
}

function cpiToColor(cpi) {
  if (cpi == null) return '#6b7280'
  if (cpi >= 0.70)  return '#ef4444'
  if (cpi >= 0.40)  return '#f59e0b'
  return '#22c55e'
}

// Circle radius scales with CPI: 5–20px
function cpiToRadius(cpi) {
  return 5 + Math.round((cpi || 0) * 15)
}

export default function CorridorMap({ readings = [], selected, onSelect }) {
  const byName = Object.fromEntries(readings.map((r) => [r.corridor, r]))

  return (
    <div className="rounded-xl overflow-hidden border border-gray-700" style={{ height: 340 }}>
      <MapContainer
        center={[22.5, 71.5]}
        zoom={7}
        style={{ width: '100%', height: '100%' }}
        scrollWheelZoom={false}
      >
        <TileLayer
          attribution='&copy; <a href="https://www.openstreetmap.org/">OpenStreetMap</a>'
          url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
        />

        {Object.entries(CORRIDOR_GEO).map(([name, geo]) => {
          const r          = byName[name]
          const cpi        = r?.cpi ?? 0
          const color      = cpiToColor(cpi)
          const isSelected = selected === name
          const isPulsing  = cpi > 0.70
          const radius     = cpiToRadius(cpi)

          return (
            <React.Fragment key={name}>
              {/* Main corridor marker — radius scales with CPI */}
              <CircleMarker
                center={geo.center}
                radius={isSelected ? radius + 6 : radius}
                pathOptions={{
                  color:       isSelected ? '#ffffff' : color,
                  fillColor:   color,
                  fillOpacity: 0.85,
                  weight:      isSelected ? 3 : 1.5,
                }}
                eventHandlers={{ click: () => onSelect?.(name) }}
              >
                <Tooltip sticky>
                  <div style={{ fontSize: 12, fontFamily: 'monospace' }}>
                    <strong>{name}</strong><br />
                    CPI: {cpi.toFixed(3)}<br />
                    {r?.surge_type && `Type: ${r.surge_type}`}<br />
                    {r?.ml_confidence != null && `ML Confidence: ${r.ml_confidence}%`}
                  </div>
                </Tooltip>
              </CircleMarker>

              {/* Chokepoint markers */}
              {geo.chokepoints.map((pos, idx) => (
                <React.Fragment key={idx}>
                  {/* Pulse ring overlay when CPI > 0.7 */}
                  {isPulsing && (
                    <Marker
                      position={pos}
                      icon={makePulseIcon(color, 24)}
                      interactive={false}
                    />
                  )}

                  {/* Solid chokepoint dot */}
                  <CircleMarker
                    center={pos}
                    radius={isPulsing ? 6 : 4}
                    pathOptions={{
                      color:       color,
                      fillColor:   isPulsing ? '#ef4444' : color,
                      fillOpacity: isPulsing ? 1.0 : 0.75,
                      weight:      1,
                    }}
                  >
                    <Tooltip>
                      <div style={{ fontSize: 11 }}>
                        Chokepoint {idx + 1} — {name}<br />
                        CPI: {cpi.toFixed(3)}
                      </div>
                    </Tooltip>
                  </CircleMarker>
                </React.Fragment>
              ))}
            </React.Fragment>
          )
        })}
      </MapContainer>
    </div>
  )
}
