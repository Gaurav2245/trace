import { useState } from 'react'
import { useNavigate, Link } from 'react-router-dom'
import { useAuth } from '../store/AuthContext.jsx'
import { apiErrorMessage } from '../services/api.js'
import { Zap, Eye, EyeOff, ArrowRight } from 'lucide-react'

export default function Login() {
  const [mode, setMode]       = useState('login')
  const [form, setForm]       = useState({ email: '', password: '', username: '', timezone: 'UTC', consent: false })
  const [loading, setLoading] = useState(false)
  const [error, setError]     = useState('')
  const [showPw, setShowPw]   = useState(false)
  const { login, register }   = useAuth()
  const nav = useNavigate()

  const set = (k, v) => setForm(f => ({ ...f, [k]: v }))

  async function submit() {
    setError(''); setLoading(true)
    try {
      if (mode === 'login') await login(form.email, form.password)
      else await register(form)
      nav('/dashboard')
    } catch (e) {
      setError(apiErrorMessage(e))
    } finally { setLoading(false) }
  }

  return (
    <div className="min-h-screen flex items-center justify-center px-4 grid-bg"
      style={{ background: 'var(--bg)' }}>
      <div className="w-full max-w-md">
        <div className="flex justify-center mb-8">
          <Link to="/" className="flex items-center gap-2">
            <div className="w-9 h-9 rounded-xl flex items-center justify-center"
              style={{ background: 'var(--accent)' }}>
              <Zap size={18} color="#fff" fill="#fff" />
            </div>
            <span className="font-mono font-bold text-lg">Trace</span>
          </Link>
        </div>

        <div className="p-8 rounded-2xl"
          style={{ background: 'var(--surface)', border: '1px solid var(--border)' }}>
          <div className="flex mb-6 rounded-xl overflow-hidden"
            style={{ background: 'var(--surface2)' }}>
            {['login', 'register'].map(m => (
              <button key={m} onClick={() => { setMode(m); setError('') }}
                className="flex-1 py-2.5 text-sm font-medium capitalize transition-all"
                style={{
                  background: mode === m ? 'var(--accent2)' : 'transparent',
                  color: mode === m ? '#fff' : 'var(--muted)',
                }}>
                {m === 'login' ? 'Sign In' : 'Register'}
              </button>
            ))}
          </div>

          <div className="space-y-4">
            {mode === 'register' && (
              <div>
                <label htmlFor="username" className="text-xs mb-1.5 block" style={{ color: 'var(--muted)' }}>Username</label>
                <input id="username" name="username" autoComplete="username"
                  value={form.username} onChange={e => set('username', e.target.value)}
                  placeholder="your_name" className="w-full px-4 py-3 rounded-xl text-sm outline-none"
                  style={{ background: 'var(--surface2)', border: '1px solid var(--border)', color: 'var(--text)', fontFamily: 'DM Sans' }} />
              </div>
            )}
            <div>
              <label htmlFor="email" className="text-xs mb-1.5 block" style={{ color: 'var(--muted)' }}>Email</label>
              <input id="email" name="email" autoComplete="email"
                value={form.email} onChange={e => set('email', e.target.value)}
                type="email" placeholder="you@example.com"
                onKeyDown={e => e.key === 'Enter' && submit()}
                className="w-full px-4 py-3 rounded-xl text-sm outline-none"
                style={{ background: 'var(--surface2)', border: '1px solid var(--border)', color: 'var(--text)', fontFamily: 'DM Sans' }} />
            </div>
            <div>
              <label htmlFor="password" className="text-xs mb-1.5 block" style={{ color: 'var(--muted)' }}>Password</label>
              <div className="relative">
                <input id="password" name="password" autoComplete={mode === 'login' ? 'current-password' : 'new-password'}
                  value={form.password} onChange={e => set('password', e.target.value)}
                  type={showPw ? 'text' : 'password'} placeholder="••••••••"
                  onKeyDown={e => e.key === 'Enter' && submit()}
                  className="w-full px-4 py-3 pr-10 rounded-xl text-sm outline-none"
                  style={{ background: 'var(--surface2)', border: '1px solid var(--border)', color: 'var(--text)', fontFamily: 'DM Sans' }} />
                <button type="button" onClick={() => setShowPw(s => !s)}
                  aria-label={showPw ? 'Hide password' : 'Show password'}
                  className="absolute right-3 top-3.5 opacity-50 hover:opacity-100">
                  {showPw ? <EyeOff size={14} /> : <Eye size={14} />}
                </button>
              </div>
            </div>

            {mode === 'register' && (
              <label className="flex items-start gap-2.5 text-xs cursor-pointer select-none" style={{ color: 'var(--muted)' }}>
                <input type="checkbox" checked={form.consent} onChange={e => set('consent', e.target.checked)}
                  className="mt-0.5 accent-indigo-500" />
                <span>I consent to Trace storing my activity logs and behavior data to generate insights.</span>
              </label>
            )}

            {error && (
              <div className="px-4 py-2 rounded-lg text-sm"
                style={{ background: 'rgba(239,68,68,0.1)', color: '#ef4444', border: '1px solid rgba(239,68,68,0.3)' }}>
                {error}
              </div>
            )}

            <button onClick={submit} disabled={loading || (mode === 'register' && !form.consent)}
              className="w-full flex items-center justify-center gap-2 py-3 rounded-xl font-medium text-sm transition-all hover:opacity-90 disabled:opacity-50"
              style={{ background: 'var(--accent)', color: '#fff' }}>
              {loading ? 'Please wait…' : mode === 'login' ? 'Sign In' : 'Create Account'}
              {!loading && <ArrowRight size={16} />}
            </button>

            {mode === 'login' && (
              <button
                onClick={() => { set('email', 'demo@trace.dev'); set('password', 'demo1234') }}
                className="w-full py-2.5 rounded-xl text-sm transition-all hover:opacity-80"
                style={{ background: 'var(--surface2)', color: 'var(--muted)', border: '1px solid var(--border)' }}>
                Use Demo Account
              </button>
            )}
          </div>
        </div>
        <p className="text-center mt-3 text-xs" style={{ color: 'var(--muted)' }}>
          Demo: demo@trace.dev / demo1234
        </p>
      </div>
    </div>
  )
}
