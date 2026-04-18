import React, { useState, useEffect } from 'react'
import axios from 'axios'
import {
  LineChart, Line, XAxis, YAxis, CartesianGrid,
  Tooltip, ReferenceLine, ResponsiveContainer,
} from 'recharts'

import { useWebSocket }    from './hooks/useWebSocket'
import PressureGauge       from './components/PressureGauge'
import AgencyPanel         from './components/AgencyPanel'
import AlertBanner         from './components/AlertBanner'
import ReplayMode          from './components/ReplayMode'
import CorridorMap         from './components/CorridorMap'
import EventLog            from './components/EventLog'
import WhatIfSimulator     from './components/WhatIfSimulator'
import CorridorCompare     from './components/CorridorCompare'

const API      = import.meta.env.VITE_API_URL || 'http://localhost:8000'
const CORRIDORS = ['Ambaji', 'Dwarka', 'Somnath', 'Pavagadh']
const AGENCIES  = ['police', 'temple', 'gsrtc']
const TABS      = ['Dashboard', 'Compare', 'Map', 'Replay', 'Events']

const AGENCY_LABELS = { police: 'Police', temple: 'Temple Trust', gsrtc: 'GSRTC' }

// Read URL param
const param = (key) => new URLSearchParams(window.location.search).get(key)

// ── Colour helpers ─────────────────────────────────────────────────────────────
const cpiColor  = (v) => v == null ? 'text-gray-400' : v >= 0.70 ? 'text-red-400' : v >= 0.40 ? 'text-amber-400' : 'text-green-400'
const cpiBorder = (v) => v == null ? 'border-gray-700' : v >= 0.70 ? 'border-red-600' : v >= 0.40 ? 'border-amber-600' : 'border-green-600'
const cpiRing   = (v, sel) => sel ? `ring-2 ${v >= 0.70 ? 'ring-red-500' : v >= 0.40 ? 'ring-amber-500' : 'ring-green-500'}` : ''

// ── Connection status badge ────────────────────────────────────────────────────
function ConnectionBadge({ status, retryCount }) {
  if (status === 'connected') {
    return (
      <span className="flex items-center gap-1.5 text-gray-400 text-xs">
        <span className="w-2 h-2 rounded-full bg-green-400" />
        Live
      </span>
    )
  }
  if (status === 'connecting') {
    return (
      <span className="flex items-center gap-1.5 text-gray-400 text-xs">
        <span className="w-2 h-2 rounded-full bg-amber-400 animate-pulse" />
        Reconnecting...
      </span>
    )
  }
  // disconnected / failed
  return (
    <span className="flex items-center gap-1.5 text-gray-400 text-xs">
      <span className="w-2 h-2 rounded-full bg-red-500" />
      {retryCount >= 5 ? 'Offline' : 'Disconnected'}
    </span>
  )
}

// ── ML Confidence Badge ────────────────────────────────────────────────────────
function ConfidenceBadge({ surgeType, confidence, riskLevel }) {
  if (!surgeType || surgeType === 'SAFE') return null
  const label = surgeType === 'GENUINE_CRUSH' ? 'GENUINE CRUSH'
    : surgeType === 'SELF_RESOLVING' ? 'SELF RESOLVING'
    : surgeType.replace(/_/g, ' ')
  const style =
    riskLevel === 'CRITICAL' ? 'bg-red-900 text-red-200 border-red-700' :
    riskLevel === 'HIGH'     ? 'bg-orange-900 text-orange-200 border-orange-700' :
    riskLevel === 'MEDIUM'   ? 'bg-amber-900 text-amber-200 border-amber-700' :
                               'bg-green-900 text-green-200 border-green-700'
  return (
    <div className={`inline-flex items-center gap-1.5 text-xs font-bold px-3 py-1 rounded-full border ${style}`}>
      <span>{label}</span>
      {confidence != null && <span className="opacity-75">· {confidence}% confident</span>}
    </div>
  )
}

