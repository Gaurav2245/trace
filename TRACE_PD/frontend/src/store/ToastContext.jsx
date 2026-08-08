import { createContext, useContext, useCallback, useState } from 'react'
import { AlertCircle, CheckCircle2, X } from 'lucide-react'

const Ctx = createContext(null)
const AUTO_DISMISS_MS = 4500

const KIND_STYLE = {
  error:   { icon: AlertCircle,  color: '#ef4444', bg: 'rgba(239,68,68,0.1)',  border: 'rgba(239,68,68,0.3)' },
  success: { icon: CheckCircle2, color: '#22c55e', bg: 'rgba(34,197,94,0.1)', border: 'rgba(34,197,94,0.3)' },
}

export function ToastProvider({ children }) {
  const [toasts, setToasts] = useState([])

  const dismiss = useCallback(id => {
    setToasts(prev => prev.filter(t => t.id !== id))
  }, [])

  const push = useCallback((message, kind = 'error') => {
    const id = Date.now() + Math.random()
    setToasts(prev => [...prev, { id, message, kind }])
    setTimeout(() => dismiss(id), AUTO_DISMISS_MS)
  }, [dismiss])

  const toast = {
    error:   msg => push(msg, 'error'),
    success: msg => push(msg, 'success'),
  }

  return (
    <Ctx.Provider value={toast}>
      {children}
      <div className="fixed bottom-5 right-5 z-[100] flex flex-col gap-2 pointer-events-none" style={{ maxWidth: 360 }}>
        {toasts.map(t => {
          const style = KIND_STYLE[t.kind]
          const Icon = style.icon
          return (
            <div key={t.id}
              className="flex items-start gap-2.5 px-4 py-3 rounded-xl text-sm shadow-lg pointer-events-auto animate-fadeUp"
              style={{ background: 'var(--surface)', border: `1px solid ${style.border}`, color: 'var(--text)' }}>
              <Icon size={16} style={{ color: style.color, flexShrink: 0, marginTop: 1 }} />
              <span className="flex-1">{t.message}</span>
              <button onClick={() => dismiss(t.id)} className="opacity-50 hover:opacity-100 flex-shrink-0">
                <X size={13} />
              </button>
            </div>
          )
        })}
      </div>
    </Ctx.Provider>
  )
}

export const useToast = () => useContext(Ctx)
