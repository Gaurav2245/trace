import { useEffect, useState } from 'react'
import { Brain, Moon, Timer, AlertTriangle, X, ArrowRight, RefreshCw } from 'lucide-react'
import {
  LineChart, Line, BarChart, Bar, XAxis, YAxis, CartesianGrid,
  Tooltip, ResponsiveContainer, Cell
} from 'recharts'
import { dashboardApi } from '../services/api.js'

const CustomTooltip = ({ active, payload, label }) => {
  if (!active || !payload?.length) return null
  return (
    <div className="px-3 py-2 rounded-lg font-mono text-xs"
      style={{ background: '#1a1a24', border: '1px solid var(--border)' }}>
      <div style={{ color: 'var(--muted)' }}>{label}</div>
      <div style={{ color: 'var(--text)', fontWeight: 600 }}>
        {payload[0].value}
      </div>
    </div>
  )
}

function StatCard({ icon: Icon, label, value, unit, delta, color }) {
  const isPositive = delta >= 0
  return (
    <div className="p-5 rounded-2xl transition-all hover:scale-[1.01]"
      style={{ background: 'var(--surface)', border: '1px solid var(--border)' }}>
      <div className="flex items-center justify-between mb-4">
        <div className="w-9 h-9 rounded-xl flex items-center justify-center"
          style={{ background: color + '18', border: `1px solid ${color}30` }}>
          <Icon size={16} style={{ color }} />
        </div>
        <span className="font-mono text-xs font-semibold"
          style={{ color: isPositive ? '#22c55e' : '#ef4444' }}>
          {isPositive ? '+' : ''}{delta}
        </span>
      </div>
      <p className="text-sm mb-1" style={{ color: 'var(--muted)' }}>{label}</p>
      <p className="font-display text-3xl">
        {value}
        <span className="font-sans text-sm ml-1" style={{ color: 'var(--muted)' }}>{unit}</span>
      </p>
    </div>
  )
}

function Skeleton() {
  return (
    <div className="animate-pulse rounded-2xl h-24"
      style={{ background: 'var(--surface)', border: '1px solid var(--border)' }} />
  )
}

