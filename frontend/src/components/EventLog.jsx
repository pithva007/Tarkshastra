import React, { useEffect, useState } from 'react'
import axios from 'axios'
import { Sparklines, SparklinesLine, SparklinesReferenceLine } from 'recharts'
import {
  LineChart, Line, ResponsiveContainer, Tooltip,
} from 'recharts'

const API = import.meta.env.VITE_API_URL || 'http://localhost:8000'

const SURGE_COLORS = {
  GENUINE_CRUSH:    'bg-red-900 text-red-300',
  PREDICTED_BREACH: 'bg-amber-900 text-amber-300',
  HIGH_PRESSURE:    'bg-orange-900 text-orange-300',
  SELF_RESOLVING:   'bg-blue-900 text-blue-300',
  NORMAL:           'bg-gray-800 text-gray-400',
}

export default function EventLog() {
  const [events,  setEvents]  = useState([])
  const [alerts,  setAlerts]  = useState([])
  const [tab,     setTab]     = useState('events') // 'events' | 'alerts'
  const [loading, setLoading] = useState(true)
  const [sortKey, setSortKey] = useState('id')
  const [sortDir, setSortDir] = useState('desc')

  const fetchAll = () => {
    Promise.all([
      axios.get(`${API}/api/events?limit=50`),
      axios.get(`${API}/api/alerts?limit=50`),
    ]).then(([ev, al]) => {
      setEvents(ev.data.events || [])
      setAlerts(al.data.alerts || [])
      setLoading(false)
    }).catch(() => setLoading(false))
  }

  useEffect(() => {
    fetchAll()
    const t = setInterval(fetchAll, 10000)
    return () => clearInterval(t)
  }, [])

  const handleSort = (key) => {
    if (sortKey === key) setSortDir((d) => d === 'asc' ? 'desc' : 'asc')
    else { setSortKey(key); setSortDir('desc') }
  }

  const sorted = (arr) =>
    [...arr].sort((a, b) => {
      const va = a[sortKey], vb = b[sortKey]
      if (va == null) return 1
      if (vb == null) return -1
      return sortDir === 'asc' ? (va > vb ? 1 : -1) : (va < vb ? 1 : -1)
    })

  const cpiColor = (v) =>
    v > 0.75 ? 'text-red-400' : v > 0.40 ? 'text-amber-400' : 'text-green-400'

  const SortHdr = ({ k, children }) => (
    <th
      onClick={() => handleSort(k)}
      className="pb-2 pr-3 cursor-pointer select-none hover:text-white whitespace-nowrap"
    >
      {children} {sortKey === k ? (sortDir === 'asc' ? '▲' : '▼') : ''}
    </th>
  )

  const exportCSV = () => {
    window.open(`${API}/api/events/export`, '_blank')
  }

  return (
    <div className="space-y-4">
      {/* Toolbar */}
      <div className="flex items-center justify-between flex-wrap gap-3">
        <div className="flex gap-1">
          {['events', 'alerts'].map((t) => (
            <button key={t} onClick={() => setTab(t)}
              className={`px-4 py-1.5 rounded-lg text-sm font-medium transition-colors ${
                tab === t ? 'bg-gray-700 text-white' : 'text-gray-400 hover:text-white'
              }`}>
              {t === 'events' ? `CPI Log (${events.length})` : `Alerts (${alerts.length})`}
            </button>
          ))}
        </div>
        <div className="flex gap-2">
          <button onClick={fetchAll}
            className="text-xs text-blue-400 hover:text-blue-300 px-3 py-1.5 rounded-lg bg-gray-800 transition-colors">
            ↻ Refresh
          </button>
          <button onClick={exportCSV}
            className="text-xs text-green-400 hover:text-green-300 px-3 py-1.5 rounded-lg bg-gray-800 transition-colors">
            ⬇ Export CSV
          </button>
        </div>
      </div>

      {loading ? (
        <p className="text-gray-400 text-sm text-center py-12">Loading…</p>
      ) : tab === 'events' ? (
        /* ── CPI Log table ── */
        events.length === 0 ? (
          <p className="text-gray-500 text-sm text-center py-12">No CPI events logged yet.</p>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm text-left">
              <thead className="text-xs text-gray-400 uppercase tracking-wide border-b border-gray-700">
                <tr>
                  <SortHdr k="logged_at">Time</SortHdr>
                  <SortHdr k="corridor">Corridor</SortHdr>
                  <SortHdr k="cpi">CPI</SortHdr>
                  <SortHdr k="flow_rate">Flow /min</SortHdr>
                  <SortHdr k="surge_type">Surge Type</SortHdr>
                  <SortHdr k="alert_fired">Alert</SortHdr>
                </tr>
              </thead>
              <tbody>
                {sorted(events).map((ev) => (
                  <tr key={ev.id} className="border-b border-gray-800 hover:bg-gray-800/30 transition-colors">
                    <td className="py-2 pr-3 font-mono text-xs text-gray-400">
                      {new Date(ev.logged_at).toLocaleTimeString()}
                    </td>
                    <td className="py-2 pr-3 font-medium text-white">{ev.corridor}</td>
                    <td className="py-2 pr-3">
                      <span className={`font-mono font-bold ${cpiColor(ev.cpi)}`}>
                        {Number(ev.cpi).toFixed(3)}
                      </span>
                    </td>
                    <td className="py-2 pr-3 font-mono text-xs text-gray-300">
                      {ev.flow_rate?.toFixed(0)}
                    </td>
                    <td className="py-2 pr-3">
                      <span className={`text-xs font-bold px-2 py-0.5 rounded-full ${SURGE_COLORS[ev.surge_type] || SURGE_COLORS.NORMAL}`}>
                        {ev.surge_type}
                      </span>
                    </td>
                    <td className="py-2">
                      {ev.alert_fired
                        ? <span className="bg-red-900 text-red-300 text-xs px-2 py-0.5 rounded-full">FIRED</span>
                        : <span className="text-gray-600 text-xs">—</span>
                      }
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )
      ) : (
        /* ── Alerts table ── */
        alerts.length === 0 ? (
          <p className="text-gray-500 text-sm text-center py-12">No alerts logged yet.</p>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm text-left">
              <thead className="text-xs text-gray-400 uppercase tracking-wide border-b border-gray-700">
                <tr>
                  <SortHdr k="fired_at">Fired At</SortHdr>
                  <SortHdr k="corridor">Corridor</SortHdr>
                  <SortHdr k="cpi">CPI</SortHdr>
                  <SortHdr k="surge_type">Type</SortHdr>
                  <th className="pb-2 pr-3">Police Ack</th>
                  <th className="pb-2 pr-3">Temple Ack</th>
                  <th className="pb-2">GSRTC Ack</th>
                </tr>
              </thead>
              <tbody>
                {sorted(alerts).map((al) => (
                  <tr key={al.id} className="border-b border-gray-800 hover:bg-gray-800/30">
                    <td className="py-2 pr-3 font-mono text-xs text-gray-400">
                      {new Date(al.fired_at).toLocaleTimeString()}
                    </td>
                    <td className="py-2 pr-3 font-medium text-white">{al.corridor}</td>
                    <td className="py-2 pr-3">
                      <span className={`font-mono font-bold ${cpiColor(al.cpi)}`}>
                        {Number(al.cpi).toFixed(3)}
                      </span>
                    </td>
                    <td className="py-2 pr-3">
                      <span className={`text-xs font-bold px-2 py-0.5 rounded-full ${SURGE_COLORS[al.surge_type] || SURGE_COLORS.NORMAL}`}>
                        {al.surge_type}
                      </span>
                    </td>
                    <td className="py-2 pr-3">{ackCell(al.police_ack)}</td>
                    <td className="py-2 pr-3">{ackCell(al.temple_ack)}</td>
                    <td className="py-2">{ackCell(al.gsrtc_ack)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )
      )}
    </div>
  )
}

function ackCell(ts) {
  if (!ts) return <span className="text-amber-400 text-xs font-semibold">Pending</span>
  return (
    <span className="text-green-400 text-xs font-mono">
      ✓ {new Date(ts).toLocaleTimeString()}
    </span>
  )
}
