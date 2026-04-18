import React, { useEffect, useRef } from 'react'

const API = import.meta.env.VITE_API_URL || 'http://localhost:8000'

// Temple locations
const TEMPLES = [
  {
    name: "Ambaji",
    lat: 23.7267, lng: 72.8503,
    chokepoints: [
      [23.7245, 72.8478],
      [23.7289, 72.8521],
      [23.7261, 72.8534]
    ]
  },
  {
    name: "Dwarka",
    lat: 22.2394, lng: 68.9678,
    chokepoints: [
      [22.2378, 68.9645],
      [22.2412, 68.9701]
    ]
  },
  {
    name: "Somnath",
    lat: 20.8880, lng: 70.4013,
    chokepoints: [
      [20.8901, 70.3989],
      [20.8865, 70.4034]
    ]
  },
  {
    name: "Pavagadh",
    lat: 22.4673, lng: 73.5315,
    chokepoints: [
      [22.4689, 73.5298],
      [22.4658, 73.5332]
    ]
  }
]

// Police stations
const POLICE_STATIONS = [
  { name: "Ambaji PS",   lat: 23.7234, lng: 72.8476 },
  { name: "Dwarka PS",   lat: 22.2378, lng: 68.9645 },
  { name: "Somnath PS",  lat: 20.8901, lng: 70.3989 },
  { name: "Pavagadh PS", lat: 22.4689, lng: 73.5298 }
]

// CPI zone colors
function getCpiColor(cpi) {
  if (!cpi || cpi < 0.4) return '#22c55e'
  if (cpi < 0.7) return '#f59e0b'
  return '#ef4444'
}

// Alert status colors for buses
function getBusColor(alertStatus) {
  if (alertStatus === 'hold')    return '#ef4444'
  if (alertStatus === 'caution') return '#f59e0b'
  return '#22c55e'
}

