import { useState, useEffect } from 'react'
import { GitBranch, ChevronRight, Zap, Check, RefreshCw, TrendingDown } from 'lucide-react'
import { loopsApi, fixesApi } from '../services/api.js'
import { useToast } from '../store/ToastContext.jsx'

const STATUS_STYLE = {
  active:     { bg: 'rgba(249,115,22,0.12)', border: 'rgba(249,115,22,0.4)', text: '#f97316' },
  resolved:   { bg: 'rgba(34,197,94,0.12)',  border: 'rgba(34,197,94,0.4)',  text: '#22c55e' },
  monitoring: { bg: 'rgba(99,102,241,0.12)', border: 'rgba(99,102,241,0.4)', text: '#6366f1' },
}

function ConfidenceBar({ value }) {
  const pct = Math.round(value * 100)
  const color = pct >= 80 ? '#f97316' : pct >= 60 ? '#f59e0b' : '#6366f1'
  return (
    <div className="flex items-center gap-2">
      <div className="flex-1 h-1.5 rounded-full overflow-hidden" style={{ background: 'var(--surface2)' }}>
        <div className="h-full rounded-full transition-all" style={{ width: `${pct}%`, background: color }} />
      </div>
      <span className="font-mono text-xs font-bold" style={{ color }}>{pct}%</span>
    </div>
  )
}

function EmptyState() {
  return (
    <div className="flex flex-col items-center py-24" style={{ color: 'var(--muted)' }}>
      <GitBranch size={36} className="mb-4 opacity-20" />
      <p className="text-sm">No loops detected yet.</p>
      <p className="text-xs mt-1">Keep logging activities — patterns appear after ~5 entries.</p>
    </div>
  )
}

