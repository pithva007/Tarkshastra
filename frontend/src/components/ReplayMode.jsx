import React, { useMemo } from 'react'
import {
  AreaChart, Area, XAxis, YAxis, CartesianGrid,
  Tooltip, ReferenceLine, ResponsiveContainer, ReferenceDot,
} from 'recharts'
import PressureGauge from './PressureGauge'
import { useReplay } from '../hooks/useReplay'

const SPEEDS = [1, 2, 4]

export default function ReplayMode() {
  const {
    frames, cursor, playing, speed, loaded, current,
    setCursor, togglePlay, setSpeed, reset,
  } = useReplay()

  // Find landmark frames
  const predFrame = useMemo(() => frames.findIndex((f) => f.prediction_fired), [frames])
  const peakFrame = useMemo(() => frames.findIndex((f) => f.crush_peak), [frames])

  // Sliding window for chart (last 80 frames)
  const chartData = useMemo(
    () => frames.slice(Math.max(0, cursor - 79), cursor + 1),
    [frames, cursor]
  )

  const predLabel = predFrame >= 0 ? frames[predFrame]?.timestamp_label : null
  const peakLabel = peakFrame >= 0 ? frames[peakFrame]?.timestamp_label : null

  if (!loaded) {
    return (
      <div className="flex items-center justify-center h-64 text-gray-400 text-sm">
        Loading replay data…
      </div>
    )
  }

  if (!frames.length) {
    return (
      <div className="text-red-400 text-center py-12">
        Replay data unavailable — is the backend running?
      </div>
    )
  }

  const isCritical = current?.surge_type === 'GENUINE_CRUSH'
  const isPredicted = current?.surge_type === 'PREDICTED_BREACH'
  const ttbMin = current?.time_to_breach_seconds
    ? (current.time_to_breach_seconds / 60).toFixed(1)
    : null

  return (
    <div className="space-y-5">
      {/* Title */}
      <div className="flex items-center justify-between flex-wrap gap-2">
        <div>
          <h2 className="text-lg font-bold text-white">Replay — Near-Crush Scenario</h2>
          <p className="text-xs text-gray-400">Ambaji Corridor · 20-min timeline · {frames.length} frames @ 5s</p>
        </div>
        <div className="flex gap-2 flex-wrap">
          {current?.prediction_fired && (
            <span className="bg-amber-900 border border-amber-600 text-amber-300 text-xs font-bold px-3 py-1 rounded-full animate-pulse flex items-center gap-1">
              <svg width="11" height="11" viewBox="0 0 24 24" fill="currentColor"><polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2"/></svg>
              PREDICTION FIRED — 10 min lead
            </span>
          )}
          {current?.crush_peak && (
            <span className="bg-red-900 border border-red-600 text-red-300 text-xs font-bold px-3 py-1 rounded-full animate-pulse flex items-center gap-1">
              <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round"><circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/></svg>
              CRUSH PEAK
            </span>
          )}
        </div>
      </div>

      {/* Stat cards */}
      {current && (
        <div className="grid grid-cols-2 md:grid-cols-5 gap-2">
          <Stat label="Time"      value={current.timestamp_label} />
          <Stat label="CPI"       value={current.cpi?.toFixed(3)}        hi={current.cpi > 0.75} />
          <Stat label="TTB"       value={ttbMin ? `${ttbMin} min` : '—'}  hi={ttbMin != null && ttbMin <= 12} />
          <Stat label="Flow"      value={`${current.flow_rate} /min`} />
          <Stat label="Phase"     value={current.phase?.toUpperCase()} />
        </div>
      )}

      {/* Gauge + Alert */}
      <div className="flex flex-col md:flex-row gap-5 items-center">
        <PressureGauge cpi={current?.cpi ?? 0} size={210} label={current?.corridor ?? ''} />

        {(isCritical || isPredicted || current?.prediction_fired) && (
          <div className={`flex-1 rounded-xl p-4 border ${
            isCritical
              ? 'bg-red-950 border-red-700'
              : 'bg-amber-950 border-amber-700'
          }`}>
            {current.prediction_fired && (
              <p className="text-xs text-amber-400 font-bold uppercase tracking-widest mb-2 flex items-center gap-1">
                <svg width="11" height="11" viewBox="0 0 24 24" fill="currentColor"><polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2"/></svg>
                Prediction fired — {(peakFrame - predFrame) * 5}s before peak
              </p>
            )}
            <p className={`text-base font-bold ${isCritical ? 'text-red-300' : 'text-amber-300'}`}>
              {current.alert_message}
            </p>
            {isPredicted && ttbMin && (
              <p className="text-sm text-gray-300 mt-2">
                Slope-based prediction: crush in <strong className="text-amber-300">{ttbMin} min</strong>.
                Algorithm detected rising CPI trend before visible crush.
              </p>
            )}
          </div>
        )}
      </div>

      {/* Timeline chart */}
      <div className="bg-gray-900 rounded-xl p-4">
        <p className="text-xs text-gray-400 uppercase tracking-wide mb-3">
          CPI Timeline — last {chartData.length} frames
        </p>
        <ResponsiveContainer width="100%" height={190}>
          <AreaChart data={chartData} margin={{ top: 8, right: 8, left: -22, bottom: 0 }}>
            <defs>
              <linearGradient id="rg" x1="0" y1="0" x2="0" y2="1">
                <stop offset="5%"  stopColor="#f59e0b" stopOpacity={0.45} />
                <stop offset="95%" stopColor="#f59e0b" stopOpacity={0.02} />
              </linearGradient>
            </defs>
            <CartesianGrid strokeDasharray="3 3" stroke="#1f2937" />
            <XAxis dataKey="timestamp_label" tick={{ fontSize: 9, fill: '#6b7280' }} interval="preserveStartEnd" />
            <YAxis domain={[0, 1]} tick={{ fontSize: 9, fill: '#6b7280' }} />
            <Tooltip
              contentStyle={{ background: '#111827', border: '1px solid #374151', borderRadius: 8, fontSize: 12 }}
              labelStyle={{ color: '#9ca3af' }}
            />

            {/* Breach threshold */}
            <ReferenceLine y={0.85} stroke="#ef4444" strokeDasharray="4 3"
              label={{ value: 'BREACH 0.85', fill: '#ef4444', fontSize: 9, position: 'insideTopRight' }} />
            <ReferenceLine y={0.70} stroke="#f59e0b" strokeDasharray="2 4"
              label={{ value: '0.70', fill: '#f59e0b', fontSize: 9, position: 'insideTopRight' }} />

            {/* PREDICTION FIRED vertical line */}
            {predLabel && cursor >= predFrame && (
              <ReferenceLine x={predLabel} stroke="#f59e0b" strokeDasharray="3 2"
                label={{ value: 'PREDICTION', fill: '#f59e0b', fontSize: 9, position: 'insideTopLeft', angle: -90 }} />
            )}

            {/* CRUSH PEAK vertical line */}
            {peakLabel && cursor >= peakFrame && (
              <ReferenceLine x={peakLabel} stroke="#ef4444" strokeWidth={2}
                label={{ value: 'PEAK', fill: '#ef4444', fontSize: 9, position: 'insideTopLeft', angle: -90 }} />
            )}

            <Area type="monotone" dataKey="cpi" stroke="#f59e0b" fill="url(#rg)"
              strokeWidth={2} dot={false} isAnimationActive={false} />
          </AreaChart>
        </ResponsiveContainer>
      </div>

      {/* Scrubber */}
      <div className="space-y-1.5">
        <div className="flex justify-between text-xs text-gray-500">
          <span>00:00</span>
          <span className="font-mono font-bold text-white">
            {current?.timestamp_label}  ({cursor + 1} / {frames.length})
          </span>
          <span>20:00</span>
        </div>

        {/* Landmark markers above slider */}
        <div className="relative h-4">
          {predFrame >= 0 && (
            <div
              className="absolute top-0 flex flex-col items-center"
              style={{ left: `${(predFrame / (frames.length - 1)) * 100}%`, transform: 'translateX(-50%)' }}
            >
              <div className="w-px h-4 bg-amber-500" />
              <span className="text-[9px] text-amber-400 whitespace-nowrap">PRED</span>
            </div>
          )}
          {peakFrame >= 0 && (
            <div
              className="absolute top-0 flex flex-col items-center"
              style={{ left: `${(peakFrame / (frames.length - 1)) * 100}%`, transform: 'translateX(-50%)' }}
            >
              <div className="w-px h-4 bg-red-500" />
              <span className="text-[9px] text-red-400 whitespace-nowrap">PEAK</span>
            </div>
          )}
        </div>

        <input
          type="range" min={0} max={frames.length - 1} value={cursor}
          onChange={(e) => setCursor(Number(e.target.value))}
          className="w-full accent-amber-500 cursor-pointer"
        />
      </div>

      {/* Controls */}
      <div className="flex items-center gap-2 justify-center flex-wrap">
        <button onClick={reset}
          className="px-4 py-2 bg-gray-700 hover:bg-gray-600 rounded-lg text-sm font-medium transition-colors flex items-center gap-1.5">
          <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round"><polygon points="19 20 9 12 19 4 19 20"/><line x1="5" y1="19" x2="5" y2="5"/></svg>
          Reset
        </button>
        <button onClick={togglePlay}
          className={`px-8 py-2 rounded-lg text-sm font-bold transition-colors flex items-center gap-1.5 ${
            playing ? 'bg-amber-600 hover:bg-amber-700' : 'bg-green-600 hover:bg-green-700'
          }`}>
          {playing ? (
            <><svg width="13" height="13" viewBox="0 0 24 24" fill="currentColor"><rect x="6" y="4" width="4" height="16"/><rect x="14" y="4" width="4" height="16"/></svg>Pause</>
          ) : (
            <><svg width="13" height="13" viewBox="0 0 24 24" fill="currentColor"><polygon points="5 3 19 12 5 21 5 3"/></svg>Play</>
          )}
        </button>
        {SPEEDS.map((s) => (
          <button key={s} onClick={() => setSpeed(s)}
            className={`px-3 py-2 rounded-lg text-xs font-bold transition-colors ${
              speed === s ? 'bg-blue-600 text-white' : 'bg-gray-700 text-gray-300 hover:bg-gray-600'
            }`}>
            {s}×
          </button>
        ))}
        <button
          onClick={() => predFrame >= 0 && setCursor(predFrame)}
          className="px-3 py-2 bg-amber-900 hover:bg-amber-800 text-amber-300 rounded-lg text-xs font-bold transition-colors"
        >
          Jump to Prediction
        </button>
        <button
          onClick={() => peakFrame >= 0 && setCursor(peakFrame)}
          className="px-3 py-2 bg-red-900 hover:bg-red-800 text-red-300 rounded-lg text-xs font-bold transition-colors"
        >
          Jump to Peak
        </button>
      </div>
    </div>
  )
}

function Stat({ label, value, hi = false }) {
  return (
    <div className={`rounded-lg p-3 ${hi ? 'bg-red-950 border border-red-700' : 'bg-gray-800'}`}>
      <p className="text-xs text-gray-400 uppercase tracking-wide truncate">{label}</p>
      <p className={`text-base font-bold font-mono ${hi ? 'text-red-300' : 'text-white'}`}>{value ?? '—'}</p>
    </div>
  )
}
