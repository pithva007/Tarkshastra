import React from 'react'
import ReactDOM from 'react-dom/client'
import App from './App.jsx'
import Login from './pages/Login.jsx'
import './index.css'

function Router() {
  const path = window.location.pathname
  const token = localStorage.getItem('ts11_token')
  const role = localStorage.getItem('ts11_role')

  // /login path OR no auth → show Login
  if (path === '/login' || !token || !role) {
    return <Login />
  }

  // / path with valid auth → show App
  return <App />
}

ReactDOM.createRoot(document.getElementById('root')).render(
  <React.StrictMode>
    <Router />
  </React.StrictMode>
)