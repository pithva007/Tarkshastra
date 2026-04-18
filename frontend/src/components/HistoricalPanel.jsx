import { useState, useEffect } from 'react'
import axios from 'axios'

const API = import.meta.env.VITE_API_URL || 'http://localhost:8000'

function riskColor(prob) {
  if (prob >= 60) return { bg: 'bg-red-950 border-red-700', text: 'text-red-300', badge: 'bg-red-700 text-red-100', label: 'HIGH RISK' }
  if (prob >= 35) return { bg: 'bg-amber-950 border-amber-700', text: 'text-amber-300', badge: 'bg-amber-600 text-amber-100', label: 'MEDIUM RISK' }
  return { bg: 'bg-green-950 border-green-700', text: 'text-green-300', badge: 'bg-green-700 text-green-100', label: 'LOW RISK' }
}

function cpiSeverityColor(cpi) {
  if (cpi >= 0.85) return 'text-red-400'
  if (cpi >= 0.70) return 'text-orange-400'
  if (cpi >= 0.55) return 'text-amber-400'
  return 'text-green-400'
}

function surgeTypeBadge(type) {
  if (type === 'GENUINE_CRUSH') return 'bg-red-900 text-red-300'
  if (type === 'SELF_RESOLVING') return 'bg-blue-900 text-blue-300'
  return 'bg-gray-800 text-gray-300'
}

/**
 * HistoricalPanel — shows historical risk analysis and seasonal predictions.
 *
 * Props:
 *   corridor — currently selected corridor name
 */
