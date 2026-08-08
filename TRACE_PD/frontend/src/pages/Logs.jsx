import { useState, useEffect } from 'react'
import { Plus, Search, Brain, Moon, Smartphone, Coffee, Dumbbell, BookOpen, X, Check, RefreshCw } from 'lucide-react'
import { logsApi, apiErrorMessage } from '../services/api.js'
import { useToast } from '../store/ToastContext.jsx'

const ACTIVITY_TYPES = [
  { id: 'deep_work', label: 'Deep Work', icon: Brain, color: '#6366f1' },
  { id: 'sleep', label: 'Sleep', icon: Moon, color: '#38bdf8' },
  { id: 'phone', label: 'Phone Usage', icon: Smartphone, color: '#f97316' },
  { id: 'break', label: 'Break', icon: Coffee, color: '#22c55e' },
  { id: 'exercise', label: 'Exercise', icon: Dumbbell, color: '#ec4899' },
  { id: 'reading', label: 'Reading', icon: BookOpen, color: '#f59e0b' },
]

function formatDuration(mins) {
  if (!mins) return '0m'
  if (mins < 60) return mins + 'm'
  const h = Math.floor(mins / 60), m = mins % 60
  return m > 0 ? h + 'h ' + m + 'm' : h + 'h'
}

function formatTime(ts) {
  const d = new Date(ts)
  return d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }) + ' · ' + d.toLocaleDateString([], { month: 'short', day: 'numeric' })
}

function getType(id) { return ACTIVITY_TYPES.find(t => t.id === id) || { id, label: id, icon: Brain, color: '#6366f1' } }

const PAGE_SIZE = 50

