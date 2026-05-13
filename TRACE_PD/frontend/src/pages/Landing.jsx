import { useNavigate, Link } from 'react-router-dom'
import { useEffect, useRef } from 'react'
import { Zap, ArrowRight, Brain, GitBranch, Terminal, Activity, Shield, Clock } from 'lucide-react'

const CONCEPTS = [
  { label: 'Program',    val: 'Personal routine & daily schedule',       color: '#6366f1' },
  { label: 'Bug',        val: 'Unwanted habit or harmful loop',           color: '#f97316' },
  { label: 'Breakpoint', val: 'Real-time alert on behavior condition',    color: '#22c55e' },
  { label: 'Root Cause', val: 'DoWhy causal inference on your habits',    color: '#ec4899' },
  { label: 'Patch/Fix',  val: 'AI-generated habit-change strategy',       color: '#f59e0b' },
  { label: 'Trace',      val: 'Time-stamped activity log in PostgreSQL',  color: '#38bdf8' },
]

const FEATURES = [
  { icon: Brain,    title: 'Behavior Mapping',  desc: 'Log activities and let Trace build your complete behavioral execution trace stored in PostgreSQL + pgvector.' },
  { icon: GitBranch,title: 'Loop Detection',    desc: 'IsolationForest ML detects anomalous loops: trigger → action → outcome patterns repeating invisibly.' },
  { icon: Terminal, title: 'Causal Debugger',   desc: 'LangGraph pipeline runs DoWhy + EconML on every question — real causation, not correlation.' },
  { icon: Activity, title: 'Live Breakpoints',  desc: 'Real-time WebSocket alerts fire the instant a harmful pattern triggers — like a debugger breakpoint.' },
  { icon: Shield,   title: 'Privacy First',     desc: 'All data in your Docker container. PostgreSQL with bcrypt auth. Right to erasure built-in.' },
  { icon: Clock,    title: 'Fix Strategies',    desc: 'LangGraph Fixer agent generates ranked habit patches with effort/impact scores persisted to DB.' },
]

const STACK = [
  { layer: 'Frontend',    items: ['React 18', 'Tailwind CSS', 'Recharts', 'React Router'] },
  { layer: 'API',         items: ['FastAPI', 'WebSocket', 'JWT Auth', 'Pydantic v2'] },
  { layer: 'AI Agents',   items: ['LangGraph', 'LangChain', 'Multi-Agent', 'RAG'] },
  { layer: 'ML/Causal',   items: ['IsolationForest', 'DoWhy', 'EconML', 'scikit-learn'] },
  { layer: 'Database',    items: ['PostgreSQL', 'pgvector', 'SQLAlchemy async', 'Alembic'] },
  { layer: 'Infra',       items: ['Docker Compose', 'Nginx', 'Prometheus', 'OpenTelemetry'] },
]

