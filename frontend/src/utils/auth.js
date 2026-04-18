const TOKEN_KEY = 'ts11_token'
const ROLE_KEY = 'ts11_role'
const USER_KEY = 'ts11_user'

export function saveAuth(loginResponse) {
  localStorage.setItem(TOKEN_KEY, loginResponse.token)
  localStorage.setItem(ROLE_KEY, loginResponse.role)
  localStorage.setItem(USER_KEY, JSON.stringify({
    name: loginResponse.name,
    role: loginResponse.role,
    unit_id: loginResponse.unit_id,
    display_name: loginResponse.display_name,
    color: loginResponse.color,
    permissions: loginResponse.permissions
  }))
}

export function getToken() {
  return localStorage.getItem(TOKEN_KEY) || ''
}

export function getRole() {
  return localStorage.getItem(ROLE_KEY) || ''
}

export function getUser() {
  try {
    const raw = localStorage.getItem(USER_KEY)
    return raw ? JSON.parse(raw) : null
  } catch {
    return null
  }
}

export function isLoggedIn() {
  const token = getToken()
  const role = getRole()
  return Boolean(token && role)
}

export function clearAuth() {
  localStorage.removeItem(TOKEN_KEY)
  localStorage.removeItem(ROLE_KEY)
  localStorage.removeItem(USER_KEY)
}

export function redirectToDashboard(role) {
  // Hard redirect — works without React Router
  window.location.href = `/?agency=${role}`
}

export function redirectToLogin() {
  clearAuth()
  window.location.href = '/login'
}

// Axios instance with auth header pre-attached
// Import this instead of raw axios everywhere
import axios from 'axios'

const API_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000'

export const api = axios.create({
  baseURL: API_URL
})

// Auto-attach token to every request
api.interceptors.request.use(config => {
  const token = getToken()
  if (token) {
    config.headers.Authorization = `Bearer ${token}`
  }
  return config
})

// Auto-handle 401 — redirect to login
api.interceptors.response.use(
  response => response,
  error => {
    if (error.response?.status === 401) {
      console.warn('[AUTH] 401 — clearing auth and redirecting')
      clearAuth()
      window.location.href = '/'
    }
    return Promise.reject(error)
  }
)

export { API_URL }