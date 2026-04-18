import React, { useState, useEffect, useRef, useCallback } from 'react'
import axios from 'axios'

const API = import.meta.env.VITE_API_URL || 'http://localhost:8000'

const CORRIDORS = ['Ambaji', 'Dwarka', 'Somnath', 'Pavagadh']

const PRESETS = {
  'buses': {
    label: '4 buses arrive simultaneously',
    flow_rate: 700,
    transport_burst: 0.90,
    chokepoint_density: 0.75,
  },
  'navratri': {
    label: 'Peak Navratri scenario',
    flow_rate: 1800,
    transport_burst: 0.95,
    chokepoint_density: 0.95,
  },
}

const SURGE_STYLE = {
  GENUINE_CRUSH:  'bg-red-900 text-red-300 border-red-700',
  SELF_RESOLVING: 'bg-amber-900 text-amber-300 border-amber-700',
  SAFE:           'bg-green-900 text-green-300 border-green-700',
}

function cpiColor(v) {
  if (v == null) return 'text-gray-400'
  if (v > 0.70) return 'text-red-400'
  if (v > 0.40) return 'text-amber-400'
  return 'text-green-400'
}

function CpiBar({ cpi }) {
  const pct  = Math.round((cpi || 0) * 100)
  const fill  = cpi > 0.70 ? '#ef4444' : cpi > 0.40 ? '#f59e0b' : '#22c55e'
  return (
    <div className="w-full bg-gray-700 rounded-full h-2 mt-1">
      <div
        className="h-2 rounded-full transition-all duration-300"
        style={{ width: `${pct}%`, background: fill }}
      />
    </div>
  )
}