export default function Logs() {
  const [logs, setLogs] = useState([])
  const [serverOffset, setServerOffset] = useState(0)
  const [loading, setLoading] = useState(true)
  const [loadingMore, setLoadingMore] = useState(false)
  const [hasMore, setHasMore] = useState(false)
  const [saving, setSaving] = useState(false)
  const [search, setSearch] = useState('')
  const [filterType, setFilterType] = useState('all')
  const [showForm, setShowForm] = useState(false)
  const [form, setForm] = useState({ activity_type: 'deep_work', duration: '', mood: 7, focus_score: '', notes: '' })
  const [error, setError] = useState('')
  const toast = useToast()

  const load = async () => {
    setLoading(true)
    try {
      const res = await logsApi.list(PAGE_SIZE, 0)
      setLogs(res.data)
      setServerOffset(res.data.length)
      setHasMore(res.data.length === PAGE_SIZE)
    } catch {
      toast.error('Could not load logs. Please try again.')
    }
    setLoading(false)
  }

  const loadMore = async () => {
    setLoadingMore(true)
    try {
      const res = await logsApi.list(PAGE_SIZE, serverOffset)
      setLogs(prev => [...prev, ...res.data])
      setServerOffset(prev => prev + res.data.length)
      setHasMore(res.data.length === PAGE_SIZE)
    } catch {
      toast.error('Could not load more logs. Please try again.')
    }
    setLoadingMore(false)
  }

  useEffect(() => { load() }, [])

  const saveLog = async () => {
    if (!form.duration) return
    setSaving(true); setError('')
    try {
      const res = await logsApi.create({
        activity_type: form.activity_type,
        duration: parseInt(form.duration),
        mood: form.mood,
        focus_score: form.focus_score ? parseInt(form.focus_score) : null,
        notes: form.notes || null,
      })
      setLogs(prev => [res.data, ...prev])
      setForm({ activity_type: 'deep_work', duration: '', mood: 7, focus_score: '', notes: '' })
      setShowForm(false)
      toast.success('Activity logged.')
    } catch (e) { setError(apiErrorMessage(e, 'Failed to save')) }
    setSaving(false)
  }

  const filtered = logs.filter(l => {
    const matchType = filterType === 'all' || l.activity_type === filterType
    const matchSearch = !search || (l.notes || '').toLowerCase().includes(search.toLowerCase())
    return matchType && matchSearch
  })

  const totalMins = logs.reduce((a, b) => a + b.duration, 0)
  const avgMood = logs.length ? (logs.reduce((a, b) => a + (b.mood || 6), 0) / logs.length).toFixed(1) : '-'

  return (
    <div className="pt-14 min-h-screen" style={{ background: 'var(--bg)' }}>
      <div className="max-w-4xl mx-auto px-6 py-8">
        <div className="flex items-center justify-between mb-6">
          <div>
            <h1 className="font-display text-3xl mb-1">Activity Logs</h1>
            <p className="text-sm" style={{ color: 'var(--muted)' }}>
              {logs.length} entries · {formatDuration(totalMins)} total · avg mood {avgMood}/10
            </p>
          </div>
          <div className="flex items-center gap-2">
            <button onClick={load} className="p-2 rounded-lg hover:opacity-70"
              style={{ background: 'var(--surface)', border: '1px solid var(--border)', color: 'var(--muted)' }}>
              <RefreshCw size={14} />
            </button>
            <button onClick={() => setShowForm(true)}
              className="flex items-center gap-2 px-4 py-2 rounded-xl text-sm font-medium transition-all hover:scale-105"
              style={{ background: 'var(--accent)', color: '#fff' }}>
              <Plus size={16} /> Log Activity
            </button>
          </div>
        </div>

        <div className="grid grid-cols-4 gap-3 mb-6">
          {ACTIVITY_TYPES.slice(0, 4).map(t => {
            const items = logs.filter(l => l.activity_type === t.id)
            const total = items.reduce((a, b) => a + b.duration, 0)
            return (
              <div key={t.id} className="p-3 rounded-xl" style={{ background: 'var(--surface)', border: '1px solid var(--border)' }}>
                <div className="flex items-center gap-2 mb-1"><t.icon size={12} style={{ color: t.color }} /><span className="text-xs" style={{ color: 'var(--muted)' }}>{t.label}</span></div>
                <p className="font-mono font-bold text-lg">{formatDuration(total)}</p>
                <p className="font-mono text-xs" style={{ color: 'var(--muted)' }}>{items.length} sessions</p>
              </div>
            )
          })}
        </div>

        <div className="flex items-center gap-3 mb-5">
          <div className="relative flex-1">
            <Search size={13} className="absolute left-3 top-1/2 -translate-y-1/2" style={{ color: 'var(--muted)' }} />
            <input value={search} onChange={e => setSearch(e.target.value)} placeholder="Search notes…"
              className="w-full pl-9 pr-4 py-2 rounded-xl text-sm outline-none"
              style={{ background: 'var(--surface)', border: '1px solid var(--border)', color: 'var(--text)', fontFamily: 'DM Sans' }} />
          </div>
          <div className="flex gap-1.5 overflow-x-auto">
            {['all', ...ACTIVITY_TYPES.map(t => t.id)].map(f => {
              const type = ACTIVITY_TYPES.find(t => t.id === f)
              const isActive = filterType === f
              return (
                <button key={f} onClick={() => setFilterType(f)}
                  className="px-3 py-1.5 rounded-lg text-xs font-mono whitespace-nowrap transition-all capitalize"
                  style={{ background: isActive ? (type?.color + '25' || 'var(--accent2)') : 'var(--surface)', color: isActive ? (type?.color || '#fff') : 'var(--muted)', border: `1px solid ${isActive ? (type?.color + '50' || 'var(--border)') : 'var(--border)'}` }}>
                  {f === 'all' ? 'All' : type?.label || f}
                </button>
              )
            })}
          </div>
        </div>

        {loading ? (
          <div className="flex items-center justify-center py-20">
            <div className="w-6 h-6 border-2 rounded-full animate-spin" style={{ borderColor: 'var(--accent2)', borderTopColor: 'transparent' }} />
          </div>
        ) : filtered.length === 0 ? (
          <div className="text-center py-20" style={{ color: 'var(--muted)' }}>No logs found. Start logging activities!</div>
        ) : (
          <div className="space-y-2">
            {filtered.map(log => {
              const type = getType(log.activity_type)
              return (
                <div key={log.id} className="flex items-center gap-4 p-4 rounded-xl transition-all hover:scale-[1.003]"
                  style={{ background: 'var(--surface)', border: '1px solid var(--border)' }}>
                  <div className="w-10 h-10 rounded-xl flex items-center justify-center flex-shrink-0"
                    style={{ background: type.color + '18', border: `1px solid ${type.color}30` }}>
                    <type.icon size={16} style={{ color: type.color }} />
                  </div>
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2 mb-0.5">
                      <span className="font-medium text-sm">{type.label}</span>
                      {log.focus_score != null && (
                        <span className="font-mono text-xs px-1.5 py-0.5 rounded"
                          style={{ background: 'rgba(99,102,241,0.15)', color: 'var(--accent2)' }}>
                          focus {log.focus_score}
                        </span>
                      )}
                    </div>
                    {log.notes && <p className="text-xs truncate" style={{ color: 'var(--muted)' }}>{log.notes}</p>}
                  </div>
                  <div className="text-right flex-shrink-0">
                    <p className="font-mono text-sm font-bold">{formatDuration(log.duration)}</p>
                    <p className="font-mono text-xs" style={{ color: 'var(--muted)' }}>{formatTime(log.timestamp)}</p>
                  </div>
                  {log.mood != null && (
                    <div className="flex-shrink-0 w-14">
                      <div className="flex items-center gap-1">
                        <div className="flex-1 h-1 rounded-full overflow-hidden" style={{ background: 'var(--surface2)' }}>
                          <div className="h-full rounded-full" style={{ width: `${log.mood * 10}%`, background: log.mood >= 7 ? '#22c55e' : log.mood >= 5 ? '#f59e0b' : '#ef4444' }} />
                        </div>
                        <span className="font-mono text-xs" style={{ color: 'var(--muted)' }}>{log.mood}</span>
                      </div>
                      <p className="font-mono text-xs text-right" style={{ color: 'var(--muted)' }}>mood</p>
                    </div>
                  )}
                </div>
              )
            })}
          </div>
        )}

        {!loading && hasMore && (
          <div className="flex justify-center mt-5">
            <button onClick={loadMore} disabled={loadingMore}
              className="px-5 py-2.5 rounded-xl text-sm transition-all hover:opacity-80 disabled:opacity-50"
              style={{ background: 'var(--surface)', border: '1px solid var(--border)', color: 'var(--muted)' }}>
              {loadingMore ? 'Loading…' : 'Load More'}
            </button>
          </div>
        )}

        {showForm && (
          <div className="fixed inset-0 z-50 flex items-center justify-center px-4" style={{ background: 'rgba(0,0,0,0.75)' }}>
            <div className="w-full max-w-md p-6 rounded-2xl" style={{ background: 'var(--surface)', border: '1px solid var(--border)' }}>
              <div className="flex items-center justify-between mb-5">
                <h3 className="font-medium">Log Activity</h3>
                <button onClick={() => { setShowForm(false); setError('') }} className="p-1 rounded-lg opacity-60 hover:opacity-100"><X size={16} style={{ color: 'var(--text)' }} /></button>
              </div>
              {error && <div className="mb-3 px-3 py-2 rounded-lg text-xs" style={{ background: 'rgba(239,68,68,0.1)', color: '#ef4444', border: '1px solid rgba(239,68,68,0.3)' }}>{error}</div>}
              <div className="space-y-4">
                <div>
                  <label className="text-xs mb-2 block" style={{ color: 'var(--muted)' }}>Activity Type</label>
                  <div className="grid grid-cols-3 gap-2">
                    {ACTIVITY_TYPES.map(t => (
                      <button key={t.id} onClick={() => setForm(f => ({ ...f, activity_type: t.id }))}
                        className="flex items-center gap-1.5 p-2.5 rounded-xl text-xs transition-all"
                        style={{ background: form.activity_type === t.id ? t.color + '20' : 'var(--surface2)', border: `1px solid ${form.activity_type === t.id ? t.color + '60' : 'var(--border)'}`, color: form.activity_type === t.id ? t.color : 'var(--muted)' }}>
                        <t.icon size={11} />{t.label}
                      </button>
                    ))}
                  </div>
                </div>
                <div className="grid grid-cols-2 gap-3">
                  <div>
                    <label htmlFor="duration" className="text-xs mb-1.5 block" style={{ color: 'var(--muted)' }}>Duration (mins)*</label>
                    <input id="duration" type="number" min="1" max="1440" value={form.duration} onChange={e => setForm(f => ({ ...f, duration: e.target.value }))} placeholder="45"
                      className="w-full px-3 py-2.5 rounded-xl text-sm outline-none"
                      style={{ background: 'var(--surface2)', border: '1px solid var(--border)', color: 'var(--text)', fontFamily: 'JetBrains Mono' }} />
                  </div>
                  <div>
                    <label htmlFor="focus_score" className="text-xs mb-1.5 block" style={{ color: 'var(--muted)' }}>Focus Score (0-100)</label>
                    <input id="focus_score" type="number" min="0" max="100" value={form.focus_score} onChange={e => setForm(f => ({ ...f, focus_score: e.target.value }))} placeholder="optional"
                      className="w-full px-3 py-2.5 rounded-xl text-sm outline-none"
                      style={{ background: 'var(--surface2)', border: '1px solid var(--border)', color: 'var(--text)', fontFamily: 'JetBrains Mono' }} />
                  </div>
                </div>
                <div>
                  <label className="text-xs mb-1.5 block" style={{ color: 'var(--muted)' }}>Mood: <strong style={{ color: 'var(--text)' }}>{form.mood}/10</strong></label>
                  <input type="range" min="1" max="10" value={form.mood} onChange={e => setForm(f => ({ ...f, mood: parseInt(e.target.value) }))} className="w-full accent-indigo-500" />
                </div>
                <div>
                  <label className="text-xs mb-1.5 block" style={{ color: 'var(--muted)' }}>Notes</label>
                  <textarea value={form.notes} onChange={e => setForm(f => ({ ...f, notes: e.target.value }))} placeholder="What did you do?" rows={2}
                    className="w-full px-3 py-2.5 rounded-xl text-sm outline-none resize-none"
                    style={{ background: 'var(--surface2)', border: '1px solid var(--border)', color: 'var(--text)', fontFamily: 'DM Sans' }} />
                </div>
              </div>
              <div className="flex gap-3 mt-5">
                <button onClick={() => { setShowForm(false); setError('') }} className="flex-1 py-2.5 rounded-xl text-sm"
                  style={{ background: 'var(--surface2)', color: 'var(--muted)', border: '1px solid var(--border)' }}>Cancel</button>
                <button onClick={saveLog} disabled={saving || !form.duration}
                  className="flex-1 flex items-center justify-center gap-2 py-2.5 rounded-xl text-sm font-medium disabled:opacity-50"
                  style={{ background: 'var(--accent)', color: '#fff' }}>
                  {saving ? 'Saving…' : <><Check size={14} /> Save to PostgreSQL</>}
                </button>
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
