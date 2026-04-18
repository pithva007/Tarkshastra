import React from 'react'
import { MapContainer, TileLayer, CircleMarker, Tooltip, Polyline } from 'react-leaflet'

const CORRIDOR_GEO = {
  Ambaji:   { center: [24.3368, 72.8502], chokepoints: [[24.334, 72.848], [24.337, 72.851], [24.339, 72.852]] },
  Dwarka:   { center: [22.2394, 68.9678], chokepoints: [[22.237, 68.965], [22.241, 68.970]] },
  Somnath:  { center: [20.8880, 70.4012], chokepoints: [[20.885, 70.399], [20.888, 70.401], [20.890, 70.403], [20.887, 70.405]] },
  Pavagadh: { center: [22.4962, 73.5247], chokepoints: [[22.493, 73.522], [22.497, 73.525], [22.499, 73.527]] },
}

/**
 * Leaflet map showing corridor markers + chokepoints.
 *
 * Props:
 *   readings  — array of live CPI objects
 *   selected  — currently selected corridor
 *   onSelect  — callback(name)
 */
export default function CorridorMap({ readings = [], selected, onSelect }) {
  const byName = Object.fromEntries(readings.map((r) => [r.corridor, r]))

  const markerColor = (cpi) => {
    if (cpi == null) return '#6b7280'
    if (cpi < 0.40)  return '#22c55e'
    if (cpi < 0.70)  return '#f59e0b'
    return '#ef4444'
  }

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
          const r = byName[name]
          const cpi = r?.cpi ?? 0
          const color = markerColor(cpi)
          const isSelected = selected === name

          return (
            <React.Fragment key={name}>
              {/* Main corridor marker */}
              <CircleMarker
                center={geo.center}
                radius={isSelected ? 20 : 13}
                pathOptions={{
                  color:       isSelected ? '#ffffff' : color,
                  fillColor:   color,
                  fillOpacity: 0.85,
                  weight:      isSelected ? 3 : 1.5,
                }}
                eventHandlers={{ click: () => onSelect?.(name) }}
              >
                <Tooltip sticky>
                  <div className="text-xs font-mono">
                    <strong>{name}</strong><br />
                    CPI: {cpi.toFixed(3)}<br />
                    {r?.surge_type && `Type: ${r.surge_type}`}
                  </div>
                </Tooltip>
              </CircleMarker>

              {/* Chokepoint markers */}
              {geo.chokepoints.map((pos, idx) => (
                <CircleMarker
                  key={idx}
                  center={pos}
                  radius={5}
                  pathOptions={{
                    color:       '#f59e0b',
                    fillColor:   cpi > 0.70 ? '#ef4444' : '#f59e0b',
                    fillOpacity: 0.75,
                    weight:      1,
                  }}
                >
                  <Tooltip>
                    <span className="text-xs">Choke Point {idx + 1} — {name}</span>
                  </Tooltip>
                </CircleMarker>
              ))}
            </React.Fragment>
          )
        })}
      </MapContainer>
    </div>
  )
}
