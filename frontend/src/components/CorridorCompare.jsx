import React from 'react'

const SURGE_BADGE = {
  GENUINE_CRUSH:    'bg-red-900 text-red-300 border-red-700',
  PREDICTED_BREACH: 'bg-amber-900 text-amber-300 border-amber-700',
  HIGH_PRESSURE:    'bg-orange-900 text-orange-300 border-orange-700',
  SELF_RESOLVING:   'bg-blue-900 text-blue-300 border-blue-700',
  NORMAL:           'bg-gray-800 text-gray-400 border-gray-700',
}

// Mini SVG arc gauge (180° semicircle, opens upward)
function MiniArc({ cpi }) {
  const v     = Math.max(0, Math.min(cpi || 0, 1))
  const r     = 34
  const cx    = 50
  const cy    = 50
  const color = v > 0.70 ? '#ef4444' : v > 0.40 ? '#f59e0b' : '#22c55e'

  // Background arc: full semicircle from (16,50) to (84,50)
  // Active arc: from (16,50) to endpoint at angle π - v*π
  const ex = cx - r * Math.cos(v * Math.PI)
  const ey = cy - r * Math.sin(v * Math.PI)

  return (
    <svg width="100" height="56" viewBox="0 0 100 56">
      {/* Track */}
      <path
        d="M 16 50 A 34 34 0 0 1 84 50"
        fill="none" stroke="#374151" strokeWidth="7" strokeLinecap="round"
      />
      {/* Active fill */}
      {v > 0.005 && (
        <path
          d={`M 16 50 A 34 34 0 0 1 ${ex.toFixed(2)} ${ey.toFixed(2)}`}
          fill="none"
          stroke={color}
          strokeWidth="7"
          strokeLinecap="round"
          style={{ transition: 'all 0.5s ease' }}
        />
      )}
      {/* Value text */}
      <text
        x="50" y="44"
        textAnchor="middle"
        fill={color}
        fontSize="13"
        fontWeight="bold"
        fontFamily="monospace"
        style={{ transition: 'fill 0.4s' }}
      >
        {v.toFixed(2)}
      </text>
    </svg>
  )
}

function CorridorCell({ reading, isHighest, onClick }) {
  if (!reading) return (
    <div className="bg-gray-900 rounded-xl p-4 border border-gray-700 flex items-center justify-center min-h-[140px]">
      <p className="text-gray-600 text-xs">No data</p>
    </div>
  )

  const { corridor, cpi, surge_type, ml_confidence, ml_risk_level } = reading
  const borderClass = isHighest
    ? 'border-red-600 animate-pulse ring-2 ring-red-500'
    : cpi > 0.70
    ? 'border-red-700'
    : cpi > 0.40
    ? 'border-amber-700'
    : 'border-green-800'

  const badge = SURGE_BADGE[surge_type] || SURGE_BADGE.NORMAL

  return (
    <button
      onClick={onClick}
      className={`bg-gray-900 rounded-xl p-3 border transition-all text-left w-full ${borderClass} hover:bg-gray-800`}
    >
      {/* Header */}
      <div className="flex items-center justify-between mb-1">
        <p className="text-xs font-bold text-white tracking-wide">{corridor}</p>
        {isHighest && (
          <span className="text-xs bg-red-900 text-red-300 px-1.5 py-0.5 rounded-full font-bold">
            HIGHEST RISK
          </span>
        )}
      </div>

      {/* Mini arc gauge */}
      <div className="flex justify-center -my-1">
        <MiniArc cpi={cpi} />
      </div>

      {/* Surge badge */}
      {surge_type && surge_type !== 'NORMAL' && (
        <div className="flex justify-center mt-1 mb-1">
          <span className={`text-xs font-bold px-2 py-0.5 rounded-full border ${badge}`}>
            {surge_type.replace('_', ' ')}
          </span>
        </div>
      )}

      {/* ML confidence */}
      {ml_confidence != null && (
        <p className="text-center text-xs text-gray-400 mt-1">
          ML: <span className="text-blue-300 font-mono font-bold">{ml_confidence}%</span>
          {ml_risk_level && (
            <span className={`ml-1 ${
              ml_risk_level === 'CRITICAL' ? 'text-red-400' :
              ml_risk_level === 'HIGH'     ? 'text-orange-400' :
              ml_risk_level === 'MEDIUM'   ? 'text-amber-400' : 'text-green-400'
            }`}>· {ml_risk_level}</span>
          )}
        </p>
      )}
    </button>
  )
}

export default function CorridorCompare({ readings = [], onSelect }) {
  // Sort by CPI descending — highest risk floats to top-left
  const sorted = [...readings].sort((a, b) => (b.cpi ?? 0) - (a.cpi ?? 0))

  const highestCorridor = sorted[0]?.corridor

  // Fill to exactly 4 cells
  while (sorted.length < 4) sorted.push(null)

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between">
        <p className="text-xs font-bold text-gray-300 uppercase tracking-wide">
          All Corridors — Live Comparison
        </p>
        <p className="text-xs text-gray-500">Sorted by risk · Updates every 2s</p>
      </div>

      <div className="grid grid-cols-2 gap-3">
        {sorted.map((r, i) =>
          r ? (
            <CorridorCell
              key={r.corridor}
              reading={r}
              isHighest={r.corridor === highestCorridor && r.cpi > 0.40}
              onClick={() => onSelect?.(r.corridor)}
            />
          ) : (
            <div key={i} className="bg-gray-900 rounded-xl border border-gray-800 min-h-[140px]" />
          )
        )}
      </div>
    </div>
  )
}
