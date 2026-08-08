import { useState, useRef, useEffect } from 'react'
import { Send, Terminal, Brain, RotateCcw, ChevronRight, Zap } from 'lucide-react'
import { debugApi } from '../services/api.js'

const SUGGESTIONS = [
  'Why do I always feel tired at 3PM?',
  'What is causing my procrastination after lunch?',
  'How can I improve my sleep quality?',
  'Explain my most common behavior loop',
  'What habit should I fix first?',
]

const WELCOME = {
  role: 'assistant',
  content: `**Trace Behavior Debugger** — LangGraph Multi-Agent Pipeline\n\nI have access to your full behavior trace: activity logs, focus scores, sleep data, and detected loops stored in PostgreSQL.\n\nI run 4 agents on every query:\n- **Parser** → intent classification\n- **Retriever** → context from your logs\n- **Causal** → statistical causal analysis\n- **Fixer** → actionable fix strategies\n\nAsk me anything about your patterns.`,
  time: 'now',
  agent_trace: [],
  tokens_used: 0,
}

const AGENT_STEPS = [
  '[Parser] Classifying query intent…',
  '[Retriever] Fetching behavior logs from PostgreSQL…',
  '[Causal] Running statistical causal analysis…',
  '[Fixer] Generating fix strategies…',
]

// Renders **bold** and "- bullet" lines as real React elements (no HTML
// injection) so message content — including a user's own stored chat
// history — can never execute as markup.
function RichText({ text }) {
  return String(text ?? '').split('\n').map((line, i) => {
    const isBullet = line.startsWith('- ')
    const body = isBullet ? line.slice(2) : line
    const parts = body.split(/(\*\*.*?\*\*)/g).filter(Boolean)
    return (
      <div key={i}>
        {isBullet && '• '}
        {parts.map((part, j) => (
          part.startsWith('**') && part.endsWith('**')
            ? <strong key={j}>{part.slice(2, -2)}</strong>
            : <span key={j}>{part}</span>
        ))}
        {line === '' && ' '}
      </div>
    )
  })
}

function MessageBubble({ msg, expanded, onToggleTrace }) {
  const isUser = msg.role === 'user'
  return (
    <div className={`flex ${isUser ? 'justify-end' : 'justify-start'} mb-4`}>
      {!isUser && (
        <div className="w-8 h-8 rounded-xl flex items-center justify-center mr-3 flex-shrink-0 mt-1"
          style={{ background: 'rgba(99,102,241,0.2)', border: '1px solid rgba(99,102,241,0.3)' }}>
          <Brain size={14} style={{ color: 'var(--accent2)' }} />
        </div>
      )}
      <div className="max-w-[76%]">
        <div className="px-4 py-3 rounded-2xl text-sm leading-relaxed"
          style={{
            background: isUser ? 'var(--accent2)' : 'var(--surface)',
            color: 'var(--text)',
            border: isUser ? 'none' : '1px solid var(--border)',
            borderTopLeftRadius: !isUser ? 4 : undefined,
            borderTopRightRadius: isUser ? 4 : undefined,
          }}>
          <RichText text={msg.content} />
        </div>
        {msg.agent_trace?.length > 0 && (
          <div className="mt-2">
            <button onClick={onToggleTrace}
              className="flex items-center gap-1.5 font-mono text-xs px-2 py-1 rounded-lg transition-all hover:opacity-80"
              style={{ color: 'var(--muted)', background: 'var(--surface2)', border: '1px solid var(--border)' }}>
              <Zap size={10} style={{ color: 'var(--accent)' }} />
              {expanded ? 'Hide' : 'Show'} agent trace ({msg.agent_trace.length} steps)
              {msg.tokens_used > 0 && <span style={{ color: 'var(--accent)' }}> · {msg.tokens_used} tokens</span>}
            </button>
            {expanded && (
              <div className="mt-2 p-3 rounded-xl font-mono text-xs space-y-1.5"
                style={{ background: 'var(--surface2)', border: '1px solid var(--border)' }}>
                {msg.agent_trace.map((step, i) => (
                  <div key={i} className="flex items-start gap-2">
                    <span style={{ color: 'var(--accent3)', flexShrink: 0 }}>✓</span>
                    <span style={{ color: 'var(--muted)' }}>{step}</span>
                  </div>
                ))}
              </div>
            )}
          </div>
        )}
        <p className="text-xs mt-1 px-1" style={{ color: 'var(--muted)' }}>
          {isUser ? 'You' : 'Trace Debugger'} · {msg.time}
        </p>
      </div>
    </div>
  )
}

