import React, { useState, useEffect } from 'react'

const API_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000'

const ROLES = [
  {
    id: "police",
    label: "Police Station",
    credentials: "police_001 / police123",
    color: "#3B82F6",
    bg: "#1E3A5F",
    border: "#3B82F6",
    svg: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
      <path d="M12 2L3 7v5c0 5.25 3.75 10.15 9 11.25C17.25 22.15 21 17.25 21 12V7L12 2z"/>
    </svg>`
  },
  {
    id: "gsrtc",
    label: "GSRTC Transport",
    credentials: "gsrtc_001 / gsrtc123",
    color: "#F59E0B",
    bg: "#1C1500",
    border: "#F59E0B",
    svg: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
      <rect x="1" y="3" width="15" height="13" rx="2"/>
      <path d="M16 8h4l3 3v4h-7V8z"/>
      <circle cx="5.5" cy="18.5" r="2.5"/>
      <circle cx="18.5" cy="18.5" r="2.5"/>
    </svg>`
  },
  {
    id: "temple",
    label: "Temple Trust",
    credentials: "temple_001 / temple123",
    color: "#8B5CF6",
    bg: "#1A1030",
    border: "#8B5CF6",
    svg: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
      <path d="M3 22V12L12 3l9 9v10"/>
      <path d="M9 22V16h6v6"/>
      <path d="M12 3v4M8 7h8"/>
    </svg>`
  },
  {
    id: "admin",
    label: "Admin Control",
    credentials: "admin_001 / admin123",
    color: "#EF4444",
    bg: "#1C0A0A",
    border: "#EF4444",
    svg: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
      <circle cx="12" cy="8" r="4"/>
      <path d="M12 14c-6 0-8 2-8 4v1h16v-1c0-2-2-4-8-4z"/>
      <path d="M18 4l2 2-8 8-4-4 2-2 2 2z" fill="currentColor" stroke="none"/>
    </svg>`
  }
]

