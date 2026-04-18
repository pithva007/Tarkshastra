import React from 'react'

/**
 * Animated SVG arc pressure gauge.
 *
 * Props:
 *   cpi                 — 0.0 to 1.0 (undefined/null shows 0.00 with LOW label)
 *   size                — pixel width/height (default 240)
 *   corridor            — corridor name shown below value
 *   surgeType           — surge classification string
 *   timeToBreachMinutes — number or null
 */
export default function PressureGauge({
  cpi,
  size = 240,
  corridor = '',
  surgeType,
  timeToBreachMinutes,
}) {
  // Safe value — never crash on undefined/null/NaN
  const safeCpi = (cpi != null && !isNaN(cpi)) ? Math.max(0, Math.min(1, Number(cpi))) : 0

  const cx = size / 2
  const cy = size * 0.52
  const r  = size * 0.36
  const sw = size * 0.095

  const START_DEG = 200
  const SWEEP     = 220

  const toXY = (deg) => {
    const rad = ((deg - 90) * Math.PI) / 180
    return { x: cx + r * Math.cos(rad), y: cy + r * Math.sin(rad) }
  }

  const arc = (from, to) => {
    if (Math.abs(to - from) < 0.01) return ''
    const s = toXY(from)
    const e = toXY(to)
    const large = (to - from) > 180 ? 1 : 0
    return `M ${s.x} ${s.y} A ${r} ${r} 0 ${large} 1 ${e.x} ${e.y}`
  }

  const fillEnd  = START_DEG + SWEEP * safeCpi
  const trackEnd = START_DEG + SWEEP

  const greenEnd = START_DEG + SWEEP * 0.40
  const amberEnd = START_DEG + SWEEP * 0.70

  const activeColor = safeCpi < 0.40 ? '#22c55e' : safeCpi < 0.70 ? '#f59e0b' : '#ef4444'
  const glowColor   = safeCpi < 0.40 ? '#16a34a' : safeCpi < 0.70 ? '#d97706' : '#dc2626'
  const riskLabel   = safeCpi < 0.40 ? 'LOW' : safeCpi < 0.70 ? 'ELEVATED' : 'CRITICAL'

  // Time to breach display
  let breachLine = null
  if (cpi != null && cpi > 0) {
    if (timeToBreachMinutes != null) {
      const mins = Math.floor(timeToBreachMinutes)
      const secs = Math.round((timeToBreachMinutes - mins) * 60)
      breachLine = `⚠ Crush risk in ${mins}m ${secs}s`
    } else {
      breachLine = 'Safe — monitoring'
    }
  }

  return (
    <div className="flex flex-col items-center select-none">
      <svg
        width={size}
        height={size * 0.78}
        viewBox={`0 0 ${size} ${size * 0.78}`}
        aria-label={`Pressure gauge: CPI ${safeCpi.toFixed(3)}`}
      >
        {/* Background track */}
        <path d={arc(START_DEG, trackEnd)} fill="none" stroke="#1f2937" strokeWidth={sw} strokeLinecap="round" />

        {/* Zone tints */}
        <path d={arc(START_DEG, greenEnd)} fill="none" stroke="#14532d" strokeWidth={sw} strokeLinecap="butt" opacity={0.35} />
        <path d={arc(greenEnd, amberEnd)} fill="none" stroke="#78350f" strokeWidth={sw} strokeLinecap="butt" opacity={0.35} />
        <path d={arc(amberEnd, trackEnd)} fill="none" stroke="#7f1d1d" strokeWidth={sw} strokeLinecap="butt" opacity={0.35} />

        {/* Active fill */}
        {safeCpi > 0.005 && (
          <path
            d={arc(START_DEG, fillEnd)}
            fill="none"
            stroke={activeColor}
            strokeWidth={sw}
            strokeLinecap="round"
            style={{
              transition: 'all 0.55s cubic-bezier(0.4, 0, 0.2, 1)',
              filter: `drop-shadow(0 0 ${size * 0.025}px ${glowColor})`,
            }}
          />
        )}

        {/* Tick marks */}
        {[0, 0.40, 0.70, 1.0].map((v) => {
          const deg = START_DEG + SWEEP * v
          const rad2 = ((deg - 90) * Math.PI) / 180
          return (
            <line
              key={v}
              x1={cx + (r - sw * 0.8) * Math.cos(rad2)}
              y1={cy + (r - sw * 0.8) * Math.sin(rad2)}
              x2={cx + (r + sw * 0.3) * Math.cos(rad2)}
              y2={cy + (r + sw * 0.3) * Math.sin(rad2)}
              stroke="#4b5563"
              strokeWidth={1.5}
            />
          )
        })}

        {/* CPI value */}
        <text
          x={cx} y={cy - r * 0.08}
          textAnchor="middle"
          fill={activeColor}
          fontSize={size * 0.18}
          fontWeight="bold"
          fontFamily="monospace"
          style={{ transition: 'fill 0.4s' }}
        >
          {safeCpi.toFixed(3)}
        </text>

        {/* Risk label */}
        <text
          x={cx} y={cy + r * 0.22}
          textAnchor="middle"
          fill={activeColor}
          fontSize={size * 0.068}
          fontWeight="700"
          letterSpacing="3"
          style={{ transition: 'fill 0.4s' }}
        >
          {riskLabel}
        </text>

        {/* Scale labels */}
        <text x={toXY(START_DEG).x - 2} y={toXY(START_DEG).y + 14} textAnchor="middle" fill="#4b5563" fontSize={size * 0.045}>0.0</text>
        <text x={toXY(trackEnd).x + 2}  y={toXY(trackEnd).y + 14}  textAnchor="middle" fill="#4b5563" fontSize={size * 0.045}>1.0</text>
      </svg>

      {corridor && (
        <p className="text-xs font-semibold tracking-widest text-gray-400 -mt-1">{corridor}</p>
      )}

      {breachLine && (
        <p className={`text-xs mt-2 font-medium ${timeToBreachMinutes != null ? 'text-red-400' : 'text-green-400'}`}>
          {breachLine}
        </p>
      )}
    </div>
  )
}
