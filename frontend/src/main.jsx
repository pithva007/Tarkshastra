import React from 'react'
import ReactDOM from 'react-dom/client'
import App from './App.jsx'
import Login from './pages/Login.jsx'
import './index.css'

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
    <Router />
  </React.StrictMode>
)