export default function HistoricalPanel({ corridor = 'Ambaji' }) {
  const [prediction, setPrediction] = useState(null)
  const [incidents, setIncidents]   = useState([])
  const [expanded, setExpanded]     = useState(null)
  const [loading, setLoading]       = useState(false)

  useEffect(() => {
    if (!corridor) return
    setLoading(true)

    Promise.all([
      axios.get(`${API}/api/prediction/seasonal/${corridor}`),
      axios.get(`${API}/api/historical/${corridor}`),
    ])
      .then(([predRes, histRes]) => {
        setPrediction(predRes.data)
        setIncidents(histRes.data.incidents || [])
      })
      .catch(() => {
        setPrediction(null)
        setIncidents([])
      })
      .finally(() => setLoading(false))
  }, [corridor])

  if (loading) {
    return (
      <div className="flex items-center justify-center py-16 text-gray-500 text-sm">
        Loading historical data…
      </div>
    )
  }

  if (!prediction) {
    return (
      <div className="flex items-center justify-center py-16 text-gray-500 text-sm">
        No historical data available for {corridor}.
      </div>
    )
  }

  const risk = riskColor(prediction.probability_of_surge)
  const yearsCount = new Set(incidents.map((i) => i.year)).size

  return (
    <div className="space-y-5">

      {/* ── Section 1: Current Risk ── */}
      <div className={`rounded-2xl border p-5 ${risk.bg}`}>
        <div className="flex items-start justify-between gap-4 flex-wrap">
          <div>
            <span className={`inline-block text-xs font-bold px-3 py-1 rounded-full mb-3 ${risk.badge}`}>
              {risk.label}
            </span>
            <p className={`text-3xl font-black ${risk.text}`}>
              {prediction.probability_of_surge}%
            </p>
            <p className="text-gray-300 text-sm mt-1">
              chance of surge in next 2 hours
            </p>
            <p className="text-gray-500 text-xs mt-1">
              Based on {yearsCount > 0 ? yearsCount : '—'} years of Navratri data
            </p>
          </div>
          <div className="text-right">
            <p className="text-xs text-gray-400 uppercase tracking-wide">Expected Peak</p>
            <p className={`text-lg font-bold font-mono ${risk.text}`}>
              {prediction.expected_peak_time}
            </p>
            {prediction.buses_to_hold_preemptively > 0 && (
              <p className="text-xs text-amber-400 mt-1">
                Hold {prediction.buses_to_hold_preemptively} buses preemptively
              </p>
            )}
          </div>
        </div>

        <div className="mt-4 bg-black/20 rounded-xl p-3">
          <p className="text-xs text-gray-400 uppercase tracking-wide mb-1">AI Prediction</p>
          <p className="text-sm text-gray-200 leading-relaxed">{prediction.prediction}</p>
        </div>
      </div>

      {/* ── Section 2: Seasonal Prediction Card ── */}
      {prediction.similar_year && (
        <div className="bg-gray-900 rounded-2xl border border-gray-700 p-5">
          <p className="text-xs text-gray-400 uppercase tracking-wide mb-3">
            Seasonal Pattern — {prediction.similar_year} Match
          </p>

          {incidents
            .filter((i) => i.year === prediction.similar_year)
            .slice(0, 1)
            .map((inc, idx) => (
              <div key={idx} className="space-y-2">
                <div className="flex items-center gap-2">
                  <span className="text-amber-400 font-bold text-sm">In {inc.year}</span>
                  <span className="text-gray-500 text-xs">same corridor at this time:</span>
                </div>
                <p className="text-sm text-gray-300">
                  CPI peaked at{' '}
                  <span className={`font-bold font-mono ${cpiSeverityColor(inc.peak_cpi)}`}>
                    {inc.peak_cpi}
                  </span>{' '}
                  during <span className="text-white">{inc.peak_time}</span>
                </p>
                <p className="text-xs text-gray-400 italic">"{inc.incident}"</p>
              </div>
            ))}

          <div className="mt-4 bg-amber-950/40 border border-amber-800/40 rounded-xl p-3">
            <p className="text-xs text-amber-400 uppercase tracking-wide mb-1">Recommended Pre-Action</p>
            <p className="text-sm text-gray-200 leading-relaxed">{prediction.recommendation}</p>
          </div>
        </div>
      )}

      {/* ── Section 3: Historical Timeline ── */}
      <div className="bg-gray-900 rounded-2xl border border-gray-700 p-5">
        <p className="text-xs text-gray-400 uppercase tracking-wide mb-4">
          Historical Incidents — {corridor}
        </p>

        {incidents.length === 0 ? (
          <p className="text-gray-500 text-sm text-center py-4">No recorded incidents</p>
        ) : (
          <div className="space-y-2">
            {incidents.map((inc, idx) => (
              <div key={idx}>
                {/* Row */}
                <button
                  onClick={() => setExpanded(expanded === idx ? null : idx)}
                  className="w-full text-left rounded-xl bg-gray-800 hover:bg-gray-750 border border-gray-700 px-4 py-3 transition-colors"
                >
                  <div className="flex items-center gap-3 flex-wrap">
                    <span className="text-gray-400 text-xs font-mono w-10">{inc.year}</span>
                    <span className="text-gray-300 text-xs">{inc.date_label}</span>
                    <span className={`font-bold font-mono text-sm ${cpiSeverityColor(inc.peak_cpi)}`}>
                      CPI {inc.peak_cpi}
                    </span>
                    <span className={`text-xs px-2 py-0.5 rounded-full font-semibold ${surgeTypeBadge(inc.surge_type)}`}>
                      {inc.surge_type?.replace('_', ' ')}
                    </span>
                    <span className="text-gray-500 text-xs ml-auto">
                      {inc.resolution_time_minutes} min resolution
                    </span>
                    <span className="text-gray-500 text-xs">{expanded === idx ? '▲' : '▼'}</span>
                  </div>
                </button>

                {/* Expanded detail */}
                {expanded === idx && (
                  <div className="mx-2 bg-gray-800/60 border border-gray-700 border-t-0 rounded-b-xl px-4 py-3 space-y-2">
                    <div className="grid grid-cols-2 gap-3 text-xs">
                      <div>
                        <p className="text-gray-500 uppercase tracking-wide">Peak Time</p>
                        <p className="text-white font-medium">{inc.peak_time}</p>
                      </div>
                      <div>
                        <p className="text-gray-500 uppercase tracking-wide">Pilgrims Affected</p>
                        <p className="text-white font-medium">{inc.pilgrims_affected?.toLocaleString()}</p>
                      </div>
                      <div>
                        <p className="text-gray-500 uppercase tracking-wide">Buses Held</p>
                        <p className="text-white font-medium">{inc.buses_held}</p>
                      </div>
                      <div>
                        <p className="text-gray-500 uppercase tracking-wide">Resolution</p>
                        <p className="text-white font-medium">{inc.resolution_time_minutes} min</p>
                      </div>
                    </div>
                    <div>
                      <p className="text-gray-500 text-xs uppercase tracking-wide">Incident</p>
                      <p className="text-gray-300 text-xs mt-0.5">{inc.incident}</p>
                    </div>
                    <div>
                      <p className="text-gray-500 text-xs uppercase tracking-wide">Action Taken</p>
                      <p className="text-green-300 text-xs mt-0.5">{inc.action_taken}</p>
                    </div>
                  </div>
                )}
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}