export default function Login() {
  console.log('[LOGIN] Component rendering')
  
  const [selectedRole, setSelectedRole] = useState(null)
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [systemStats, setSystemStats] = useState({ alerts: 0 })

  useEffect(() => {
    console.log('[LOGIN] useEffect running')
    // Fetch system health for active alerts count
    fetch(`${API_URL}/health`)
      .then(res => res.json())
      .then(data => {
        console.log('[LOGIN] Health data:', data)
        setSystemStats({ alerts: data.connections || 0 })
      })
      .catch(err => {
        console.error('[LOGIN] Health fetch error:', err)
        setSystemStats({ alerts: 0 })
      })
  }, [])

  const handleRoleSelect = (role) => {
    setSelectedRole(role)
    setError('')
    
    // Prefill demo credentials on role select
    const DEMO_CREDS = {
      police:  { u: 'police_001',  p: 'police123'  },
      gsrtc:   { u: 'gsrtc_001',   p: 'gsrtc123'   },
      temple:  { u: 'temple_001',  p: 'temple123'  },
      admin:   { u: 'admin_001',   p: 'admin123'   }
    }
    
    const creds = DEMO_CREDS[role.id]
    if (creds) {
      setUsername(creds.u)
      setPassword(creds.p)
    }
  }

  const handleLogin = async (e) => {
    e.preventDefault()
    setError('')
    
    if (!username || !password) {
      setError('Enter username and password')
      return
    }

    setLoading(true)

    try {
      const response = await fetch(`${API_URL}/api/login`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ username, password })
      })

      const data = await response.json()

      if (!response.ok) {
        setError(data.detail || 'Invalid credentials')
        setLoading(false)
        return
      }

      // Save to localStorage
      localStorage.setItem('ts11_token', data.token)
      localStorage.setItem('ts11_role', data.role)
      localStorage.setItem('ts11_user', JSON.stringify({
        name: data.name,
        role: data.role,
        unit_id: data.unit_id,
        display_name: data.display_name,
        color: data.color || '#3B82F6',
        permissions: data.permissions || []
      }))

      console.log('[LOGIN] Success:', data.role, data.name)
      console.log('[LOGIN] Token saved:', data.token.slice(0,20) + '...')

      // Hard redirect to dashboard
      // Small delay so localStorage write completes
      setTimeout(() => {
        window.location.href = `/?agency=${data.role}`
      }, 100)

    } catch (err) {
      console.error('[LOGIN] Error:', err)
      setError('Connection failed. Is backend running?')
      setLoading(false)
    }
  }

  return (
    <div style={{
      minHeight: '100vh',
      display: 'flex',
      background: 'linear-gradient(135deg, #0f172a 0%, #1e293b 100%)'
    }}>
      {/* Left Panel - Brand */}
      <div style={{
        width: '40%',
        padding: '60px 40px',
        display: 'flex',
        flexDirection: 'column',
        justifyContent: 'center',
        background: `
          radial-gradient(circle at 20% 80%, rgba(59, 130, 246, 0.1) 0%, transparent 50%),
          radial-gradient(circle at 80% 20%, rgba(139, 92, 246, 0.1) 0%, transparent 50%),
          linear-gradient(135deg, #0f172a 0%, #1e293b 100%)
        `,
        position: 'relative'
      }}>
        {/* Grid pattern overlay */}
        <div style={{
          position: 'absolute',
          inset: 0,
          backgroundImage: `
            linear-gradient(rgba(148, 163, 184, 0.03) 1px, transparent 1px),
            linear-gradient(90deg, rgba(148, 163, 184, 0.03) 1px, transparent 1px)
          `,
          backgroundSize: '20px 20px'
        }} />
        
        <div style={{ position: 'relative', zIndex: 1 }}>
          <div style={{
            fontSize: '48px',
            fontWeight: '800',
            color: '#f1f5f9',
            marginBottom: '16px',
            letterSpacing: '-0.02em'
          }}>
            Stampede Window
          </div>
          <div style={{
            fontSize: '48px',
            fontWeight: '800',
            background: 'linear-gradient(135deg, #3b82f6, #8b5cf6)',
            WebkitBackgroundClip: 'text',
            WebkitTextFillColor: 'transparent',
            marginBottom: '24px',
            letterSpacing: '-0.02em'
          }}>
            Predictor
          </div>
          
          <div style={{
            fontSize: '18px',
            color: '#94a3b8',
            marginBottom: '40px',
            lineHeight: '1.6'
          }}>
            Real-time crowd pressure monitoring and alert system for Gujarat pilgrimage corridors
          </div>
          
          <div style={{
            padding: '20px',
            background: 'rgba(15, 23, 42, 0.6)',
            border: '1px solid #334155',
            borderRadius: '12px',
            backdropFilter: 'blur(8px)'
          }}>
            <div style={{
              fontSize: '14px',
              color: '#64748b',
              marginBottom: '12px',
              fontWeight: '500'
            }}>
              System Status
            </div>
            <div style={{
              display: 'flex',
              alignItems: 'center',
              gap: '12px'
            }}>
              <div style={{
                width: '8px',
                height: '8px',
                borderRadius: '50%',
                background: '#22c55e'
              }} />
              <span style={{ color: '#f1f5f9', fontSize: '16px' }}>
                Operational
              </span>
              <span style={{ color: '#64748b', fontSize: '14px' }}>
                • {systemStats.alerts} active connections
              </span>
            </div>
          </div>
        </div>
      </div>

      {/* Right Panel - Login */}
      <div style={{
        width: '60%',
        padding: '60px 40px',
        display: 'flex',
        flexDirection: 'column',
        justifyContent: 'center',
        background: 'rgba(15, 23, 42, 0.8)',
        backdropFilter: 'blur(10px)'
      }}>
        <div style={{ maxWidth: '500px', margin: '0 auto', width: '100%' }}>
          <h2 style={{
            fontSize: '32px',
            fontWeight: '700',
            color: '#f1f5f9',
            marginBottom: '8px',
            textAlign: 'center'
          }}>
            Select your role
          </h2>
          <p style={{
            color: '#94a3b8',
            textAlign: 'center',
            marginBottom: '40px',
            fontSize: '16px'
          }}>
            Choose your agency to access the dashboard
          </p>

          {/* Role Cards Grid */}
          <div style={{
            display: 'grid',
            gridTemplateColumns: '1fr 1fr',
            gap: '16px',
            marginBottom: '32px'
          }}>
            {ROLES.map(role => (
              <div
                key={role.id}
                onClick={() => handleRoleSelect(role)}
                style={{
                  padding: '24px',
                  background: selectedRole?.id === role.id ? role.bg : '#1e293b',
                  border: `2px solid ${selectedRole?.id === role.id ? role.border : '#334155'}`,
                  borderRadius: '12px',
                  cursor: 'pointer',
                  transition: 'all 0.2s ease',
                  transform: selectedRole?.id === role.id ? 'scale(1.02)' : 'scale(1)',
                  boxShadow: selectedRole?.id === role.id 
                    ? `0 0 20px ${role.color}40` 
                    : '0 4px 6px rgba(0, 0, 0, 0.1)'
                }}
              >
                <div style={{
                  display: 'flex',
                  alignItems: 'center',
                  gap: '12px',
                  marginBottom: '12px'
                }}>
                  <div 
                    style={{ 
                      width: '24px', 
                      height: '24px', 
                      color: role.color 
                    }}
                    dangerouslySetInnerHTML={{ __html: role.svg }}
                  />
                  <div style={{
                    fontSize: '16px',
                    fontWeight: '600',
                    color: '#f1f5f9'
                  }}>
                    {role.label}
                  </div>
                </div>
                <div style={{
                  fontSize: '12px',
                  color: '#94a3b8',
                  fontFamily: 'monospace'
                }}>
                  Demo: {role.credentials}
                </div>
              </div>
            ))}
          </div>

          {/* Login Form */}
          {selectedRole && (
            <form onSubmit={handleLogin} style={{ marginBottom: '24px' }}>
              <div style={{ marginBottom: '16px' }}>
                <label style={{
                  display: 'block',
                  fontSize: '14px',
                  fontWeight: '500',
                  color: '#f1f5f9',
                  marginBottom: '6px'
                }}>
                  Username
                </label>
                <input
                  type="text"
                  value={username}
                  onChange={(e) => setUsername(e.target.value)}
                  style={{
                    width: '100%',
                    padding: '12px 16px',
                    background: '#0f172a',
                    border: '1px solid #334155',
                    borderRadius: '8px',
                    color: '#f1f5f9',
                    fontSize: '16px',
                    outline: 'none',
                    transition: 'border-color 0.2s ease'
                  }}
                  onFocus={(e) => e.target.style.borderColor = selectedRole.color}
                  onBlur={(e) => e.target.style.borderColor = '#334155'}
                />
              </div>

              <div style={{ marginBottom: '24px' }}>
                <label style={{
                  display: 'block',
                  fontSize: '14px',
                  fontWeight: '500',
                  color: '#f1f5f9',
                  marginBottom: '6px'
                }}>
                  Password
                </label>
                <input
                  type="password"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  style={{
                    width: '100%',
                    padding: '12px 16px',
                    background: '#0f172a',
                    border: '1px solid #334155',
                    borderRadius: '8px',
                    color: '#f1f5f9',
                    fontSize: '16px',
                    outline: 'none',
                    transition: 'border-color 0.2s ease'
                  }}
                  onFocus={(e) => e.target.style.borderColor = selectedRole.color}
                  onBlur={(e) => e.target.style.borderColor = '#334155'}
                />
              </div>

              {error && (
                <div style={{
                  padding: '12px 16px',
                  background: 'rgba(239, 68, 68, 0.1)',
                  border: '1px solid #ef4444',
                  borderRadius: '8px',
                  color: '#ef4444',
                  fontSize: '14px',
                  marginBottom: '16px'
                }}>
                  {error}
                </div>
              )}

              <button
                type="submit"
                disabled={loading || !selectedRole}
                style={{
                  width: '100%',
                  padding: '12px',
                  background: loading ? '#374151' : '#2563eb',
                  color: 'white',
                  border: 'none',
                  borderRadius: '8px',
                  fontSize: '14px',
                  fontWeight: '600',
                  cursor: loading ? 'not-allowed' : 'pointer',
                  marginTop: '12px'
                }}
              >
                {loading ? 'Signing in...' : 'Sign In'}
              </button>
            </form>
          )}

          <div style={{
            textAlign: 'center',
            fontSize: '12px',
            color: '#64748b'
          }}>
            Demo system - Use provided credentials above
          </div>
        </div>
      </div>

      {/* Mobile responsive styles */}
      <style jsx>{`
        @media (max-width: 768px) {
          div[style*="display: flex"] {
            flex-direction: column !important;
          }
          div[style*="width: 40%"], div[style*="width: 60%"] {
            width: 100% !important;
          }
          div[style*="gridTemplateColumns: '1fr 1fr'"] {
            grid-template-columns: 1fr !important;
          }
        }
      `}</style>
    </div>
  )
}