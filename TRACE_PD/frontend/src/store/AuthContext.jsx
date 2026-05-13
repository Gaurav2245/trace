import { createContext, useContext, useState, useEffect, useCallback } from 'react'
import { authApi, openWebSocket } from '../services/api'

const Ctx = createContext(null)

export function AuthProvider({ children }) {
  const [user, setUser]   = useState(() => {
    try { return JSON.parse(localStorage.getItem('trcpd_user')) } catch { return null }
  })
  const [alert, setAlert] = useState(null)
  const [wsRef, setWsRef] = useState(null)

  const handleMsg = useCallback(msg => {
    if (msg.type === 'breakpoint') {
      setAlert({
        title:  msg.name,
        message: msg.message || 'Breakpoint triggered',
        action: 'Take a 10-min walk',
      })
    }
  }, [])

  useEffect(() => {
    if (user?.user_id) {
      const ws = openWebSocket(user.user_id, handleMsg)
      setWsRef(ws)
      return () => ws.close()
    }
  }, [user?.user_id, handleMsg])

  const login = async (email, password) => {
    const { data } = await authApi.login(email, password)
    localStorage.setItem('trcpd_token', data.access_token)
    localStorage.setItem('trcpd_user',  JSON.stringify(data))
    setUser(data)
    return data
  }

  const register = async payload => {
    const { data } = await authApi.register(payload)
    localStorage.setItem('trcpd_token', data.access_token)
    localStorage.setItem('trcpd_user',  JSON.stringify(data))
    setUser(data)
    return data
  }

  const logout = () => {
    localStorage.removeItem('trcpd_token')
    localStorage.removeItem('trcpd_user')
    wsRef?.close()
    setUser(null)
  }

  return (
    <Ctx.Provider value={{ user, login, register, logout, alert, setAlert }}>
      {children}
    </Ctx.Provider>
  )
}

export const useAuth = () => useContext(Ctx)