function TypingDots({ steps, current }) {
  return (
    <div className="flex justify-start mb-4">
      <div className="w-8 h-8 rounded-xl flex items-center justify-center mr-3 flex-shrink-0 mt-1"
        style={{ background: 'rgba(99,102,241,0.2)', border: '1px solid rgba(99,102,241,0.3)' }}>
        <Brain size={14} style={{ color: 'var(--accent2)' }} />
      </div>
      <div className="p-4 rounded-2xl rounded-tl-sm font-mono text-xs space-y-2"
        style={{ background: 'var(--surface)', border: '1px solid var(--border)' }}>
        {steps.map((s, i) => (
          <div key={i} className="flex items-center gap-2"
            style={{ color: i < current ? 'var(--accent3)' : 'var(--muted)', opacity: i < current ? 1 : 0.4 }}>
            <span>{i < current ? '✓' : '○'}</span>{s}
          </div>
        ))}
        {current < steps.length && (
          <div className="flex items-center gap-1 pt-1">
            {[0,1,2].map(i => (
              <div key={i} className="w-1.5 h-1.5 rounded-full animate-bounce"
                style={{ background: 'var(--accent2)', animationDelay: `${i * 0.15}s` }} />
            ))}
          </div>
        )}
      </div>
    </div>
  )
}

