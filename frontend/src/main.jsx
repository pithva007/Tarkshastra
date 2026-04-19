import React from 'react'
import ReactDOM from 'react-dom/client'
import App from './App.jsx'
import Login from './pages/Login.jsx'
import './index.css'

// ── Error Boundary — shows crash message instead of blank screen ──────────────
class ErrorBoundary extends React.Component {
  constructor(props) {
    super(props)
    this.state = { hasError: false, error: null, info: null }
  }
  static getDerivedStateFromError(error) {
    return { hasError: true, error }
  }
  componentDidCatch(error, info) {
    console.error('[ERROR BOUNDARY] Caught:', error, info)
    this.setState({ info })
  }
  render() {
    if (this.state.hasError) {
      return (
        <div style={{
          minHeight: '100vh', background: '#0f172a', color: '#f1f5f9',
          display: 'flex', alignItems: 'center', justifyContent: 'center',
          flexDirection: 'column', padding: '2rem', fontFamily: 'monospace'
        }}>
          <div style={{ fontSize: '2rem', marginBottom: '1rem' }}>💥 App Crashed</div>
          <div style={{
            background: '#1e293b', border: '1px solid #ef4444', borderRadius: '12px',
            padding: '1.5rem', maxWidth: '800px', width: '100%'
          }}>
            <div style={{ color: '#ef4444', fontWeight: 700, marginBottom: '0.5rem' }}>
              {this.state.error?.toString()}
            </div>
            <pre style={{ color: '#94a3b8', fontSize: '12px', whiteSpace: 'pre-wrap', overflow: 'auto' }}>
              {this.state.info?.componentStack}
            </pre>
          </div>
          <button
            onClick={() => { localStorage.clear(); window.location.reload() }}
            style={{
              marginTop: '1.5rem', padding: '0.75rem 2rem', background: '#2563eb',
              color: 'white', border: 'none', borderRadius: '8px',
              fontSize: '14px', cursor: 'pointer'
            }}
          >
            Clear Auth &amp; Reload
          </button>
        </div>
      )
    }
    return this.props.children
  }
}

function Router() {
  const token = localStorage.getItem('ts11_token')
  const role = localStorage.getItem('ts11_role')

  console.log('[ROUTER] Token:', token ? 'exists' : 'missing')
  console.log('[ROUTER] Role:', role)

  // No auth → show Login
  if (!token || !role) {
    console.log('[ROUTER] No auth, showing Login')
    return <Login />
  }

  // Has auth → show App
  console.log('[ROUTER] Has auth, showing App')
  return <App />
}

ReactDOM.createRoot(document.getElementById('root')).render(
  <React.StrictMode>
    <ErrorBoundary>
      <Router />
    </ErrorBoundary>
  </React.StrictMode>
)