export default function Landing() {
  const nav = useNavigate()
  const canvasRef = useRef()

  useEffect(() => {
    const canvas = canvasRef.current
    if (!canvas) return
    const ctx = canvas.getContext('2d')
    let W = canvas.width = window.innerWidth
    let H = canvas.height = window.innerHeight
    const pts = Array.from({ length: 55 }, () => ({
      x: Math.random()*W, y: Math.random()*H,
      vx: (Math.random()-0.5)*0.25, vy: (Math.random()-0.5)*0.25,
      r: Math.random()*1.4+0.4,
    }))
    let raf
    function draw() {
      ctx.clearRect(0,0,W,H)
      pts.forEach(p => {
        p.x+=p.vx; p.y+=p.vy
        if(p.x<0||p.x>W) p.vx*=-1
        if(p.y<0||p.y>H) p.vy*=-1
        ctx.beginPath(); ctx.arc(p.x,p.y,p.r,0,Math.PI*2)
        ctx.fillStyle='rgba(99,102,241,0.45)'; ctx.fill()
      })
      for(let i=0;i<pts.length;i++)
        for(let j=i+1;j<pts.length;j++){
          const d=Math.hypot(pts[i].x-pts[j].x,pts[i].y-pts[j].y)
          if(d<110){
            ctx.beginPath(); ctx.moveTo(pts[i].x,pts[i].y); ctx.lineTo(pts[j].x,pts[j].y)
            ctx.strokeStyle=`rgba(99,102,241,${0.12*(1-d/110)})`; ctx.stroke()
          }
        }
      raf=requestAnimationFrame(draw)
    }
    draw()
    const onResize=()=>{W=canvas.width=window.innerWidth;H=canvas.height=window.innerHeight}
    window.addEventListener('resize',onResize)
    return ()=>{cancelAnimationFrame(raf);window.removeEventListener('resize',onResize)}
  },[])

  return (
    <div className="relative min-h-screen overflow-hidden" style={{background:'#07070a'}}>
      <canvas ref={canvasRef} className="absolute inset-0 pointer-events-none" style={{opacity:0.55}}/>
      <div className="absolute inset-0 grid-bg opacity-35 pointer-events-none"/>
      <div className="absolute top-1/3 left-1/4 w-96 h-96 rounded-full pointer-events-none"
        style={{background:'radial-gradient(circle,rgba(99,102,241,0.1) 0%,transparent 70%)',filter:'blur(60px)'}}/>

      {/* Nav */}
      <header className="relative z-10 flex items-center justify-between px-8 py-5">
        <div className="flex items-center gap-2">
          <div className="w-8 h-8 rounded-lg flex items-center justify-center" style={{background:'var(--accent)'}}>
            <Zap size={15} color="#fff" fill="#fff"/>
          </div>
          <span className="font-mono font-bold tracking-wider">Trace</span>
        </div>
        <div className="flex items-center gap-3">
          <span className="font-mono text-xs px-3 py-1.5 rounded-full" style={{color:'var(--muted)',border:'1px solid var(--border)'}}>PERSONAL_DEBUGGER</span>
          <Link to="/login" className="text-sm px-4 py-2 rounded-lg font-medium transition-all hover:opacity-90"
            style={{background:'var(--surface)',color:'var(--text)',border:'1px solid var(--border)'}}>Sign In</Link>
          <button onClick={()=>nav('/login')} className="text-sm px-4 py-2 rounded-lg font-medium transition-all hover:scale-105"
            style={{background:'var(--accent)',color:'#fff'}}>Open App</button>
        </div>
      </header>

      {/* Hero */}
      <section className="relative z-10 flex flex-col items-center text-center px-6 pt-20 pb-28">
        <div className="mb-6 px-4 py-2 rounded-full font-mono text-xs inline-flex items-center gap-2"
          style={{background:'rgba(249,115,22,0.1)',border:'1px solid rgba(249,115,22,0.3)',color:'var(--accent)'}}>
          <span className="w-1.5 h-1.5 rounded-full animate-pulse" style={{background:'var(--accent)'}}/>
          Personal Behavior Debugger · Docker + PostgreSQL + LangGraph
        </div>
        <h1 className="font-display text-6xl md:text-8xl mb-6 leading-none" style={{maxWidth:900}}>
          Debug your<span className="italic text-glow" style={{color:'var(--accent)'}}> habits</span><br/>like code.
        </h1>
        <p className="text-lg mb-10 max-w-xl leading-relaxed" style={{color:'var(--muted)'}}>
          Trace applies software-debugging concepts to human behavior — breakpoints, root-cause analysis, causal inference, fix strategies — on a real FastAPI + LangGraph + PostgreSQL backend.
        </p>
        <div className="flex items-center gap-4 mb-16">
          <button onClick={()=>nav('/login')} className="flex items-center gap-2 px-6 py-3 rounded-xl font-medium text-sm transition-all hover:scale-105"
            style={{background:'var(--accent)',color:'#fff',boxShadow:'0 0 30px rgba(249,115,22,0.3)'}}>
            Start Debugging <ArrowRight size={16}/>
          </button>
          <button onClick={()=>nav('/login')} className="flex items-center gap-2 px-6 py-3 rounded-xl font-medium text-sm glass transition-all"
            style={{color:'var(--text)'}}>
            <Terminal size={16}/> Try AI Debugger
          </button>
        </div>

        {/* Terminal mockup */}
        <div className="w-full max-w-2xl rounded-2xl overflow-hidden text-left glow-indigo" style={{border:'1px solid var(--border)'}}>
          <div className="flex items-center gap-2 px-4 py-3" style={{background:'var(--surface2)',borderBottom:'1px solid var(--border)'}}>
            <span className="w-3 h-3 rounded-full" style={{background:'#ff5f57'}}/>
            <span className="w-3 h-3 rounded-full" style={{background:'#febc2e'}}/>
            <span className="w-3 h-3 rounded-full" style={{background:'#28c840'}}/>
            <span className="ml-3 font-mono text-xs" style={{color:'var(--muted)'}}>PERSONAL_DEBUGGER — trace --debug</span>
          </div>
          <div className="p-6 font-mono text-sm space-y-3" style={{background:'var(--surface)'}}>
            <div><span style={{color:'var(--muted)'}}>$ </span><span>trace debug "Why do I procrastinate after lunch?"</span></div>
            <div className="pl-2 space-y-1 text-xs" style={{borderLeft:'2px solid var(--border)',color:'var(--muted)'}}>
              <div>🔍 [Parser] Intent: focus_analysis</div>
              <div>📊 [Retriever] Loaded 30 logs from PostgreSQL</div>
              <div>🧠 [Causal] DoWhy back-door adjustment running…</div>
              <div>🛠  [Fixer] Generating fix strategies…</div>
            </div>
            <div style={{color:'var(--accent)'}}>▶ Root cause: <span style={{color:'var(--text)'}}>Phone mediates 68% of focus drop (p=0.002)</span></div>
            <div style={{color:'#22c55e'}}>✅ Fix: <span style={{color:'var(--text)'}}>25-min Pomodoro + 60-sec app friction</span></div>
            <div className="text-xs" style={{color:'var(--muted)'}}>↳ Confidence: 82% · Tokens: 850 · Saved to PostgreSQL ✓</div>
          </div>
        </div>
      </section>

      {/* Concepts */}
      <section className="relative z-10 px-6 py-20" style={{borderTop:'1px solid var(--border)'}}>
        <div className="max-w-4xl mx-auto">
          <div className="text-center mb-12">
            <h2 className="font-display text-4xl mb-3">Software → Behavior</h2>
            <p style={{color:'var(--muted)'}}>Every debugging concept maps to a real behavioral pattern</p>
          </div>
          <div className="grid grid-cols-2 md:grid-cols-3 gap-4">
            {CONCEPTS.map((c,i)=>(
              <div key={i} className="p-4 rounded-xl glass transition-all hover:scale-[1.03]" style={{border:'1px solid var(--border)'}}>
                <div className="font-mono text-xs mb-2 px-2 py-0.5 rounded inline-block"
                  style={{background:c.color+'20',color:c.color,border:`1px solid ${c.color}40`}}>{c.label}</div>
                <p className="text-sm" style={{color:'var(--muted)'}}>{c.val}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* Features */}
      <section className="relative z-10 px-6 py-20" style={{borderTop:'1px solid var(--border)'}}>
        <div className="max-w-5xl mx-auto">
          <div className="text-center mb-12">
            <h2 className="font-display text-4xl mb-3">Built to <span className="italic" style={{color:'var(--accent)'}}>actually work</span></h2>
            <p style={{color:'var(--muted)'}}>Full backend — not a mockup. Every feature hits PostgreSQL.</p>
          </div>
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-5">
            {FEATURES.map((f,i)=>(
              <div key={i} className="p-6 rounded-2xl glass group transition-all hover:scale-[1.02]" style={{border:'1px solid var(--border)'}}>
                <div className="w-10 h-10 rounded-xl flex items-center justify-center mb-4 group-hover:scale-110 transition-transform"
                  style={{background:'rgba(99,102,241,0.15)',border:'1px solid rgba(99,102,241,0.3)'}}>
                  <f.icon size={18} style={{color:'var(--accent2)'}}/>
                </div>
                <h3 className="font-medium mb-2">{f.title}</h3>
                <p className="text-sm leading-relaxed" style={{color:'var(--muted)'}}>{f.desc}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* Stack */}
      <section className="relative z-10 px-6 py-20" style={{borderTop:'1px solid var(--border)'}}>
        <div className="max-w-5xl mx-auto">
          <div className="text-center mb-12">
            <h2 className="font-display text-4xl mb-3">Full-Stack Architecture</h2>
            <p style={{color:'var(--muted)'}}>Every layer purpose-built, every service Dockerized</p>
          </div>
          <div className="grid grid-cols-2 md:grid-cols-3 gap-4">
            {STACK.map((s,i)=>(
              <div key={i} className="p-5 rounded-2xl" style={{background:'var(--surface)',border:'1px solid var(--border)'}}>
                <p className="font-mono text-xs mb-3 font-bold" style={{color:'var(--accent)'}}>{s.layer}</p>
                <div className="space-y-1.5">
                  {s.items.map((item,j)=>(
                    <div key={j} className="flex items-center gap-2 text-sm" style={{color:'var(--muted)'}}>
                      <div className="w-1 h-1 rounded-full flex-shrink-0" style={{background:'var(--accent2)'}}/>{item}
                    </div>
                  ))}
                </div>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* CTA */}
      <section className="relative z-10 px-6 py-24 text-center" style={{borderTop:'1px solid var(--border)'}}>
        <div className="max-w-2xl mx-auto">
          <h2 className="font-display text-5xl mb-4">Ready to <span className="italic" style={{color:'var(--accent)'}}>debug</span> yourself?</h2>
          <p className="mb-8" style={{color:'var(--muted)'}}>
            Run <code className="font-mono text-sm px-2 py-1 rounded" style={{background:'var(--surface2)',color:'var(--accent)'}}>docker compose up</code> and start tracing.
          </p>
          <button onClick={()=>nav('/login')} className="inline-flex items-center gap-2 px-8 py-4 rounded-xl font-medium transition-all hover:scale-105"
            style={{background:'var(--accent)',color:'#fff',boxShadow:'0 0 40px rgba(249,115,22,0.35)'}}>
            Open Dashboard <ArrowRight size={18}/>
          </button>
        </div>
      </section>

      <footer className="relative z-10 px-6 py-8 text-center font-mono text-xs" style={{color:'var(--muted)',borderTop:'1px solid var(--border)'}}>
        PERSONAL_DEBUGGER · Trace v1.0 · FastAPI + LangGraph + PostgreSQL + React + Docker
      </footer>
    </div>
  )
}
