import { useState } from 'react'
import axios from 'axios'

const API = import.meta.env.VITE_API_URL || 'http://localhost:8000'

const ROLES = [
  {
    id: 'driver',
    label: 'Bus Driver',
    icon: '🚌',
    desc: 'Track your route & get hold alerts',
    color: 'from-green-900 to-green-800',
    border: 'border-green-600',
    demo: 'driver_001 / driver123',
  },
  {
    id: 'police',
    label: 'Police Station',
    icon: '🚔',
    desc: 'Monitor corridors & deploy officers',
    color: 'from-blue-900 to-blue-800',
    border: 'border-blue-600',
    demo: 'police_001 / police123',
  },
  {
    id: 'temple',
    label: 'Temple Trust',
    icon: '🛕',
    desc: 'Manage darshan flow & queue control',
    color: 'from-yellow-900 to-yellow-800',
    border: 'border-yellow-600',
    demo: 'temple_001 / temple123',
  },
  {
    id: 'gsrtc',
    label: 'GSRTC Control',
    icon: '🗺️',
    desc: 'Coordinate bus dispatch & holds',
    color: 'from-purple-900 to-purple-800',
    border: 'border-purple-600',
    demo: 'gsrtc_001 / gsrtc123',
  },
]

export default function Login({ onLogin }) {
  const [selectedRole, setSelectedRole] = useState(null)
  const [username, setUsername]         = useState('')
  const [password, setPassword]         = useState('')
  const [loading, setLoading]           = useState(false)
  const [error, setError]               = useState('')

  const handleRoleSelect = (role) => {
    setSelectedRole(role)
    setError('')
    // Auto-fill demo credentials
    const r = ROLES.find((r) => r.id === role)
    if (r) {
      const [u, p] = r.demo.split(' / ')
      setUsername(u)
      setPassword(p)
    }
  }

  const handleLogin = async (e) => {
    e.preventDefault()
    if (!selectedRole) { setError('Please select a role'); return }
    if (!username || !password) { setError('Enter username and password'); return }

    setLoading(true)
    setError('')

    try {
      const { data } = await axios.post(`${API}/api/login`, {
        role: selectedRole,
        username,
        password,
      })
      localStorage.setItem('ts11_token', data.token)
      localStorage.setItem('ts11_role', data.role)
      localStorage.setItem('ts11_name', data.name)
      localStorage.setItem('ts11_unit', data.unit_id)

      if (onLogin) {
        onLogin(data)
      } else {
        window.location.href = data.redirect_url
      }
    } catch (err) {
      setError(err.response?.data?.detail || 'Login failed. Check credentials.')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="min-h-screen bg-gray-950 flex flex-col items-center justify-center px-4 py-10">
      {/* Logo / Title */}
      <div className="text-center mb-8">
        <div className="text-5xl mb-3">🏛️</div>
        <h1 className="text-2xl font-bold text-white tracking-wide">Stampede Window Predictor</h1>
        <p className="text-gray-400 text-sm mt-1">TS-11 · Gujarat Pilgrimage Safety System</p>
      </div>

      <div className="w-full max-w-2xl">
        {/* Role selector */}
        <p className="text-gray-300 text-sm font-semibold mb-3 uppercase tracking-wide">Select your role</p>
        <div className="grid grid-cols-2 gap-3 mb-6">
          {ROLES.map((role) => (
            <button
              key={role.id}
              onClick={() => handleRoleSelect(role.id)}
              className={`rounded-xl p-4 text-left border-2 transition-all bg-gradient-to-br ${role.color} ${
                selectedRole === role.id
                  ? `${role.border} ring-2 ring-white/20 scale-[1.02]`
                  : 'border-gray-700 hover:border-gray-500'
              }`}
            >
              <div className="text-3xl mb-2">{role.icon}</div>
              <p className="font-bold text-white text-sm">{role.label}</p>
              <p className="text-gray-300 text-xs mt-0.5">{role.desc}</p>
            </button>
          ))}
        </div>

        {/* Login form */}
        <form onSubmit={handleLogin} className="bg-gray-900 rounded-2xl p-6 border border-gray-700 space-y-4">
          <div>
            <label className="block text-xs text-gray-400 uppercase tracking-wide mb-1">Username</label>
            <input
              type="text"
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              placeholder="e.g. driver_001"
              className="w-full bg-gray-800 border border-gray-600 rounded-lg px-3 py-2.5 text-white text-sm focus:outline-none focus:border-amber-500 transition-colors"
            />
          </div>
          <div>
            <label className="block text-xs text-gray-400 uppercase tracking-wide mb-1">Password</label>
            <input
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              placeholder="••••••••"
              className="w-full bg-gray-800 border border-gray-600 rounded-lg px-3 py-2.5 text-white text-sm focus:outline-none focus:border-amber-500 transition-colors"
            />
          </div>

          {error && (
            <p className="text-red-400 text-sm bg-red-950 border border-red-800 rounded-lg px-3 py-2">
              {error}
            </p>
          )}

          <button
            type="submit"
            disabled={loading}
            className="w-full py-3 rounded-xl font-bold text-sm bg-amber-500 hover:bg-amber-400 text-gray-900 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
          >
            {loading ? 'Signing in…' : 'Sign In →'}
          </button>
        </form>

        {/* Demo credentials */}
        <div className="mt-5 bg-gray-900 rounded-xl border border-gray-700 p-4">
          <p className="text-xs text-gray-400 uppercase tracking-wide font-semibold mb-3">
            Demo Credentials (for judges)
          </p>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
            {ROLES.map((role) => (
              <button
                key={role.id}
                onClick={() => handleRoleSelect(role.id)}
                className="text-left rounded-lg bg-gray-800 hover:bg-gray-700 px-3 py-2 transition-colors"
              >
                <span className="text-base mr-1.5">{role.icon}</span>
                <span className="text-xs text-gray-300 font-mono">{role.demo}</span>
              </button>
            ))}
          </div>
          <p className="text-xs text-gray-600 mt-3 text-center">
            Click any credential above to auto-fill, then Sign In
          </p>
        </div>
      </div>
    </div>
  )
}
