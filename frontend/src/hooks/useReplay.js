import { useState, useEffect, useRef, useCallback } from 'react'
import axios from 'axios'

const API = import.meta.env.VITE_API_URL || 'http://localhost:8000'

/**
 * Manages replay playback state.
 *
 * Returns:
 *   frames        — full array of replay frame objects
 *   cursor        — current frame index
 *   playing       — boolean
 *   speed         — 1 | 2 | 4
 *   loaded        — boolean
 *   current       — frames[cursor] (convenience)
 *   setCursor     — jump to frame index
 *   togglePlay    — play / pause
 *   setSpeed      — change playback speed
 *   reset         — jump to frame 0 and pause
 */
export function useReplay() {
  const [frames,  setFrames]  = useState([])
  const [cursor,  setCursor]  = useState(0)
  const [playing, setPlaying] = useState(false)
  const [speed,   setSpeed]   = useState(1)
  const [loaded,  setLoaded]  = useState(false)

  const intervalRef = useRef(null)

  // Load all frames once on mount
  useEffect(() => {
    axios.get(`${API}/api/replay/all`)
      .then(({ data }) => {
        setFrames(data.frames || [])
        setLoaded(true)
      })
      .catch(() => setLoaded(true))
  }, [])

  // Playback interval — each real-world frame represents 5 s of scenario time
  // At 1×: advance 1 frame every 500 ms (10× faster than real-time, good for demo)
  const tick = useCallback(() => {
    setCursor((c) => {
      if (c >= frames.length - 1) {
        setPlaying(false)
        return c
      }
      return c + 1
    })
  }, [frames.length])

  useEffect(() => {
    clearInterval(intervalRef.current)
    if (playing && frames.length > 0) {
      intervalRef.current = setInterval(tick, Math.round(500 / speed))
    }
    return () => clearInterval(intervalRef.current)
  }, [playing, speed, tick, frames.length])

  const togglePlay = useCallback(() => {
    setPlaying((p) => {
      // If at end, restart
      if (!p && cursor >= frames.length - 1) setCursor(0)
      return !p
    })
  }, [cursor, frames.length])

  const reset = useCallback(() => {
    setPlaying(false)
    setCursor(0)
  }, [])

  const jumpTo = useCallback((idx) => {
    setPlaying(false)
    setCursor(Math.max(0, Math.min(idx, frames.length - 1)))
  }, [frames.length])

  return {
    frames,
    cursor,
    playing,
    speed,
    loaded,
    current: frames[cursor] || null,
    setCursor: jumpTo,
    togglePlay,
    setSpeed,
    reset,
  }
}