export default function WhatIfSimulator() {
  const [open,     setOpen]     = useState(false)
  const [corridor, setCorridor] = useState('Ambaji')
  const [flowRate, setFlowRate] = useState(300)
  const [transport, setTransport] = useState(0.30)
  const [density,  setDensity]  = useState(0.35)
  const [result,   setResult]   = useState(null)
  const [loading,  setLoading]  = useState(false)
  const [error,    setError]    = useState(null)
  const debounceRef = useRef(null)

  const runSim = useCallback(() => {
    setLoading(true)
    setError(null)
    axios.post(`${API}/api/simulate`, {
      corridor,
      flow_rate:          flowRate,
      transport_burst:    transport,
      chokepoint_density: density,
    })
      .then((r) => { setResult(r.data); setLoading(false) })
      .catch((e) => { setError('Simulation failed'); setLoading(false) })
  }, [corridor, flowRate, transport, density])

  // Debounce slider changes 300ms
  useEffect(() => {
    if (!open) return
    clearTimeout(debounceRef.current)
    debounceRef.current = setTimeout(runSim, 300)
    return () => clearTimeout(debounceRef.current)
  }, [corridor, flowRate, transport, density, open, runSim])

  const applyPreset = (key) => {
    const p = PRESETS[key]
    setFlowRate(p.flow_rate)
    setTransport(p.transport_burst)
    setDensity(p.chokepoint_density)
  }

  const ttbLabel = (s) => {
    if (s == null) return '—'
    if (s === 0)   return 'BREACH NOW'
    const m = Math.floor(s / 60)
    const sec = s % 60
    return `${m}m ${sec}s`
  }

  return (
    <div className="bg-gray-900 rounded-xl border border-gray-700 overflow-hidden">
      {/* Header / toggle */}
      <button
        onClick={() => setOpen((o) => !o)}
        className="w-full flex items-center justify-between px-4 py-3 hover:bg-gray-800 transition-colors"
      >
        <div className="flex items-center gap-2">
          <span className="text-amber-400 text-sm font-bold">⚡ What-If Simulator</span>
          <span className="text-gray-500 text-xs">— Pure calculation, no live effect</span>
        </div>
        <span className="text-gray-400 text-xs">{open ? '▲ Collapse' : '▼ Expand'}</span>
      </button>

      {open && (
        <div className="px-4 pb-4 space-y-4 border-t border-gray-800 pt-4">
          {/* Corridor + Presets row */}
          <div className="flex flex-wrap items-center gap-2">
            <select
              value={corridor}
              onChange={(e) => setCorridor(e.target.value)}
              className="bg-gray-800 border border-gray-600 text-white text-xs rounded-lg px-3 py-1.5 focus:outline-none"
            >
              {CORRIDORS.map((c) => <option key={c}>{c}</option>)}
            </select>
            {Object.entries(PRESETS).map(([key, p]) => (
              <button
                key={key}
                onClick={() => applyPreset(key)}
                className="text-xs px-3 py-1.5 rounded-lg bg-gray-800 border border-gray-600 text-amber-300 hover:bg-gray-700 transition-colors"
              >
                {key === 'buses' ? '🚌' : '🎪'} {p.label}
              </button>
            ))}
          </div>

          {/* Sliders */}
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            <SliderCard
              label="Flow Rate"
              unit="pax/min"
              min={0} max={2000} step={10}
              value={flowRate}
              onChange={setFlowRate}
            />
            <SliderCard
              label="Transport Burst"
              unit=""
              min={0} max={1} step={0.01}
              value={transport}
              onChange={setTransport}
              decimals={2}
            />
            <SliderCard
              label="Chokepoint Density"
              unit=""
              min={0} max={1} step={0.01}
              value={density}
              onChange={setDensity}
              decimals={2}
            />
          </div>

          {/* Result */}
          <div className="bg-gray-800 rounded-xl p-4 min-h-[80px] flex items-center">
            {loading && (
              <p className="text-gray-400 text-sm animate-pulse">Computing…</p>
            )}
            {error && !loading && (
              <p className="text-red-400 text-sm">{error}</p>
            )}
            {result && !loading && (
              <div className="w-full grid grid-cols-2 md:grid-cols-4 gap-4">
                {/* CPI */}
                <div>
                  <p className="text-xs text-gray-500 uppercase tracking-wide">Predicted CPI</p>
                  <p className={`text-2xl font-bold font-mono mt-1 ${cpiColor(result.cpi)}`}>
                    {result.cpi?.toFixed(3)}
                  </p>
                  <CpiBar cpi={result.cpi} />
                </div>

                {/* Surge type */}
                <div>
                  <p className="text-xs text-gray-500 uppercase tracking-wide mb-1">Surge Type</p>
                  <span className={`text-xs font-bold px-2 py-1 rounded-full border ${SURGE_STYLE[result.surge_type] || 'bg-gray-700 text-gray-300'}`}>
                    {result.surge_type?.replace('_', ' ')}
                  </span>
                </div>

                {/* TTB */}
                <div>
                  <p className="text-xs text-gray-500 uppercase tracking-wide">Time to Breach</p>
                  <p className={`text-xl font-bold font-mono mt-1 ${
                    result.time_to_breach_seconds != null && result.time_to_breach_seconds < 600
                      ? 'text-red-400' : 'text-gray-300'
                  }`}>
                    {ttbLabel(result.time_to_breach_seconds)}
                  </p>
                </div>

                {/* Confidence */}
                <div>
                  <p className="text-xs text-gray-500 uppercase tracking-wide">ML Confidence</p>
                  <p className="text-xl font-bold font-mono mt-1 text-blue-300">
                    {result.ml_confidence != null ? `${result.ml_confidence}%` : '—'}
                  </p>
                </div>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  )
}

function SliderCard({ label, unit, min, max, step, value, onChange, decimals = 0 }) {
  const pct = ((value - min) / (max - min)) * 100
  const fill = value / max > 0.70 ? '#ef4444' : value / max > 0.40 ? '#f59e0b' : '#22c55e'
  return (
    <div className="space-y-1">
      <div className="flex justify-between items-baseline">
        <p className="text-xs text-gray-400 uppercase tracking-wide">{label}</p>
        <p className="text-xs font-mono text-white font-bold">
          {decimals > 0 ? value.toFixed(decimals) : value}
          {unit && <span className="text-gray-500 ml-1">{unit}</span>}
        </p>
      </div>
      <input
        type="range"
        min={min}
        max={max}
        step={step}
        value={value}
        onChange={(e) => onChange(decimals > 0 ? parseFloat(e.target.value) : parseInt(e.target.value))}
        className="w-full h-1.5 rounded-full appearance-none cursor-pointer bg-gray-700"
        style={{
          background: `linear-gradient(to right, ${fill} ${pct}%, #374151 ${pct}%)`,
        }}
      />
    </div>
  )
}