// ── App ────────────────────────────────────────────────────────────────────────
export default function App() {
  const agency = param('agency')

  const [tab,       setTab]      = useState('Dashboard')
  const [selectedCorridor, setSelectedCorridor] = useState('Ambaji')
  const [backendOk, setBackendOk] = useState(null)

  const { corridorData, corridorHistory, connectionStatus, lastUpdate, retryCount } = useWebSocket()

  useEffect(() => {
    axios.get(`${API}/health`)
      .then(() => setBackendOk(true))
      .catch(() => setBackendOk(false))
  }, [])

  const current     = corridorData[selectedCorridor] || null
  const currentHist = corridorHistory[selectedCorridor] || []
  const allReadings = Object.values(corridorData)

  return (
    <div className="min-h-screen bg-gray-950 text-white">

      <AlertBanner readings={allReadings} />

      {/* ── Header ── */}
      <header className="bg-gray-900 border-b border-gray-800 sticky top-0 z-40">
        <div className="max-w-7xl mx-auto px-4 py-3 flex items-center justify-between gap-4">
          <div className="flex items-center gap-3 min-w-0">
            <span className="text-xl flex-shrink-0">🔮</span>
            <div className="min-w-0">
              <h1 className="text-sm font-bold text-white tracking-wide truncate">
                Stampede Window Predictor — TS-11
                {agency && (
                  <span className="ml-2 text-amber-400">
                    [{AGENCY_LABELS[agency] || agency}]
                  </span>
                )}
              </h1>
              <p className="text-xs text-gray-500">Gujarat Pilgrimage Corridors · Navratri</p>
            </div>
          </div>

          <div className="flex items-center gap-3 flex-shrink-0 text-xs">
            <span className="hidden sm:flex items-center gap-1.5 text-gray-400">
              <span className={`w-2 h-2 rounded-full ${
                backendOk === null ? 'bg-gray-400 animate-pulse' : backendOk ? 'bg-green-400' : 'bg-red-400'
              }`} />
              {backendOk === null ? 'Waking…' : backendOk ? 'Backend OK' : 'Backend Down'}
            </span>

            <ConnectionBadge status={connectionStatus} retryCount={retryCount} />

            {!agency && (
              <div className="hidden md:flex gap-1">
                {AGENCIES.map((ag) => (
                  <a key={ag} href={`?agency=${ag}`}
                    className="px-2 py-1 rounded bg-gray-800 hover:bg-gray-700 text-gray-300 text-xs transition-colors capitalize">
                    {ag}
                  </a>
                ))}
              </div>
            )}

            <button
              onClick={() => setTab('Compare')}
              className="hidden md:block px-2 py-1 rounded bg-indigo-900 hover:bg-indigo-800 text-indigo-300 text-xs transition-colors font-medium"
            >
              Compare All
            </button>
          </div>
        </div>

        {/* Tabs */}
        <div className="max-w-7xl mx-auto px-4 flex">
          {TABS.map((t) => (
            <button key={t} onClick={() => setTab(t)}
              className={`px-4 py-2.5 text-sm font-medium border-b-2 transition-colors ${
                tab === t
                  ? 'border-amber-500 text-amber-400'
                  : 'border-transparent text-gray-400 hover:text-white'
              }`}>
              {t}
            </button>
          ))}
        </div>
      </header>

      {/* ── Main ── */}
      <main className="max-w-7xl mx-auto px-4 py-6 space-y-6">

        {/* Corridor selector */}
        {tab !== 'Events' && tab !== 'Compare' && (
          <div className="flex gap-2 flex-wrap">
            {CORRIDORS.map((c) => {
              const r   = corridorData[c]
              const cpi = r?.cpi
              return (
                <button key={c} onClick={() => setSelectedCorridor(c)}
                  className={`flex-1 min-w-[5rem] rounded-xl py-2.5 px-3 text-sm font-medium border transition-all ${
                    selectedCorridor === c
                      ? `${cpiBorder(cpi)} bg-gray-800 ${cpiRing(cpi, true)}`
                      : 'border-gray-700 bg-gray-900 text-gray-400 hover:bg-gray-800'
                  }`}>
                  <span className="block">{c}</span>
                  {cpi != null && (
                    <span className={`font-mono text-xs ${cpiColor(cpi)}`}>
                      {cpi.toFixed(3)}
                    </span>
                  )}
                </button>
              )
            })}
          </div>
        )}

        {/* ═══════════ DASHBOARD ═══════════ */}
        {tab === 'Dashboard' && (
          <div className="space-y-6">

            {/* Row: gauge + metrics */}
            <div className="grid grid-cols-1 lg:grid-cols-3 gap-5">

              {/* Gauge card */}
              <div className={`rounded-2xl p-5 flex flex-col items-center justify-center bg-gray-900 border ${
                current?.cpi >= 0.70 ? 'border-red-700' : current?.cpi >= 0.40 ? 'border-amber-700' : 'border-gray-700'
              }`}>
                <PressureGauge
                  cpi={current?.cpi}
                  corridor={selectedCorridor}
                  surgeType={current?.surge_type}
                  timeToBreachMinutes={current?.time_to_breach_minutes}
                />

                {current && (
                  <div className="mt-3">
                    <ConfidenceBadge
                      surgeType={current.surge_type}
                      confidence={current.ml_confidence}
                      riskLevel={current.ml_risk_level}
                    />
                  </div>
                )}
              </div>

              {/* Metrics grid */}
              <div className="lg:col-span-2 grid grid-cols-2 md:grid-cols-3 gap-3">
                <Metric label="CPI"
                  value={current?.cpi?.toFixed(3) ?? '—'}
                  sub="0 = safe · 1 = crush"
                  accent={current?.cpi >= 0.70 ? 'red' : current?.cpi >= 0.40 ? 'amber' : 'green'} />
                <Metric label="Time to Breach"
                  value={current?.time_to_breach_seconds != null
                    ? `${Math.floor(current.time_to_breach_seconds / 60)}m ${current.time_to_breach_seconds % 60 | 0}s`
                    : '—'}
                  sub="at CPI = 0.85"
                  accent={current?.time_to_breach_seconds != null && current.time_to_breach_seconds < 720 ? 'red' : 'neutral'} />
                <Metric label="Flow Rate"
                  value={current?.flow_rate != null ? `${Math.round(current.flow_rate)}/min` : '—'}
                  sub="pax per minute"
                  accent="neutral" />
                <Metric label="Transport Burst"
                  value={current?.transport_burst?.toFixed(3) ?? '—'}
                  sub="0–1 bus load factor"
                  accent={current?.transport_burst > 0.7 ? 'amber' : 'neutral'} />
                <Metric label="Chokepoint Density"
                  value={current?.chokepoint_density?.toFixed(3) ?? '—'}
                  sub="normalised 0–1"
                  accent={current?.chokepoint_density > 0.7 ? 'amber' : 'neutral'} />
                <Metric label="ML Risk"
                  value={current?.ml_risk_level ?? '—'}
                  sub={current?.ml_confidence != null ? `${current.ml_confidence}% confidence` : 'no model'}
                  accent={
                    current?.ml_risk_level === 'CRITICAL' ? 'red' :
                    current?.ml_risk_level === 'HIGH'     ? 'amber' :
                    current?.ml_risk_level === 'MEDIUM'   ? 'amber' : 'green'
                  } />
              </div>
            </div>

            {/* Alert inline */}
            {current?.alert_active && (
              <div className={`rounded-xl p-4 flex items-start gap-3 border ${
                current.surge_type === 'GENUINE_CRUSH'
                  ? 'bg-red-950 border-red-700 animate-pulse'
                  : 'bg-amber-950 border-amber-700'
              }`}>
                <span className="text-2xl">{current.surge_type === 'GENUINE_CRUSH' ? '🚨' : '⚠️'}</span>
                <div>
                  <p className={`font-bold text-sm ${current.surge_type === 'GENUINE_CRUSH' ? 'text-red-300' : 'text-amber-300'}`}>
                    {current.surge_type === 'GENUINE_CRUSH'
                      ? `CRITICAL: Genuine crush developing in ${selectedCorridor}`
                      : current.time_to_breach_seconds != null
                      ? `WARNING: Breach predicted in ${Math.ceil(current.time_to_breach_seconds / 60)} min — ${selectedCorridor}`
                      : `ALERT: High pressure in ${selectedCorridor}`
                    }
                  </p>
                  <p className="text-xs text-gray-400 mt-0.5">
                    ID: {current.alert_id} · CPI {current.cpi?.toFixed(3)}
                    {current.ml_confidence != null && ` · ML: ${current.ml_confidence}% · ${current.ml_risk_level}`}
                  </p>
                </div>
              </div>
            )}

            {/* Live CPI chart */}
            <div className="bg-gray-900 rounded-xl p-4">
              <p className="text-xs text-gray-400 uppercase tracking-wide mb-3">
                Live CPI — {selectedCorridor} (last {currentHist.length} readings)
              </p>
              <ResponsiveContainer width="100%" height={160}>
                <LineChart data={currentHist} margin={{ top: 4, right: 6, left: -24, bottom: 0 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#1f2937" />
                  <XAxis dataKey="t" tick={false} />
                  <YAxis domain={[0, 1]} tick={{ fontSize: 10, fill: '#6b7280' }} />
                  <Tooltip contentStyle={{ background: '#111827', border: '1px solid #374151', borderRadius: 8, fontSize: 11 }} />
                  <ReferenceLine y={0.85} stroke="#ef4444" strokeDasharray="4 3" />
                  <ReferenceLine y={0.70} stroke="#f59e0b" strokeDasharray="2 4" />
                  <ReferenceLine y={0.40} stroke="#22c55e" strokeDasharray="2 4" />
                  <Line type="monotone" dataKey="cpi" stroke="#f59e0b" strokeWidth={2} dot={false} isAnimationActive={false} />
                </LineChart>
              </ResponsiveContainer>
            </div>

            {/* Agency panels */}
            <div>
              <h2 className="text-sm font-bold text-gray-300 uppercase tracking-wide mb-3">
                {agency ? `${AGENCY_LABELS[agency]} — Action Panel` : '3-Agency Coordination Centre'}
              </h2>
              <div className={`grid gap-4 ${agency ? 'grid-cols-1 max-w-lg' : 'grid-cols-1 md:grid-cols-3'}`}>
                {(agency ? [agency] : AGENCIES).map((ag) => (
                  <AgencyPanel
                    key={ag}
                    agency={ag}
                    corridorData={corridorData}
                    selectedCorridor={selectedCorridor}
                  />
                ))}
              </div>
            </div>

            <WhatIfSimulator />
          </div>
        )}

        {/* ═══════════ COMPARE ═══════════ */}
        {tab === 'Compare' && (
          <CorridorCompare
            readings={allReadings}
            onSelect={(c) => { setSelectedCorridor(c); setTab('Dashboard') }}
          />
        )}

        {/* ═══════════ MAP ═══════════ */}
        {tab === 'Map' && (
          <div className="space-y-4">
            <CorridorMap readings={allReadings} selected={selectedCorridor} onSelect={setSelectedCorridor} />
            <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
              {CORRIDORS.map((c) => {
                const r   = corridorData[c]
                const cpi = r?.cpi
                return (
                  <button key={c} onClick={() => setSelectedCorridor(c)}
                    className={`rounded-xl p-3 text-left border transition-all ${cpiBorder(cpi)} ${
                      selectedCorridor === c ? 'bg-gray-800 ring-2 ring-white' : 'bg-gray-900'
                    }`}>
                    <p className="text-xs text-gray-400">{c}</p>
                    <p className={`text-2xl font-bold font-mono ${cpiColor(cpi)}`}>
                      {cpi?.toFixed(3) ?? '…'}
                    </p>
                    {r?.surge_type && r.surge_type !== 'SAFE' && (
                      <p className="text-xs text-amber-400 mt-1">{r.surge_type}</p>
                    )}
                    {r?.ml_confidence != null && (
                      <p className="text-xs text-blue-400 mt-0.5">ML: {r.ml_confidence}%</p>
                    )}
                  </button>
                )
              })}
            </div>
          </div>
        )}

        {/* ═══════════ REPLAY ═══════════ */}
        {tab === 'Replay' && <ReplayMode />}

        {/* ═══════════ EVENTS ═══════════ */}
        {tab === 'Events' && <EventLog />}

      </main>
    </div>
  )
}

// ── Sub-components ─────────────────────────────────────────────────────────────
function Metric({ label, value, sub, accent = 'neutral' }) {
  const colors = { red: 'text-red-400', amber: 'text-amber-400', green: 'text-green-400', neutral: 'text-white' }
  return (
    <div className="bg-gray-900 rounded-xl p-3.5">
      <p className="text-xs text-gray-500 uppercase tracking-wide truncate">{label}</p>
      <p className={`text-xl font-bold font-mono mt-1 ${colors[accent]}`}>{value}</p>
      <p className="text-xs text-gray-600 mt-0.5 truncate">{sub}</p>
    </div>
  )
}