export default function Chat() {
  const [messages, setMessages] = useState([WELCOME])
  const [input, setInput] = useState('')
  const [loading, setLoading] = useState(false)
  const [agentStep, setAgentStep] = useState(0)
  const [expandedTraces, setExpandedTraces] = useState({})
  const bottomRef = useRef()

  useEffect(() => { bottomRef.current?.scrollIntoView({ behavior: 'smooth' }) }, [messages, loading])

  useEffect(() => {
    debugApi.history().then(res => {
      if (res.data?.length) {
        const loaded = res.data.map(m => ({
          role: m.role,
          content: m.content,
          time: new Date(m.created_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
          agent_trace: [],
          tokens_used: 0,
        }))
        setMessages([WELCOME, ...loaded])
      }
    }).catch(() => {})
  }, [])

  async function send(text) {
    const q = (text || input).trim()
    if (!q || loading) return
    setInput('')
    const now = new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
    setMessages(prev => [...prev, { role: 'user', content: q, time: now, agent_trace: [], tokens_used: 0 }])
    setLoading(true)
    setAgentStep(0)

    const stepTimer = setInterval(() => setAgentStep(s => Math.min(s + 1, AGENT_STEPS.length)), 650)

    try {
      const res = await debugApi.query(q)
      clearInterval(stepTimer)
      setAgentStep(AGENT_STEPS.length)
      const { cause, suggestion, confidence, agent_trace, tokens_used } = res.data
      setMessages(prev => [...prev, {
        role: 'assistant',
        content: `${cause}\n\n${suggestion}`,
        time: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
        agent_trace: agent_trace || [],
        tokens_used: tokens_used || 0,
        confidence,
      }])
    } catch {
      clearInterval(stepTimer)
      setMessages(prev => [...prev, {
        role: 'assistant',
        content: 'Backend connection error. Make sure the FastAPI server is running (`docker compose up` or `uvicorn app.main:app`).',
        time: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
        agent_trace: [], tokens_used: 0,
      }])
    } finally {
      setLoading(false)
      setAgentStep(0)
    }
  }

  return (
    <div className="pt-14 h-screen flex flex-col" style={{ background: 'var(--bg)' }}>
      <div className="flex items-center justify-between px-6 py-3 flex-shrink-0"
        style={{ borderBottom: '1px solid var(--border)', background: 'var(--surface)' }}>
        <div className="flex items-center gap-3">
          <div className="w-9 h-9 rounded-xl flex items-center justify-center"
            style={{ background: 'rgba(99,102,241,0.2)', border: '1px solid rgba(99,102,241,0.4)' }}>
            <Terminal size={16} style={{ color: 'var(--accent2)' }} />
          </div>
          <div>
            <h2 className="font-medium text-sm">Behavior Debugger</h2>
            <p className="font-mono text-xs" style={{ color: 'var(--muted)' }}>FastAPI → LangGraph → Causal Analysis → PostgreSQL</p>
          </div>
        </div>
        <div className="flex items-center gap-3">
          <div className="flex items-center gap-1.5">
            <div className="w-2 h-2 rounded-full animate-pulse" style={{ background: '#22c55e' }} />
            <span className="font-mono text-xs" style={{ color: 'var(--muted)' }}>4 agents active</span>
          </div>
          <button onClick={() => setMessages([WELCOME])} className="p-2 rounded-lg hover:opacity-70" style={{ color: 'var(--muted)' }}>
            <RotateCcw size={14} />
          </button>
        </div>
      </div>

      <div className="flex gap-2 px-6 py-2.5 flex-shrink-0 overflow-x-auto"
        style={{ borderBottom: '1px solid var(--border)', background: 'var(--surface)' }}>
        {['Parser','Retriever','Causal','Fixer'].map((a, i) => (
          <div key={a} className="flex-shrink-0 flex items-center gap-1.5 px-3 py-1 rounded-full font-mono text-xs"
            style={{ background: 'var(--surface2)', border: '1px solid var(--border)', color: 'var(--muted)' }}>
            <div className="w-1.5 h-1.5 rounded-full" style={{ background: ['#6366f1','#38bdf8','#f97316','#22c55e'][i] }} />
            {a}
          </div>
        ))}
        <div className="flex-shrink-0 flex items-center gap-1.5 px-3 py-1 rounded-full font-mono text-xs"
          style={{ background: 'rgba(99,102,241,0.1)', border: '1px solid rgba(99,102,241,0.3)', color: 'var(--accent2)' }}>
          PostgreSQL + pgvector
        </div>
      </div>

      <div className="flex-1 overflow-y-auto px-6 py-6">
        {messages.map((m, i) => (
          <MessageBubble key={i} msg={m}
            expanded={!!expandedTraces[i]}
            onToggleTrace={() => setExpandedTraces(t => ({ ...t, [i]: !t[i] }))} />
        ))}
        {loading && <TypingDots steps={AGENT_STEPS} current={agentStep} />}
        <div ref={bottomRef} />
      </div>

      {messages.length <= 1 && (
        <div className="px-6 pb-3 flex gap-2 overflow-x-auto flex-shrink-0">
          {SUGGESTIONS.map(s => (
            <button key={s} onClick={() => send(s)}
              className="flex-shrink-0 flex items-center gap-1.5 px-3 py-2 rounded-xl text-xs transition-all hover:scale-[1.02]"
              style={{ background: 'var(--surface)', border: '1px solid var(--border)', color: 'var(--muted)', whiteSpace: 'nowrap' }}>
              <ChevronRight size={12} style={{ color: 'var(--accent)' }} />{s}
            </button>
          ))}
        </div>
      )}

      <div className="px-6 py-4 flex-shrink-0" style={{ borderTop: '1px solid var(--border)' }}>
        <div className="flex gap-3 items-end">
          <textarea value={input} onChange={e => setInput(e.target.value)}
            onKeyDown={e => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); send() } }}
            placeholder="Ask about your behavior patterns…" rows={1}
            className="flex-1 resize-none px-4 py-3 rounded-xl text-sm outline-none"
            style={{ background: 'var(--surface)', border: '1px solid var(--border)', color: 'var(--text)', fontFamily: 'DM Sans', lineHeight: 1.5 }} />
          <button onClick={() => send()} disabled={!input.trim() || loading}
            className="w-11 h-11 rounded-xl flex items-center justify-center flex-shrink-0 transition-all hover:scale-105 disabled:opacity-40"
            style={{ background: 'var(--accent)', color: '#fff' }}>
            <Send size={16} />
          </button>
        </div>
        <p className="text-xs mt-2 text-center" style={{ color: 'var(--muted)' }}>
          Powered by LangGraph · History persisted in PostgreSQL · Data never leaves your container
        </p>
      </div>
    </div>
  )
}