export default function Loops() {
  const [loops, setLoops]   = useState([])
  const [selected, setSelected] = useState(null)
  const [filter, setFilter] = useState('all')
  const [loading, setLoading] = useState(true)
  const [applying, setApplying] = useState({})
  const toast = useToast()

  const load = async () => {
    setLoading(true)
    try {
      const res = await loopsApi.list()
      setLoops(res.data)
      if (res.data.length) setSelected(s => s ?? res.data[0])
    } catch {
      toast.error('Could not load loops. Please try again.')
    }
    setLoading(false)
  }

  useEffect(() => { load() }, [])

  const changeStatus = async (id, status) => {
    try {
      await loopsApi.updateStatus(id, status)
      setLoops(prev => prev.map(l => l.id === id ? { ...l, status } : l))
      if (selected?.id === id) setSelected(s => ({ ...s, status }))
      toast.success(`Loop marked as ${status}.`)
    } catch {
      toast.error('Could not update status. Please try again.')
    }
  }

  const toggleFix = async (fixId, current) => {
    setApplying(a => ({ ...a, [fixId]: true }))
    try {
      await fixesApi.apply(fixId, !current)
      const patch = (list) => list.map(f => f.id === fixId ? { ...f, applied: !current } : f)
      setLoops(prev => prev.map(l => ({ ...l, fixes: patch(l.fixes || []) })))
      setSelected(s => s ? ({ ...s, fixes: patch(s.fixes || []) }) : s)
    } catch {
      toast.error('Could not update fix. Please try again.')
    }
    setApplying(a => ({ ...a, [fixId]: false }))
  }

  const filtered = filter === 'all' ? loops : loops.filter(l => l.status === filter)
  const activeCount   = loops.filter(l => l.status === 'active').length
  const resolvedCount = loops.filter(l => l.status === 'resolved').length

  return (
    <div className="pt-14 min-h-screen" style={{ background: 'var(--bg)' }}>
      <div className="max-w-6xl mx-auto px-6 py-8">

        {/* Header */}
        <div className="flex items-center justify-between mb-8">
          <div>
            <h1 className="font-display text-3xl mb-1 flex items-center gap-3">
              <GitBranch size={28} style={{ color: 'var(--accent)' }} />
              Behavior Loops
            </h1>
            <p className="text-sm" style={{ color: 'var(--muted)' }}>
              {activeCount} active · {resolvedCount} resolved · IsolationForest anomaly detection
            </p>
          </div>
          <div className="flex items-center gap-2">
            {['all', 'active', 'monitoring', 'resolved'].map(f => (
              <button key={f} onClick={() => setFilter(f)}
                className="px-3 py-1.5 rounded-lg text-xs font-mono capitalize transition-all"
                style={{
                  background: filter === f ? 'var(--accent2)' : 'var(--surface)',
                  color: filter === f ? '#fff' : 'var(--muted)',
                  border: '1px solid var(--border)',
                }}>
                {f}
              </button>
            ))}
            <button onClick={load}
              className="p-2 rounded-lg hover:opacity-70 transition-opacity"
              style={{ background: 'var(--surface)', border: '1px solid var(--border)', color: 'var(--muted)' }}>
              <RefreshCw size={13} className={loading ? 'animate-spin' : ''} />
            </button>
          </div>
        </div>

        {loading ? (
          <div className="flex items-center justify-center py-24">
            <div className="w-7 h-7 border-2 rounded-full animate-spin"
              style={{ borderColor: 'var(--accent2)', borderTopColor: 'transparent' }} />
          </div>
        ) : filtered.length === 0 ? <EmptyState /> : (
          <div className="grid grid-cols-5 gap-5">

            {/* ── Loop list ── */}
            <div className="col-span-2 space-y-3 overflow-y-auto" style={{ maxHeight: 'calc(100vh - 180px)' }}>
              {filtered.map(loop => {
                const sc  = STATUS_STYLE[loop.status] || STATUS_STYLE.monitoring
                const sel = selected?.id === loop.id
                return (
                  <button key={loop.id} onClick={() => setSelected(loop)}
                    className="w-full text-left p-4 rounded-2xl transition-all hover:scale-[1.01]"
                    style={{
                      background: sel ? 'var(--surface2)' : 'var(--surface)',
                      border: `1px solid ${sel ? 'var(--accent2)' : 'var(--border)'}`,
                      boxShadow: sel ? '0 0 20px rgba(99,102,241,0.15)' : 'none',
                    }}>
                    <div className="flex items-center justify-between mb-3">
                      <span className="font-mono text-xs px-2 py-0.5 rounded-full capitalize"
                        style={{ background: sc.bg, color: sc.text, border: `1px solid ${sc.border}` }}>
                        {loop.status}
                      </span>
                      <span className="font-mono text-xs" style={{ color: 'var(--muted)' }}>
                        ×{loop.occurrences}
                      </span>
                    </div>
                    <p className="text-sm font-medium mb-1 truncate">{loop.trigger_desc}</p>
                    <div className="flex items-center gap-1 text-xs mb-3" style={{ color: 'var(--muted)' }}>
                      <span className="truncate max-w-[80px]">{loop.action_desc}</span>
                      <ChevronRight size={10} className="flex-shrink-0" />
                      <span className="truncate max-w-[80px]">{loop.outcome_desc}</span>
                    </div>
                    <ConfidenceBar value={loop.confidence} />
                  </button>
                )
              })}
            </div>

            {/* ── Detail panel ── */}
            {selected && (
              <div className="col-span-3 space-y-4 overflow-y-auto" style={{ maxHeight: 'calc(100vh - 180px)' }}>

                {/* Anatomy */}
                <div className="p-6 rounded-2xl" style={{ background: 'var(--surface)', border: '1px solid var(--border)' }}>
                  <p className="font-mono text-xs mb-4" style={{ color: 'var(--muted)' }}>LOOP ANATOMY</p>
                  <div className="grid grid-cols-3 gap-3">
                    {[
                      { color: '#6366f1', label: 'TRIGGER', desc: selected.trigger_desc, sub: selected.trigger_time },
                      { color: '#f97316', label: 'ACTION',  desc: selected.action_desc },
                      { color: '#ef4444', label: 'OUTCOME', desc: selected.outcome_desc },
                    ].map((item, i) => (
                      <div key={i} className="relative p-4 rounded-xl"
                        style={{ background: 'var(--surface2)', border: `1px solid ${item.color}25` }}>
                        {i > 0 && (
                          <ChevronRight size={14} className="absolute -left-2 top-1/2 -translate-y-1/2 z-10"
                            style={{ color: 'var(--muted)' }} />
                        )}
                        <div className="flex items-center gap-1.5 mb-2">
                          <div className="w-1.5 h-1.5 rounded-full" style={{ background: item.color }} />
                          <span className="font-mono text-xs" style={{ color: item.color }}>{item.label}</span>
                        </div>
                        <p className="text-sm font-medium leading-snug">{item.desc}</p>
                        {item.sub && (
                          <p className="font-mono text-xs mt-1" style={{ color: 'var(--muted)' }}>{item.sub}</p>
                        )}
                      </div>
                    ))}
                  </div>
                </div>

                {/* Causal analysis */}
                {selected.causal_estimate && (
                  <div className="p-5 rounded-2xl"
                    style={{ background: 'var(--surface)', border: '1px solid var(--border)' }}>
                    <div className="flex items-center gap-2 mb-3">
                      <Zap size={14} style={{ color: 'var(--accent)' }} />
                      <h3 className="font-medium text-sm">Causal Analysis</h3>
                      <span className="font-mono text-xs px-2 py-0.5 rounded"
                        style={{ background: 'rgba(249,115,22,0.1)', color: 'var(--accent)' }}>
                        Causal Heuristic
                      </span>
                    </div>
                    <p className="text-sm leading-relaxed mb-4" style={{ color: 'var(--muted)' }}>
                      {selected.causal_estimate}
                    </p>
                    <ConfidenceBar value={selected.confidence} />
                  </div>
                )}

                {/* Fix strategies */}
                {selected.fixes?.length > 0 && (
                  <div className="p-5 rounded-2xl"
                    style={{ background: 'var(--surface)', border: '1px solid var(--border)' }}>
                    <h3 className="font-medium text-sm mb-4">Fix Strategies</h3>
                    <div className="space-y-2">
                      {selected.fixes.map(fix => (
                        <div key={fix.id} className="flex items-center gap-3 p-3 rounded-xl"
                          style={{ background: 'var(--surface2)', border: '1px solid var(--border)' }}>
                          <div className="flex-1">
                            <p className="text-sm font-medium mb-1">{fix.suggestion}</p>
                            <div className="flex items-center gap-2">
                              <span className="font-mono text-xs px-2 py-0.5 rounded"
                                style={{ background: 'rgba(34,197,94,0.1)', color: '#22c55e' }}>
                                Impact: {fix.impact}
                              </span>
                              <span className="font-mono text-xs px-2 py-0.5 rounded"
                                style={{ background: 'rgba(99,102,241,0.1)', color: '#6366f1' }}>
                                Effort: {fix.effort}
                              </span>
                            </div>
                          </div>
                          <button
                            disabled={!!applying[fix.id]}
                            onClick={() => toggleFix(fix.id, fix.applied)}
                            className="w-8 h-8 rounded-lg flex items-center justify-center transition-all disabled:opacity-50"
                            style={{
                              background: fix.applied ? 'rgba(34,197,94,0.2)' : 'var(--surface)',
                              border: `1px solid ${fix.applied ? '#22c55e' : 'var(--border)'}`,
                            }}>
                            <Check size={14} style={{ color: fix.applied ? '#22c55e' : 'var(--muted)' }} />
                          </button>
                        </div>
                      ))}
                    </div>
                  </div>
                )}

                {/* Status controls */}
                <div className="flex gap-2">
                  {['active', 'monitoring', 'resolved']
                    .filter(s => s !== selected.status)
                    .map(s => (
                      <button key={s} onClick={() => changeStatus(selected.id, s)}
                        className="flex-1 py-2.5 rounded-xl text-xs font-medium capitalize transition-all hover:opacity-80"
                        style={{ background: 'var(--surface)', border: '1px solid var(--border)', color: 'var(--muted)' }}>
                        Mark as {s}
                      </button>
                    ))}
                </div>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  )
}