export default function CorridorMap({ corridorData = {}, busData = [] }) {
  const mapRef = useRef(null)
  const leafletMap = useRef(null)
  const markersRef = useRef({
    temples: [],
    police: [],
    chokepoints: [],
    buses: {},        // keyed by bus id
    circles: []
  })

  // Initialize map ONCE
  useEffect(() => {
    if (leafletMap.current) return
    if (!mapRef.current) return

    // Dynamically import Leaflet to avoid SSR issues
    import('leaflet').then(L => {
      // Fix default icon path issue in Vite
      delete L.Icon.Default.prototype._getIconUrl
      L.Icon.Default.mergeOptions({
        iconRetinaUrl: 'https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/images/marker-icon-2x.png',
        iconUrl: 'https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/images/marker-icon.png',
        shadowUrl: 'https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/images/marker-shadow.png',
      })

      const map = L.map(mapRef.current, {
        center: [22.2587, 71.1924],
        zoom: 7,
        zoomControl: true,
        scrollWheelZoom: true
      })

      // OpenStreetMap tiles
      L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
        attribution: 'OpenStreetMap',
        maxZoom: 18
      }).addTo(map)

      leafletMap.current = map

      // Add static markers after map loads
      addTempleMarkers(L, map)
      addPoliceMarkers(L, map)
      addChokepointMarkers(L, map)
    })

    return () => {
      if (leafletMap.current) {
        leafletMap.current.remove()
        leafletMap.current = null
      }
    }
  }, [])

  // Add temple markers with SVG icon using DivIcon
  function addTempleMarkers(L, map) {
    TEMPLES.forEach(temple => {
      const icon = L.divIcon({
        className: '',
        html: `<div style="width:36px;height:36px;background:#1e1b2e;border:2px solid #8B5CF6;border-radius:50%;display:flex;align-items:center;justify-content:center;box-shadow:0 0 8px rgba(139,92,246,0.6)">
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="#8B5CF6" stroke-width="1.5">
            <path d="M3 22V12L12 3l9 9v10"/>
            <path d="M9 22V16h6v6"/>
            <path d="M12 3v4M8 7h8"/>
          </svg>
        </div>`,
        iconSize: [36, 36],
        iconAnchor: [18, 18],
        popupAnchor: [0, -20]
      })

      const marker = L.marker([temple.lat, temple.lng], { icon }).addTo(map)
      marker.bindPopup(`<div style="background:#1e293b;color:#f1f5f9;padding:12px;border-radius:8px;min-width:160px;font-family:system-ui;">
        <div style="font-weight:600;font-size:14px;margin-bottom:6px;">${temple.name} Temple</div>
        <div style="font-size:12px;color:#94a3b8;">Loading live data...</div>
      </div>`, {
        className: 'dark-popup'
      })

      markersRef.current.temples.push({
        marker, name: temple.name
      })
    })
  }

  // Add police station markers
  function addPoliceMarkers(L, map) {
    POLICE_STATIONS.forEach(station => {
      const icon = L.divIcon({
        className: '',
        html: `<div style="width:30px;height:30px;background:#0f172a;border:2px solid #3B82F6;border-radius:6px;display:flex;align-items:center;justify-content:center;">
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="#3B82F6" stroke-width="1.5">
            <path d="M12 2L3 7v5c0 5.25 3.75 10.15 9 11.25C17.25 22.15 21 17.25 21 12V7L12 2z"/>
          </svg>
        </div>`,
        iconSize: [30, 30],
        iconAnchor: [15, 15],
        popupAnchor: [0, -18]
      })

      const marker = L.marker([station.lat, station.lng], { icon }).addTo(map)
      marker.bindPopup(`<div style="background:#1e293b;color:#f1f5f9;padding:10px;border-radius:8px;font-family:system-ui;">
        <div style="font-weight:600;font-size:13px;">${station.name}</div>
        <div style="font-size:11px;color:#3B82F6;margin-top:4px;">Police Station</div>
      </div>`)

      markersRef.current.police.push(marker)
    })
  }

  // Add chokepoint warning markers
  function addChokepointMarkers(L, map) {
    TEMPLES.forEach(temple => {
      temple.chokepoints.forEach((cp, idx) => {
        const icon = L.divIcon({
          className: '',
          html: `<div style="width:24px;height:24px;display:flex;align-items:center;justify-content:center;">
            <svg width="24" height="24" viewBox="0 0 24 24">
              <path d="M12 2L2 20h20L12 2z" fill="#ef4444" fill-opacity="0.15" stroke="#ef4444" stroke-width="1.5"/>
              <text x="12" y="17" text-anchor="middle" font-size="9" font-weight="bold" fill="#ef4444">!</text>
            </svg>
          </div>`,
          iconSize: [24, 24],
          iconAnchor: [12, 12]
        })

        const marker = L.marker(cp, { icon }).addTo(map)
        marker.bindPopup(`<div style="background:#1e293b;color:#f1f5f9;padding:10px;border-radius:8px;font-family:system-ui;">
          <div style="font-weight:600;font-size:13px;color:#ef4444;">Choke Point ${idx + 1}</div>
          <div style="font-size:11px;color:#94a3b8;margin-top:4px;">${temple.name} corridor</div>
        </div>`)

        markersRef.current.chokepoints.push(marker)
      })
    })
  }

  // Update temple popups when corridorData changes
  useEffect(() => {
    if (!leafletMap.current) return

    import('leaflet').then(L => {
      // Update pressure circles
      markersRef.current.circles.forEach(c => c.remove())
      markersRef.current.circles = []

      TEMPLES.forEach(temple => {
        const data = corridorData[temple.name]
        const cpi = data?.cpi || 0
        const color = getCpiColor(cpi)

        // Pressure circle (radius scales with CPI)
        const circle = L.circle([temple.lat, temple.lng], {
          radius: cpi * 4000,
          color: color,
          fillColor: color,
          fillOpacity: 0.12,
          weight: 1.5,
          opacity: 0.5
        }).addTo(leafletMap.current)

        markersRef.current.circles.push(circle)

        // Update temple marker popup content
        const tmpl = markersRef.current.temples.find(t => t.name === temple.name)
        if (tmpl && data) {
          tmpl.marker.setPopupContent(`<div style="background:#1e293b;color:#f1f5f9;padding:12px;border-radius:8px;min-width:180px;font-family:system-ui;">
            <div style="font-weight:600;font-size:14px;margin-bottom:8px;">${temple.name} Temple</div>
            <div style="display:flex;justify-content:space-between;margin-bottom:4px;font-size:12px;">
              <span style="color:#94a3b8;">CPI</span>
              <span style="color:${color};font-weight:600;">${(cpi).toFixed(3)}</span>
            </div>
            <div style="display:flex;justify-content:space-between;margin-bottom:4px;font-size:12px;">
              <span style="color:#94a3b8;">State</span>
              <span style="color:#f1f5f9;">${data.corridor_state || 'NORMAL'}</span>
            </div>
            <div style="display:flex;justify-content:space-between;font-size:12px;">
              <span style="color:#94a3b8;">Surge Type</span>
              <span style="color:${color};">${data.surge_type || 'SAFE'}</span>
            </div>
          </div>`)
        }
      })
    })
  }, [corridorData])

  // ── BUS MARKERS — Updated every 5 seconds ──
  useEffect(() => {
    if (!leafletMap.current || !busData?.length) return

    import('leaflet').then(L => {
      busData.forEach(bus => {
        // Skip if invalid coordinates
        if (!bus.lat || !bus.lng) return
        if (isNaN(bus.lat) || isNaN(bus.lng)) return

        const color = getBusColor(bus.alert_status)
        const isHeld = bus.held

        // Build bus DivIcon — styled div, not SVG file
        const busIcon = L.divIcon({
          className: '',   // MUST be empty string
          html: `<div style="position:relative;width:38px;height:38px;">
            <div style="width:38px;height:38px;background:#0f172a;border:2px solid ${color};border-radius:8px;display:flex;align-items:center;justify-content:center;box-shadow:0 0 6px ${color}80;${isHeld ? 'animation:pulse 1s infinite;' : ''}">
              <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="${color}" stroke-width="1.5">
                <rect x="1" y="3" width="15" height="13" rx="2"/>
                <path d="M16 8h4l3 3v4h-7V8z"/>
                <circle cx="5.5" cy="18.5" r="2.5"/>
                <circle cx="18.5" cy="18.5" r="2.5"/>
              </svg>
            </div>
            ${isHeld ? `<div style="position:absolute;top:-6px;right:-6px;width:14px;height:14px;background:#ef4444;border-radius:50%;border:2px solid #0f172a;"></div>` : ''}
          </div>`,
          iconSize: [38, 38],
          iconAnchor: [19, 19],
          popupAnchor: [0, -22]
        })

        const popupContent = `<div style="background:#1e293b;color:#f1f5f9;padding:12px;border-radius:8px;min-width:200px;font-family:system-ui;">
          <div style="font-weight:600;font-size:13px;margin-bottom:8px;color:${color};">${bus.id}</div>
          <div style="font-size:12px;margin-bottom:4px;"><span style="color:#94a3b8;">Driver: </span>${bus.driver}</div>
          <div style="font-size:12px;margin-bottom:4px;"><span style="color:#94a3b8;">Route: </span>${bus.route}</div>
          <div style="font-size:12px;margin-bottom:4px;"><span style="color:#94a3b8;">Passengers: </span>${bus.passengers}/${bus.capacity}</div>
          <div style="font-size:12px;margin-bottom:4px;"><span style="color:#94a3b8;">ETA: </span>${bus.eta_minutes} min (${bus.distance_km} km)</div>
          <div style="font-size:12px;margin-bottom:4px;"><span style="color:#94a3b8;">Speed: </span>${bus.speed_kmh} km/h</div>
          <div style="font-size:12px;margin-top:8px;padding:6px;border-radius:6px;background:${color}20;color:${color};font-weight:500;">${bus.alert_message}</div>
          ${bus.held ? `<div style="font-size:11px;margin-top:6px;color:#ef4444;font-weight:600;">HELD AT CHECKPOINT</div>` : ''}
        </div>`

        if (markersRef.current.buses[bus.id]) {
          // UPDATE existing marker position
          markersRef.current.buses[bus.id].setLatLng([bus.lat, bus.lng])
          markersRef.current.buses[bus.id].setIcon(busIcon)
          markersRef.current.buses[bus.id].setPopupContent(popupContent)
        } else {
          // CREATE new marker
          const marker = L.marker([bus.lat, bus.lng], { icon: busIcon }).addTo(leafletMap.current)
          marker.bindPopup(popupContent)
          markersRef.current.buses[bus.id] = marker
          console.log(`[MAP] Bus marker added: ${bus.id} at [${bus.lat}, ${bus.lng}]`)
        }
      })
    })
  }, [busData])   // Re-runs every time busData updates

  return (
    <div style={{ position: 'relative', width: '100%' }}>
      {/* Map container */}
      <div
        ref={mapRef}
        style={{
          width: '100%',
          height: '520px',
          borderRadius: '12px',
          overflow: 'hidden',
          border: '1px solid #334155',
          background: '#0f172a'
        }}
      />

      {/* Legend */}
      <div style={{
        position: 'absolute',
        bottom: '16px',
        left: '16px',
        background: 'rgba(15,23,42,0.92)',
        border: '1px solid #334155',
        borderRadius: '8px',
        padding: '10px 14px',
        zIndex: 1000,
        display: 'flex',
        flexDirection: 'column',
        gap: '6px'
      }}>
        {[
          { color: '#8B5CF6', label: 'Temple' },
          { color: '#3B82F6', label: 'Police Station' },
          { color: '#ef4444', label: 'Choke Point' },
          { color: '#22c55e', label: 'Bus (Normal)' },
          { color: '#f59e0b', label: 'Bus (Caution)' },
          { color: '#ef4444', label: 'Bus (Held)' },
        ].map(({ color, label }) => (
          <div key={label} style={{
            display: 'flex',
            alignItems: 'center',
            gap: '8px',
            fontSize: '11px',
            color: '#94a3b8'
          }}>
            <div style={{
              width: '10px',
              height: '10px',
              borderRadius: '50%',
              background: color,
              flexShrink: 0
            }} />
            {label}
          </div>
        ))}
      </div>

      {/* Bus count badge */}
      <div style={{
        position: 'absolute',
        top: '12px',
        right: '12px',
        background: 'rgba(15,23,42,0.92)',
        border: '1px solid #334155',
        borderRadius: '8px',
        padding: '6px 12px',
        zIndex: 1000,
        fontSize: '12px',
        color: '#94a3b8',
        display: 'flex',
        alignItems: 'center',
        gap: '8px'
      }}>
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="#f59e0b" strokeWidth="1.5">
          <rect x="1" y="3" width="15" height="13" rx="2"/>
          <path d="M16 8h4l3 3v4h-7V8z"/>
          <circle cx="5.5" cy="18.5" r="2.5"/>
          <circle cx="18.5" cy="18.5" r="2.5"/>
        </svg>
        {busData.length} buses tracked
        {busData.filter(b => b.held).length > 0 && (
          <span style={{
            color: '#ef4444',
            fontWeight: 600
          }}>
            · {busData.filter(b => b.held).length} held
          </span>
        )}
      </div>
    </div>
  )
}