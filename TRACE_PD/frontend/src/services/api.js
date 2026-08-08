import axios from 'axios'

function resolveApiBase() {
  if (import.meta.env.VITE_API_URL) return import.meta.env.VITE_API_URL
  if (window.location.port === '10080') return window.location.origin
  return 'http://localhost:18000'
}

function resolveWsBase(apiBase) {
  if (import.meta.env.VITE_WS_URL) return import.meta.env.VITE_WS_URL
  if (apiBase.startsWith('https://')) return apiBase.replace('https://', 'wss://')
  if (apiBase.startsWith('http://')) return apiBase.replace('http://', 'ws://')
  return 'ws://localhost:18000'
}

const BASE = resolveApiBase()
const WS   = resolveWsBase(BASE)

const api = axios.create({ baseURL: BASE })

api.interceptors.request.use(cfg => {
  const token = localStorage.getItem('trcpd_token')
  if (token) cfg.headers.Authorization = `Bearer ${token}`
  return cfg
})

api.interceptors.response.use(
  r => r,
  err => {
    if (err.response?.status === 401) {
      localStorage.removeItem('trcpd_token')
      localStorage.removeItem('trcpd_user')
      window.location.href = '/login'
    }
    return Promise.reject(err)
  }
)

export const authApi = {
  register: d => api.post('/auth/register', d),
  login: (email, password) => {
    const fd = new FormData()
    fd.append('username', email)
    fd.append('password', password)
    return api.post('/auth/login', fd)
  },
  me: () => api.get('/users/me'),
}

export const dashboardApi = { get: () => api.get('/dashboard') }

export const logsApi = {
  list:   (limit = 50, offset = 0) => api.get(`/logs?limit=${limit}&offset=${offset}`),
  create: d => api.post('/logs', d),
}

export const loopsApi = {
  list:         () => api.get('/loops'),
  updateStatus: (id, status) => api.patch(`/loops/${id}/status?status=${status}`),
}

export const fixesApi = {
  apply: (id, applied) => api.patch(`/fixes/${id}`, { applied }),
}

export const debugApi = {
  query:   q => api.post('/debug', { query: q, include_context: true }),
  history: () => api.get('/chat/history'),
}

export const breakpointsApi = {
  list:   () => api.get('/breakpoints'),
  create: d  => api.post('/breakpoints', d),
}

// FastAPI validation errors return `detail` as an array of
// {loc, msg, type} objects rather than a string — rendering that directly
// as a React child throws. Always route API errors through this first.
export function apiErrorMessage(err, fallback = 'Something went wrong') {
  const detail = err?.response?.data?.detail
  if (!detail) return fallback
  if (typeof detail === 'string') return detail
  if (Array.isArray(detail)) {
    return detail.map(d => d.msg || JSON.stringify(d)).join('; ') || fallback
  }
  return fallback
}

export function openWebSocket(userId, onMessage) {
  const token = localStorage.getItem('trcpd_token')
  const ws = new WebSocket(`${WS}/ws/${userId}?token=${encodeURIComponent(token || '')}`)
  ws.onmessage = e => {
    try { onMessage(JSON.parse(e.data)) }
    catch (err) { console.warn('[TRACE_PD WS] failed to handle message', err) }
  }
  ws.onerror   = e => console.warn('[TRACE_PD WS]', e)
  const ping   = setInterval(() => {
    if (ws.readyState === WebSocket.OPEN) ws.send(JSON.stringify({ type: 'ping' }))
  }, 25000)
  ws.onclose = () => clearInterval(ping)
  return ws
}

export default api
