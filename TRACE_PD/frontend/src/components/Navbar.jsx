import { Link, useLocation, useNavigate } from 'react-router-dom'
import { Activity, GitBranch, MessageSquare, List, Zap, LogOut } from 'lucide-react'
import { useAuth } from '../store/AuthContext.jsx'

const NAV = [
  { to: '/dashboard', label: 'Dashboard', icon: Activity },
  { to: '/loops',     label: 'Loops',     icon: GitBranch },
  { to: '/chat',      label: 'Debugger',  icon: MessageSquare },
  { to: '/logs',      label: 'Logs',      icon: List },
]

export default function Navbar() {
  const { pathname } = useLocation()
  const { user, logout } = useAuth()
  const nav = useNavigate()

  return (
    <nav className="fixed top-0 inset-x-0 z-50 h-14 flex items-center px-6 gap-5"
      style={{ background: 'var(--surface)', borderBottom: '1px solid var(--border)' }}>

      <Link to="/" className="flex items-center gap-2 mr-2 flex-shrink-0">
        <div className="w-7 h-7 rounded-lg flex items-center justify-center"
          style={{ background: 'var(--accent)' }}>
          <Zap size={13} color="#fff" fill="#fff" />
        </div>
        <span className="font-mono font-bold text-sm tracking-wider">Trace</span>
      </Link>

      <div className="flex items-center gap-1 flex-1">
        {NAV.map(({ to, label, icon: Icon }) => {
          const active = pathname === to
          return (
            <Link key={to} to={to}
              className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-sm transition-all"
              style={{
                color:      active ? 'var(--text)' : 'var(--muted)',
                background: active ? 'var(--surface2)' : 'transparent',
                fontWeight: active ? 500 : 400,
              }}>
              <Icon size={13} />
              {label}
            </Link>
          )
        })}
      </div>

      <div className="flex items-center gap-3 flex-shrink-0">
        <div className="flex items-center gap-1.5">
          <div className="w-1.5 h-1.5 rounded-full animate-pulse"
            style={{ background: 'var(--accent3)' }} />
          <span className="font-mono text-xs" style={{ color: 'var(--muted)' }}>live</span>
        </div>
        {user && (
          <>
            <span className="font-mono text-xs px-2 py-1 rounded-lg"
              style={{ background: 'var(--surface2)', color: 'var(--muted)' }}>
              {user.username}
            </span>
            <button onClick={() => { logout(); nav('/') }}
              className="p-1.5 rounded-lg opacity-50 hover:opacity-100 transition-opacity"
              style={{ color: 'var(--muted)' }}>
              <LogOut size={13} />
            </button>
          </>
        )}
      </div>
    </nav>
  )
}
