import React, { useState, useEffect, useRef } from 'react'

const API = import.meta.env.VITE_API_URL || 'http://localhost:8000'

const CORRIDORS = ['Ambaji', 'Dwarka', 'Somnath', 'Pavagadh']

const CORRIDOR_WIDTH = {
  Ambaji:   4,
  Dwarka:   3,
  Somnath:  5,
  Pavagadh: 2.5
}

export default function VisionUpload({
  onVisionData,
  connectionStatus,
  wsData          // latest WebSocket message from App
}) {
  const [expanded, setExpanded] = useState(false)
  const [corridor, setCorridor] = useState('Ambaji')
  const [file, setFile] = useState(null)
  const [uploading, setUploading] = useState(false)
  const [processing, setProcessing] = useState(false)
  const [progress, setProgress] = useState(0)
  const [liveCount, setLiveCount] = useState(null)
  const [flowRate, setFlowRate] = useState(null)
  const [result, setResult] = useState(null)
  const [error, setError] = useState('')
  const [status, setStatus] = useState('')
  const [visionCpi, setVisionCpi] = useState(null)
  const [visionFlowRate, setVisionFlowRate] = useState(null)
  const [triggering, setTriggering] = useState(false)
  const [triggerResult, setTriggerResult] = useState(null)
  const [isActive, setIsActive] = useState(false)

  // Frame-level progress
  const [framesRead, setFramesRead] = useState(0)
  const [framesLeft, setFramesLeft] = useState(0)
  const [totalFrames, setTotalFrames] = useState(0)

  const fileInputRef = useRef(null)

  // Listen to WebSocket messages for vision events
  useEffect(() => {
    if (!wsData) return

    if (wsData.type === 'vision_started' && wsData.corridor === corridor) {
      setProcessing(true)
      setProgress(0)
      setStatus('Starting YOLOv8 analysis...')
      setFramesRead(0)
      setFramesLeft(0)
      setTotalFrames(0)
    }

    if (wsData.type === 'vision_progress' && wsData.corridor === corridor) {
      setProgress(wsData.progress || 0)
      setLiveCount(wsData.live_count || 0)
      setFlowRate(wsData.flow_rate || 0)
      setVisionCpi(wsData.cpi || 0)
      setFramesRead(wsData.keyframe || 0)
      setFramesLeft((wsData.total_keyframes || 0) - (wsData.keyframe || 0))
      setTotalFrames(wsData.total_keyframes || 0)
      setStatus(wsData.message || 'Processing...')
    }

    if (wsData.type === 'vision_complete' && wsData.corridor === corridor) {
      const r = wsData.result || {}
      setProcessing(false)
      setProgress(100)
      setLiveCount(r.median_count || 0)
      setFlowRate(r.average_flow_rate || 0)
      setVisionCpi(r.peak_cpi || 0)
      setVisionFlowRate(r.average_flow_rate || 0)
      setIsActive(true)
      setStatus(`Complete — ${r.median_count} people detected`)
      setResult(r)
      setUploading(false)
      if (onVisionData) {
        onVisionData({ corridor, ...r })
      }
    }

    if (wsData.type === 'vision_error' && wsData.corridor === corridor) {
      setProcessing(false)
      setError(wsData.message || 'Processing failed')
      setStatus('')
      setUploading(false)
    }
  }, [wsData, corridor])

  async function handleUpload() {
    if (!file) return

    setError('')
    setUploading(true)
    setResult(null)
    setLiveCount(null)
    setFlowRate(null)
    setVisionCpi(null)
    setVisionFlowRate(null)
    setTriggerResult(null)
    setFramesRead(0)
    setFramesLeft(0)
    setTotalFrames(0)
    setIsActive(false)

    try {
      const formData = new FormData()
      formData.append('file', file)

      const width = CORRIDOR_WIDTH[corridor]
      const res = await fetch(
        `${API}/api/vision/upload` +
        `?corridor=${corridor}` +
        `&corridor_width_m=${width}`,
        { method: 'POST', body: formData }
      )

      const data = await res.json()

      if (data.status === 'processing_started') {
        setUploading(false)
        setProcessing(true)
        setProgress(0)
        setStatus(`Processing ${file.name} for ${corridor}...`)
      } else if (data.status === 'busy') {
        setError(data.message)
        setUploading(false)
      } else {
        setError(data.message || 'Upload failed')
        setUploading(false)
      }
    } catch (e) {
      setError('Upload failed — check backend connection')
      setUploading(false)
    }
  }

  async function handleClear() {
    try {
      await fetch(`${API}/api/vision/clear/${corridor}`, { method: 'DELETE' })
      setResult(null)
      setLiveCount(null)
      setFlowRate(null)
      setVisionCpi(null)
      setVisionFlowRate(null)
      setTriggerResult(null)
      setProgress(0)
      setFile(null)
      setIsActive(false)
      setStatus('Cleared — reverted to simulation')
    } catch (e) {
      setError('Clear failed')
    }
  }

  async function triggerVisionAlert() {
    setTriggering(true)
    setTriggerResult(null)
    const storedToken = localStorage.getItem('ts11_token') || ''
    try {
      const res = await fetch(`${API}/api/simulate/trigger-alert`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          token: storedToken,
          corridor,
          cpi: visionCpi,
          flow_rate: visionFlowRate,
          transport_burst: 0.75,
          chokepoint_density: 0.80,
          surge_type: 'GENUINE_CRUSH',
          ttb_minutes: 0,
          ml_confidence: 91,
          source: 'vision'
        })
      })
      const data = await res.json()
      setTriggerResult(data)
    } catch (e) {
      setTriggerResult({ status: 'error', reason: 'Connection failed' })
    } finally {
      setTriggering(false)
    }
  }

  return (
    <div style={{
      background: '#1e293b',
      border: `1px solid ${isActive ? '#22c55e' : '#334155'}`,
      borderRadius: '12px',
      marginBottom: '16px',
      overflow: 'hidden'
    }}>
      {/* Header */}
      <div
        onClick={() => setExpanded(!expanded)}
        style={{
          padding: '14px 18px',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          cursor: 'pointer',
          userSelect: 'none'
        }}
      >
        <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
          <svg width="18" height="18" viewBox="0 0 24 24"
               fill="none"
               stroke={isActive ? '#22c55e' : '#94a3b8'}
               strokeWidth="1.5">
            <path d="M15 10l4.553-2.069A1 1 0 0 1 21 8.867v6.266a1 1 0 0 1-1.447.902L15 14M3 8a2 2 0 0 1 2-2h10a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8z"/>
          </svg>
          <span style={{ fontSize: '14px', fontWeight: '600', color: '#f1f5f9' }}>
            Vision Input
          </span>
          <span style={{ fontSize: '12px', color: '#64748b' }}>
            — Upload corridor video for real crowd count
          </span>
          {isActive && (
            <span style={{
              background: '#14532d',
              color: '#86efac',
              fontSize: '11px',
              fontWeight: '600',
              padding: '2px 8px',
              borderRadius: '10px'
            }}>
              LIVE — {corridor}
            </span>
          )}
        </div>
        <svg width="16" height="16" viewBox="0 0 24 24"
             fill="none" stroke="#64748b" strokeWidth="2">
          <path d={expanded ? 'M18 15l-6-6-6 6' : 'M6 9l6 6 6-6'}/>
        </svg>
      </div>

      {expanded && (
        <div style={{ padding: '0 18px 18px', borderTop: '1px solid #334155' }}>

          {/* Active vision data badge */}
          {isActive && (
            <div style={{
              background: '#14532d',
              border: '1px solid #16a34a',
              borderRadius: '8px',
              padding: '10px 14px',
              marginTop: '14px',
              marginBottom: '12px'
            }}>
              <div style={{
                display: 'flex',
                justifyContent: 'space-between',
                alignItems: 'center',
                marginBottom: '8px'
              }}>
                <div style={{ fontSize: '12px', color: '#86efac', fontWeight: '600' }}>
                  Vision data active — {corridor}
                </div>
                <button
                  onClick={handleClear}
                  style={{
                    background: 'transparent',
                    border: '1px solid #16a34a',
                    color: '#86efac',
                    borderRadius: '4px',
                    padding: '2px 8px',
                    fontSize: '11px',
                    cursor: 'pointer'
                  }}
                >
                  Clear
                </button>
              </div>

              <div style={{
                display: 'grid',
                gridTemplateColumns: '1fr 1fr 1fr',
                gap: '8px',
                marginBottom: visionCpi >= 0.75 ? '10px' : 0
              }}>
                {[
                  { label: 'People counted', value: liveCount || 0, color: '#86efac' },
                  { label: 'Flow rate', value: `${flowRate || 0}/min`, color: '#86efac' },
                  {
                    label: 'Vision CPI',
                    value: visionCpi ? visionCpi.toFixed(3) : '0.000',
                    color: visionCpi >= 0.85 ? '#ef4444' : visionCpi >= 0.70 ? '#f59e0b' : '#86efac'
                  }
                ].map(item => (
                  <div key={item.label} style={{
                    background: '#0f172a',
                    borderRadius: '6px',
                    padding: '8px',
                    textAlign: 'center'
                  }}>
                    <div style={{ fontSize: '16px', fontWeight: '700', color: item.color }}>
                      {item.value}
                    </div>
                    <div style={{ fontSize: '10px', color: '#64748b', marginTop: '2px' }}>
                      {item.label}
                    </div>
                  </div>
                ))}
              </div>

              {visionCpi >= 0.75 && (
                <div style={{
                  background: '#7f1d1d30',
                  border: '1px solid #ef444450',
                  borderRadius: '6px',
                  padding: '10px'
                }}>
                  <div style={{
                    fontSize: '12px',
                    color: '#fca5a5',
                    marginBottom: '8px',
                    display: 'flex',
                    alignItems: 'center',
                    gap: '5px'
                  }}>
                    <svg width="13" height="13" viewBox="0 0 24 24"
                         fill="none" stroke="#ef4444" strokeWidth="2">
                      <path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"/>
                      <path d="M12 9v4M12 17h.01"/>
                    </svg>
                    High density detected — CPI {visionCpi?.toFixed(3)}
                  </div>
                  {!triggerResult ? (
                    <button
                      onClick={triggerVisionAlert}
                      disabled={triggering}
                      style={{
                        width: '100%',
                        padding: '8px',
                        background: '#7f1d1d',
                        border: '1px solid #ef4444',
                        color: '#fca5a5',
                        borderRadius: '6px',
                        fontSize: '12px',
                        fontWeight: '600',
                        cursor: triggering ? 'not-allowed' : 'pointer',
                        display: 'flex',
                        alignItems: 'center',
                        justifyContent: 'center',
                        gap: '6px'
                      }}
                    >
                      {triggering ? 'Triggering...' : `Trigger Alert — ${corridor}`}
                    </button>
                  ) : (
                    <div style={{
                      fontSize: '12px',
                      color: triggerResult.status === 'triggered' ? '#86efac' : '#fca5a5',
                      textAlign: 'center',
                      padding: '6px'
                    }}>
                      {triggerResult.status === 'triggered'
                        ? 'Alert triggered — all agencies notified'
                        : triggerResult.reason}
                    </div>
                  )}
                </div>
              )}
            </div>
          )}

          {/* Controls */}
          <div style={{
            display: 'grid',
            gridTemplateColumns: '1fr 1fr',
            gap: '12px',
            marginTop: '14px',
            marginBottom: '14px'
          }}>
            <div>
              <label style={{
                fontSize: '11px',
                color: '#64748b',
                fontWeight: '600',
                textTransform: 'uppercase',
                letterSpacing: '0.06em',
                display: 'block',
                marginBottom: '6px'
              }}>
                Corridor
              </label>
              <select
                value={corridor}
                onChange={e => { setCorridor(e.target.value); setTriggerResult(null) }}
                disabled={processing}
                style={{
                  width: '100%',
                  background: '#0f172a',
                  border: '1px solid #334155',
                  borderRadius: '8px',
                  padding: '8px 10px',
                  color: '#f1f5f9',
                  fontSize: '13px'
                }}
              >
                {CORRIDORS.map(c => (
                  <option key={c} value={c}>{c}</option>
                ))}
              </select>
            </div>
            <div>
              <label style={{
                fontSize: '11px',
                color: '#64748b',
                fontWeight: '600',
                textTransform: 'uppercase',
                letterSpacing: '0.06em',
                display: 'block',
                marginBottom: '6px'
              }}>
                Corridor Width
              </label>
              <div style={{
                background: '#0f172a',
                border: '1px solid #334155',
                borderRadius: '8px',
                padding: '8px 10px',
                color: '#94a3b8',
                fontSize: '13px'
              }}>
                {CORRIDOR_WIDTH[corridor]}m — multiplier x{Math.round(CORRIDOR_WIDTH[corridor] * 3)}
              </div>
            </div>
          </div>

          {/* File upload area */}
          <div
            onClick={() => fileInputRef.current?.click()}
            style={{
              border: `2px dashed ${file ? '#3B82F6' : '#334155'}`,
              borderRadius: '8px',
              padding: '20px',
              textAlign: 'center',
              cursor: 'pointer',
              marginBottom: '14px',
              background: file ? '#1e3a5f20' : 'transparent',
              transition: 'all 0.2s'
            }}
          >
            <input
              ref={fileInputRef}
              type="file"
              accept=".mp4,.avi,.mov,.mkv,.webm"
              style={{ display: 'none' }}
              onChange={e => {
                setFile(e.target.files[0])
                setError('')
                setTriggerResult(null)
              }}
            />
            <svg width="24" height="24" viewBox="0 0 24 24"
                 fill="none"
                 stroke={file ? '#3B82F6' : '#64748b'}
                 strokeWidth="1.5"
                 style={{ margin: '0 auto 8px' }}>
              <path d="M15 10l4.553-2.069A1 1 0 0 1 21 8.867v6.266a1 1 0 0 1-1.447.902L15 14M3 8a2 2 0 0 1 2-2h10a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8z"/>
            </svg>
            <div style={{ fontSize: '13px', color: file ? '#60a5fa' : '#94a3b8', marginBottom: '4px' }}>
              {file
                ? `${file.name} (${(file.size / 1024 / 1024).toFixed(1)}MB)`
                : 'Click to select corridor video'}
            </div>
            <div style={{ fontSize: '11px', color: '#64748b' }}>
              MP4, AVI, MOV, MKV supported
            </div>
          </div>

          {/* Processing progress panel */}
          {processing && (
            <div style={{ marginBottom: '14px' }}>
              {/* Progress header */}
              <div style={{
                display: 'flex',
                justifyContent: 'space-between',
                alignItems: 'center',
                marginBottom: '8px'
              }}>
                <div style={{
                  display: 'flex',
                  alignItems: 'center',
                  gap: '8px',
                  fontSize: '13px',
                  fontWeight: '600',
                  color: '#60a5fa'
                }}>
                  <svg width="14" height="14" viewBox="0 0 24 24"
                       fill="none" stroke="currentColor" strokeWidth="2"
                       style={{ animation: 'spin 1s linear infinite' }}>
                    <circle cx="12" cy="12" r="10" strokeOpacity="0.25"/>
                    <path d="M12 2a10 10 0 0 1 10 10"/>
                  </svg>
                  YOLOv8 Analysing
                </div>
                <span style={{ fontSize: '13px', fontWeight: '700', color: '#60a5fa' }}>
                  {progress}%
                </span>
              </div>

              {/* Progress bar */}
              <div style={{
                height: '6px',
                background: '#1e293b',
                borderRadius: '3px',
                overflow: 'hidden',
                marginBottom: '10px'
              }}>
                <div style={{
                  width: `${progress}%`,
                  height: '100%',
                  background: '#3B82F6',
                  borderRadius: '3px',
                  transition: 'width 0.5s ease'
                }} />
              </div>

              {/* Frame stats */}
              <div style={{
                display: 'grid',
                gridTemplateColumns: '1fr 1fr 1fr',
                gap: '8px',
                marginBottom: '8px'
              }}>
                {[
                  { label: 'Frames read', value: framesRead, color: '#22c55e' },
                  { label: 'Frames left', value: framesLeft, color: '#f59e0b' },
                  { label: 'Total to process', value: totalFrames, color: '#94a3b8' }
                ].map(s => (
                  <div key={s.label} style={{
                    background: '#0f172a',
                    borderRadius: '6px',
                    padding: '8px',
                    textAlign: 'center'
                  }}>
                    <div style={{ fontSize: '18px', fontWeight: '700', color: s.color }}>
                      {s.value}
                    </div>
                    <div style={{ fontSize: '10px', color: '#64748b', marginTop: '2px' }}>
                      {s.label}
                    </div>
                  </div>
                ))}
              </div>

              {/* Live count while processing */}
              {liveCount > 0 && (
                <div style={{
                  background: '#0f172a',
                  borderRadius: '6px',
                  padding: '8px 12px',
                  fontSize: '12px',
                  color: '#94a3b8',
                  display: 'flex',
                  justifyContent: 'space-between'
                }}>
                  <span>
                    Current frame count:{' '}
                    <span style={{ color: '#f1f5f9', fontWeight: '600' }}>{liveCount} people</span>
                  </span>
                  <span>
                    Flow:{' '}
                    <span style={{ color: '#f1f5f9', fontWeight: '600' }}>{flowRate}/min</span>
                  </span>
                </div>
              )}

              {/* Status text */}
              <div style={{
                fontSize: '11px',
                color: '#64748b',
                marginTop: '6px',
                textAlign: 'center'
              }}>
                {status || 'Processing keyframes...'}
              </div>
            </div>
          )}

          {error && (
            <div style={{
              background: '#7f1d1d',
              color: '#fca5a5',
              padding: '8px 12px',
              borderRadius: '6px',
              fontSize: '12px',
              marginBottom: '12px'
            }}>
              {error}
            </div>
          )}

          {status && !processing && !error && (
            <div style={{
              background: '#14532d20',
              color: '#86efac',
              padding: '8px 12px',
              borderRadius: '6px',
              fontSize: '12px',
              marginBottom: '12px'
            }}>
              {status}
            </div>
          )}

          {/* Upload button */}
          <button
            id="visionProcessBtn"
            onClick={handleUpload}
            disabled={!file || uploading || processing}
            style={{
              width: '100%',
              padding: '10px',
              background: (!file || uploading || processing) ? '#374151' : '#2563eb',
              color: 'white',
              border: 'none',
              borderRadius: '8px',
              fontSize: '13px',
              fontWeight: '600',
              cursor: (!file || uploading || processing) ? 'not-allowed' : 'pointer',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              gap: '8px'
            }}
          >
            {uploading || processing ? (
              <>
                <svg width="14" height="14" viewBox="0 0 24 24"
                     fill="none" stroke="white" strokeWidth="2"
                     style={{ animation: 'spin 1s linear infinite' }}>
                  <circle cx="12" cy="12" r="10" strokeOpacity="0.25"/>
                  <path d="M12 2a10 10 0 0 1 10 10"/>
                </svg>
                {uploading ? 'Uploading...' : `Processing ${progress}%`}
              </>
            ) : (
              <>
                <svg width="14" height="14" viewBox="0 0 24 24"
                     fill="none" stroke="white" strokeWidth="2">
                  <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/>
                  <path d="M17 8l-5-5-5 5M12 3v12"/>
                </svg>
                Upload and Count Crowd
              </>
            )}
          </button>

          <div style={{
            marginTop: '12px',
            fontSize: '11px',
            color: '#475569',
            lineHeight: '1.5'
          }}>
            Upload a video from any pilgrimage corridor.
            YOLOv8 counts people frame by frame.
            Flow rate is calculated and fed directly into
            the CPI engine — replacing simulated data
            with real measurements for that corridor.
            If CPI crosses 0.75, you can trigger a real alert.
            Vision data expires after 5 minutes.
          </div>
        </div>
      )}
    </div>
  )
}