export default function Dashboard() {
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(true)
  const [showAlert, setShowAlert] = useState(true)
  const [error, setError] = useState('')

  const load = async () => {
    setLoading(true); setError('')
    try {
      const res = await dashboardApi.get()
      setData(res.data)
      setShowAlert(true)
    } catch {
      setError('Could not reach backend. Is Docker running?')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { load() }, [])

  if (error) return (
    <div className="pt-14 min-h-screen flex items-center justify-center flex-col gap-4"
      style={{ background: 'var(--bg)' }}>
      <p className="text-sm" style={{ color: '#ef4444' }}>{error}</p>
      <button onClick={load}
        className="flex items-center gap-2 px-4 py-2 rounded-xl text-sm"
        style={{ background: 'var(--accent)', color: '#fff' }}>
        <RefreshCw size={14} /> Retry
      </button>
    </div>
  )

  return (
    <div className="pt-14 min-h-screen" style={{ background: 'var(--bg)' }}>
      <div className="max-w-6xl mx-auto px-6 py-8">

        {/* Header */}
        <div className="flex items-start justify-between mb-8">
          <div>
            <h1 className="font-display text-4xl mb-1">Trace</h1>
            <p className="text-sm" style={{ color: 'var(--muted)' }}>
              Personal Behavior Debugger
              {data && ` · ${data.active_loops} active loops · ${data.resolved_loops} resolved`}
            </p>
          </div>
          <button onClick={load}
            className="flex items-center gap-2 px-3 py-1.5 rounded-lg text-xs transition-all hover:opacity-70"
            style={{ background: 'var(--surface)', color: 'var(--muted)', border: '1px solid var(--border)' }}>
            <RefreshCw size={12} className={loading ? 'animate-spin' : ''} /> Refresh
          </button>
        </div>

        {/* Alert from backend */}
        {data?.alert && showAlert && (
          <div className="mb-6 p-4 rounded-2xl flex items-start gap-4 animate-fadeUp"
            style={{ background: 'var(--surface)', border: '2px solid var(--accent)', boxShadow: '0 0 30px rgba(249,115,22,0.15)' }}>
            <div className="w-10 h-10 rounded-xl flex items-center justify-center flex-shrink-0"
              style={{ background: 'rgba(249,115,22,0.15)' }}>
              <AlertTriangle size={18} style={{ color: 'var(--accent)' }} />
            </div>
            <div className="flex-1">
              <div className="font-medium mb-1">{data.alert.title}</div>
              <p className="text-sm mb-3" style={{ color: 'var(--muted)' }}>{data.alert.message}</p>
              <button className="flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium hover:opacity-90"
                style={{ background: 'var(--accent)', color: '#fff' }}>
                {data.alert.action} <ArrowRight size={14} />
              </button>
            </div>
            <button onClick={() => setShowAlert(false)} className="opacity-50 hover:opacity-100 p-1">
              <X size={16} />
            </button>
          </div>
        )}

        {/* Stat cards */}
        <div className="grid grid-cols-3 gap-4 mb-6">
          {loading ? (
            [0,1,2].map(i => <Skeleton key={i} />)
          ) : data ? (
            <>
              <StatCard icon={Brain} label="Focus Score" value={data.focus_score} unit="/100" delta={data.focus_delta} color="var(--accent2)" />
              <StatCard icon={Moon} label="Sleep Quality" value={data.sleep_hours} unit="hrs" delta={data.sleep_delta} color="#38bdf8" />
              <StatCard icon={Timer} label="Productive Time" value={data.productive_hours} unit="hrs" delta={data.productive_delta} color="var(--accent3)" />
            </>
          ) : null}
        </div>

        {/* Focus Timeline */}
        <div className="mb-6 p-6 rounded-2xl" style={{ background: 'var(--surface)', border: '1px solid var(--border)' }}>
          <div className="flex items-center justify-between mb-6">
            <h2 className="font-medium">Focus Timeline</h2>
            <span className="font-mono text-xs px-2 py-1 rounded"
              style={{ background: 'rgba(99,102,241,0.1)', color: 'var(--accent2)' }}>
              Avg focus by hour of day
            </span>
          </div>
          {loading ? (
            <div className="h-48 rounded-xl animate-pulse" style={{ background: 'var(--surface2)' }} />
          ) : !data?.focus_timeline?.length ? (
            <div className="h-48 flex flex-col items-center justify-center text-center" style={{ color: 'var(--muted)' }}>
              <p className="text-sm">No focus data yet.</p>
              <p className="text-xs mt-1">Log a few activities with a focus score to see your timeline.</p>
            </div>
          ) : (
            <ResponsiveContainer width="100%" height={200}>
              <LineChart data={data.focus_timeline}>
                <defs>
                  <linearGradient id="focusGrad" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="5%" stopColor="#6366f1" stopOpacity={0.3} />
                    <stop offset="95%" stopColor="#6366f1" stopOpacity={0} />
                  </linearGradient>
                </defs>
                <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.05)" />
                <XAxis dataKey="time" tick={{ fill: 'var(--muted)', fontSize: 11, fontFamily: 'JetBrains Mono' }} axisLine={false} tickLine={false} />
                <YAxis domain={[0, 100]} tick={{ fill: 'var(--muted)', fontSize: 11 }} axisLine={false} tickLine={false} />
                <Tooltip content={<CustomTooltip />} />
                <Line type="monotone" dataKey="value" stroke="#6366f1" strokeWidth={2.5}
                  dot={{ r: 3, fill: '#6366f1', strokeWidth: 0 }} activeDot={{ r: 5, fill: '#6366f1' }} />
              </LineChart>
            </ResponsiveContainer>
          )}
        </div>

        {/* Activity distribution + Mood trend */}
        <div className="grid grid-cols-2 gap-4 mb-6">
          <div className="p-6 rounded-2xl" style={{ background: 'var(--surface)', border: '1px solid var(--border)' }}>
            <div className="flex items-center justify-between mb-6">
              <h2 className="font-medium">Daily Activity</h2>
              <span className="font-mono text-xs" style={{ color: 'var(--muted)' }}>hours</span>
            </div>
            {loading ? (
              <div className="h-44 rounded-xl animate-pulse" style={{ background: 'var(--surface2)' }} />
            ) : (
              <ResponsiveContainer width="100%" height={176}>
                <BarChart data={data?.activity_distribution || []} barSize={22}>
                  <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.05)" vertical={false} />
                  <XAxis dataKey="name" tick={{ fill: 'var(--muted)', fontSize: 9, fontFamily: 'JetBrains Mono' }} axisLine={false} tickLine={false} />
                  <YAxis tick={{ fill: 'var(--muted)', fontSize: 10 }} axisLine={false} tickLine={false} />
                  <Tooltip content={<CustomTooltip />} />
                  <Bar dataKey="value" radius={[4, 4, 0, 0]}>
                    {(data?.activity_distribution || []).map((d, i) => (
                      <Cell key={i} fill={d.fill || '#6366f1'} />
                    ))}
                  </Bar>
                </BarChart>
              </ResponsiveContainer>
            )}
          </div>

          <div className="p-6 rounded-2xl" style={{ background: 'var(--surface)', border: '1px solid var(--border)' }}>
            <div className="flex items-center justify-between mb-6">
              <h2 className="font-medium">Mood Trends</h2>
              <span className="font-mono text-xs" style={{ color: 'var(--muted)' }}>weekly</span>
            </div>
            {loading ? (
              <div className="h-44 rounded-xl animate-pulse" style={{ background: 'var(--surface2)' }} />
            ) : (
              <ResponsiveContainer width="100%" height={176}>
                <LineChart data={data?.mood_trend || []}>
                  <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.05)" />
                  <XAxis dataKey="day" tick={{ fill: 'var(--muted)', fontSize: 11, fontFamily: 'JetBrains Mono' }} axisLine={false} tickLine={false} />
                  <YAxis domain={[0, 10]} tick={{ fill: 'var(--muted)', fontSize: 11 }} axisLine={false} tickLine={false} />
                  <Tooltip content={<CustomTooltip />} />
                  <Line type="monotone" dataKey="value" stroke="#22c55e" strokeWidth={2.5}
                    dot={{ r: 3, fill: '#22c55e', strokeWidth: 0 }} activeDot={{ r: 5 }} />
                </LineChart>
              </ResponsiveContainer>
            )}
          </div>
        </div>

        {/* Top Loop from backend */}
        {!loading && data?.top_loop && (
          <div className="p-6 rounded-2xl animate-fadeUp"
            style={{ background: 'var(--surface)', border: '1px solid var(--border)' }}>
            <div className="flex items-center justify-between mb-5">
              <div>
                <h2 className="font-medium">Detected Behavior Loop</h2>
                <p className="text-sm mt-0.5" style={{ color: 'var(--muted)' }}>
                  Repeating pattern · IsolationForest detected
                </p>
              </div>
              <div className="flex items-center gap-2">
                <span className="font-mono text-xs px-2.5 py-1 rounded-full"
                  style={{ background: 'rgba(249,115,22,0.12)', color: 'var(--accent)', border: '1px solid rgba(249,115,22,0.3)' }}>
                  {(data.top_loop.confidence * 100).toFixed(0)}% confidence
                </span>
                <span className="font-mono text-xs px-2.5 py-1 rounded-full"
                  style={{ background: 'var(--surface2)', color: 'var(--muted)', border: '1px solid var(--border)' }}>
                  ×{data.top_loop.occurrences}
                </span>
              </div>
            </div>

            <div className="grid grid-cols-3 gap-3 mb-5">
              {[
                { color: '#6366f1', label: 'TRIGGER', desc: data.top_loop.trigger_desc, sub: data.top_loop.trigger_time },
                { color: '#f97316', label: 'ACTION',  desc: data.top_loop.action_desc },
                { color: '#ef4444', label: 'OUTCOME', desc: data.top_loop.outcome_desc },
              ].map((item, i) => (
                <div key={i} className="p-4 rounded-xl"
                  style={{ background: 'var(--surface2)', border: `1px solid ${item.color}25` }}>
                  <div className="flex items-center gap-1.5 mb-2">
                    <div className="w-1.5 h-1.5 rounded-full" style={{ background: item.color }} />
                    <span className="font-mono text-xs" style={{ color: item.color }}>{item.label}</span>
                  </div>
                  <p className="text-sm font-medium leading-snug">{item.desc}</p>
                  {item.sub && <p className="font-mono text-xs mt-1" style={{ color: 'var(--muted)' }}>{item.sub}</p>}
                </div>
              ))}
            </div>

            {data.top_loop.fixes?.length > 0 && (
              <div className="space-y-2">
                <p className="text-xs mb-2" style={{ color: 'var(--muted)' }}>Fix strategies from database:</p>
                {data.top_loop.fixes.slice(0, 2).map((f, i) => (
                  <div key={i} className="flex items-center gap-3 px-4 py-2.5 rounded-xl text-sm"
                    style={{
                      background: f.applied ? 'rgba(34,197,94,0.08)' : 'var(--surface2)',
                      border: `1px solid ${f.applied ? 'rgba(34,197,94,0.3)' : 'var(--border)'}`,
                      color: f.applied ? '#22c55e' : 'var(--text)',
                    }}>
                    <span>{f.applied ? '✓' : '•'}</span>
                    <span>{f.suggestion}</span>
                  </div>
                ))}
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  )
}
