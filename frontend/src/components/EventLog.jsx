import React, { useEffect, useState } from 'react'
import axios from 'axios'

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
  const [tab,     setTab]     = useState('events')
  const [loading, setLoading] = useState(true)
  const [sortKey, setSortKey] = useState('id')
  const [sortDir, setSortDir] = useState('desc')

  const [reportAlert,   setReportAlert]   = useState(null)
  const [report,        setReport]        = useState(null)
  const [reportLoading, setReportLoading] = useState(false)

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

  const isFullyAcked = (al) => Boolean(al.police_ack && al.temple_ack && al.gsrtc_ack)

  const openReport = (al) => {
    setReportAlert(al)
    setReport(null)
    setReportLoading(true)
    axios.get(`${API}/api/report/${al.alert_id}`)
      .then((r) => { setReport(r.data); setReportLoading(false) })
      .catch(() => { setReport({ error: 'Failed to fetch report' }); setReportLoading(false) })
  }

  const exportCSV = () => window.open(`${API}/api/events/export`, '_blank')

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
                  <th className="pb-2 pr-3">GSRTC Ack</th>
                  <th className="pb-2">Report</th>
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
                    <td className="py-2 pr-3">{ackCell(al.gsrtc_ack)}</td>
                    <td className="py-2">
                      {isFullyAcked(al) ? (
                        <button
                          onClick={() => openReport(al)}
                          className="text-xs bg-indigo-900 text-indigo-300 hover:bg-indigo-800 border border-indigo-700 px-2 py-0.5 rounded-full font-semibold transition-colors"
                        >
                          📋 Report
                        </button>
                      ) : (
                        <span className="text-gray-600 text-xs">—</span>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )
      )}

      {/* ── Incident Report Modal ── */}
      {reportAlert && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70">
          <div className="bg-gray-900 border border-gray-700 rounded-2xl p-6 w-full max-w-lg shadow-2xl">
            {/* Header */}
            <div className="flex items-center justify-between mb-4">
              <h2 className="text-sm font-bold text-white uppercase tracking-wide">
                📋 Incident Report
              </h2>
              <div className="flex gap-2">
                <button
                  onClick={() => window.print()}
                  className="text-xs bg-gray-700 hover:bg-gray-600 text-white px-3 py-1.5 rounded-lg transition-colors"
                >
                  🖨 Print
                </button>
                <button
                  onClick={() => { setReportAlert(null); setReport(null) }}
                  className="text-xs text-gray-400 hover:text-white px-3 py-1.5 rounded-lg bg-gray-800"
                >
                  ✕ Close
                </button>
              </div>
            </div>

            {reportLoading && (
              <p className="text-center text-gray-400 text-sm py-8 animate-pulse">Loading report…</p>
            )}

            {report && !reportLoading && report.error && (
              <p className="text-red-400 text-sm text-center py-8">{report.error}</p>
            )}

            {report && !reportLoading && !report.error && (
              <div className="space-y-2.5 text-sm" id="incident-report">
                <p className="text-gray-500 text-xs uppercase tracking-widest mb-3">
                  TS-11 Stampede Window Predictor — Formal Incident Summary
                </p>
                <ReportRow label="Alert ID"      value={report.alert_id} mono />
                <ReportRow label="Corridor"       value={report.corridor} />
                <ReportRow label="Surge Type"     value={report.surge_type} accent />
                <ReportRow label="Peak CPI"       value={report.peak_cpi?.toFixed(3)} mono accent />
                <ReportRow label="ML Confidence"  value={report.ml_confidence != null ? `${report.ml_confidence}%` : 'N/A'} />
                <div className="border-t border-gray-700 pt-2.5 mt-2.5 space-y-2.5">
                  <ReportRow label="Alert Fired At" value={fmtTime(report.fired_at)} />
                  <ReportRow label="Police Ack"     value={fmtTime(report.police_ack_time) || 'Pending'} />
                  <ReportRow label="Temple Ack"     value={fmtTime(report.temple_ack_time) || 'Pending'} />
                  <ReportRow label="GSRTC Ack"      value={fmtTime(report.gsrtc_ack_time) || 'Pending'} />
                </div>
                <div className="border-t border-gray-700 pt-2.5 mt-2.5 space-y-2.5">
                  <ReportRow
                    label="Duration"
                    value={report.duration_seconds != null
                      ? `${Math.floor(report.duration_seconds / 60)}m ${report.duration_seconds % 60}s`
                      : '—'}
                  />
                  <ReportRow label="Resolved At" value={fmtTime(report.resolved_at) || '—'} />
                  <ReportRow label="Outcome"     value={report.outcome} accent />
                </div>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  )
}

function ReportRow({ label, value, mono = false, accent = false }) {
  return (
    <div className="flex justify-between items-center">
      <span className="text-gray-400 text-xs uppercase tracking-wide">{label}</span>
      <span className={`text-xs font-semibold ${mono ? 'font-mono' : ''} ${accent ? 'text-amber-300' : 'text-white'}`}>
        {value ?? '—'}
      </span>
    </div>
  )
}

function fmtTime(iso) {
  if (!iso) return null
  try { return new Date(iso).toLocaleString() } catch { return iso }
}

function ackCell(ts) {
  if (!ts) return <span className="text-amber-400 text-xs font-semibold">Pending</span>
  return (
    <span className="text-green-400 text-xs font-mono">
      ✓ {new Date(ts).toLocaleTimeString()}
    </span>
  )
}
