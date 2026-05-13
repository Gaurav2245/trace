import { useAuth } from '../store/AuthContext.jsx'
import { AlertTriangle, X, ArrowRight } from 'lucide-react'

export default function AlertBanner() {
  const { alert, setAlert } = useAuth()
  if (!alert) return null

  return (
    <div className="fixed top-14 inset-x-0 z-40 px-6 py-2 animate-slideIn pointer-events-none">
      <div className="max-w-5xl mx-auto flex items-start gap-4 p-4 rounded-2xl pointer-events-auto"
        style={{
          background: 'var(--surface)',
          border: '2px solid var(--accent)',
          boxShadow: '0 0 30px rgba(249,115,22,0.2)',
        }}>
        <div className="w-9 h-9 rounded-xl flex items-center justify-center flex-shrink-0"
          style={{ background: 'rgba(249,115,22,0.15)' }}>
          <AlertTriangle size={16} style={{ color: 'var(--accent)' }} />
        </div>
        <div className="flex-1">
          <p className="font-medium mb-1">{alert.title}</p>
          <p className="text-sm mb-3" style={{ color: 'var(--muted)' }}>{alert.message}</p>
          {alert.action && (
            <button className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium"
              style={{ background: 'var(--accent)', color: '#fff' }}>
              {alert.action} <ArrowRight size={12} />
            </button>
          )}
        </div>
        <button onClick={() => setAlert(null)}
          className="opacity-50 hover:opacity-100 p-1 flex-shrink-0">
          <X size={14} />
        </button>
      </div>
    </div>
  )
}
