import { useEffect, useMemo, useRef, useState } from 'react'
import { FloorScene } from './floor/FloorScene.js'
import { useAgentStatus } from './floor/useAgentStatus.js'
import { COLORS, WORLD, stateColor } from './floor/tokens.js'

const TEAM_ID = 'company-brain'

// Static desk layout so avatars ALWAYS render, even before the WS snapshot
// arrives. Mirrors app/telemetry/floor_config.py.
const DEFAULT_AGENTS = [
  { agent_id: 'top_agent', name: 'Top Agent', role: 'Chief of Staff', accent: '#6E1423', desk: { x: 480, y: 60 }, state: 'idle' },
  { agent_id: 'market_research_agent', name: 'Market Research Agent', role: 'research', accent: '#2C7A78', desk: { x: 345, y: 105 }, state: 'idle' },
  { agent_id: 'briefing_agent', name: 'Briefing Agent', role: 'briefings', accent: '#5B4B8A', desk: { x: 480, y: 175 }, state: 'idle' },
  { agent_id: 'strategy_agent', name: 'Strategy Agent', role: 'campaigns', accent: '#3C6E47', desk: { x: 615, y: 105 }, state: 'idle' },
  { agent_id: 'refinement_agent', name: 'Refinement Agent', role: 'polish', accent: '#C25B4E', desk: { x: 750, y: 170 }, state: 'idle' },
  { agent_id: 'sales_agent', name: 'Sales Agent', role: 'lead qualification', accent: '#2F4B7C', desk: { x: 240, y: 390 }, state: 'idle' },
  { agent_id: 'onboarding_agent', name: 'Onboarding Agent', role: 'client setup', accent: '#3A6EA5', desk: { x: 365, y: 455 }, state: 'idle' },
  { agent_id: 'negotiation_agent', name: 'Negotiation Agent', role: 'pricing', accent: '#6B2737', desk: { x: 480, y: 485 }, state: 'idle' },
  { agent_id: 'finance_agent', name: 'Finance Agent', role: 'invoices', accent: '#1F3A5F', desk: { x: 595, y: 455 }, state: 'idle' },
  { agent_id: 'legal_agent', name: 'Legal Agent', role: 'contracts', accent: '#2B2B33', desk: { x: 720, y: 390 }, state: 'idle' },
]

// Role-based professional outfit colors (mirror portrait.js ROLE_OUTFITS)
const ROLE_SUIT = {
  top_agent: '#6E1423',
  sales_agent: '#2F4B7C',
  legal_agent: '#2B2B33',
  finance_agent: '#1F3A5F',
  negotiation_agent: '#6B2737',
  strategy_agent: '#3C6E47',
  market_research_agent: '#2C7A78',
  briefing_agent: '#5B4B8A',
  refinement_agent: '#C25B4E',
  onboarding_agent: '#3A6EA5',
}

// DOM fallback: guaranteed-visible floor if Pixi ever fails to render.
// Shows the same avatars at their desks, dressed per role, no WebGL needed.
function FloorFallback({ entries, onSelect }) {
  return (
    <div
      className="floor-fallback"
      style={{ aspectRatio: `${WORLD.width} / ${WORLD.height}` }}
    >
      <div className="ff-table" style={{ left: '50%', top: `${(330 / WORLD.height) * 100}%` }} />
      {entries.map((a) => {
        const suit = ROLE_SUIT[a.agent_id] || '#546170'
        const working = (a.state || 'idle') === 'working'
        return (
          <button
            key={a.agent_id}
            className={`ff-agent ${working ? 'working' : ''}`}
            style={{
              left: `${(a.desk.x / WORLD.width) * 100}%`,
              top: `${(a.desk.y / WORLD.height) * 100}%`,
              '--suit': suit,
            }}
            onClick={() => onSelect(a)}
            title={`${a.name} — ${a.role}`}
          >
            <span className="ff-head" />
            <span className="ff-body" />
            <span className="ff-name">{a.name.replace(' Agent', '')}</span>
            <span className={`ff-pill ${working ? 'busy' : 'idle'}`}>{a.state || 'idle'}</span>
          </button>
        )
      })}
    </div>
  )
}

// Split-view bounds: the floor stays readable and the composer stays usable.
const FLOOR_MIN_W = 300
const CHAT_MIN_W = 340

function loadFloorWidth() {
  try {
    const v = parseFloat(localStorage.getItem('cb_floor_width'))
    return Number.isFinite(v) && v >= FLOOR_MIN_W ? v : null
  } catch {
    return null
  }
}

export default function App() {
  // Floor on the left, chat on the right, separated by a draggable handle —
  // watch the desks react while you type, with the split sized to taste.
  const [floorOpen, setFloorOpen] = useState(true)
  const [floorWidth, setFloorWidth] = useState(loadFloorWidth) // null = default share
  const benchRef = useRef(null)
  const dockRef = useRef(null)

  const startResize = (e) => {
    e.preventDefault()
    const bench = benchRef.current?.getBoundingClientRect()
    if (!bench || !dockRef.current) return
    const startX = e.clientX
    const startW = dockRef.current.getBoundingClientRect().width
    const maxW = bench.width - CHAT_MIN_W - 12
    let lastW = startW
    const onMove = (ev) => {
      lastW = Math.min(Math.max(startW + (ev.clientX - startX), FLOOR_MIN_W), maxW)
      setFloorWidth(lastW)
    }
    const onUp = () => {
      window.removeEventListener('pointermove', onMove)
      window.removeEventListener('pointerup', onUp)
      window.removeEventListener('pointercancel', onUp)
      document.body.classList.remove('split-resizing')
      try {
        localStorage.setItem('cb_floor_width', String(Math.round(lastW)))
      } catch {
        /* private mode etc. */
      }
    }
    document.body.classList.add('split-resizing')
    window.addEventListener('pointermove', onMove)
    window.addEventListener('pointerup', onUp)
    window.addEventListener('pointercancel', onUp)
  }

  const resetResize = () => {
    setFloorWidth(null)
    try {
      localStorage.removeItem('cb_floor_width')
    } catch {
      /* ignore */
    }
  }

  // keyboard-resize: arrow keys nudge the split (also easier to automate-test)
  const nudgeResize = (e) => {
    const step = e.shiftKey ? 64 : 24
    const bench = benchRef.current?.getBoundingClientRect()
    if (!bench || !dockRef.current) return
    if (e.key !== 'ArrowLeft' && e.key !== 'ArrowRight') return
    e.preventDefault()
    const current = dockRef.current.getBoundingClientRect().width
    const maxW = bench.width - CHAT_MIN_W - 12
    const next =
      e.key === 'ArrowLeft'
        ? Math.max(FLOOR_MIN_W, current - step)
        : Math.min(maxW, current + step)
    setFloorWidth(next)
    try {
      localStorage.setItem('cb_floor_width', String(Math.round(next)))
    } catch {
      /* ignore */
    }
  }

  return (
    <div className="shell">
      <header className="topbar">
        <div className="brand">
          <span className="brand-dot" />
          <span>Company Brain</span>
        </div>
        <button
          className={`floor-btn ${floorOpen ? 'is-active' : ''}`}
          onClick={() => setFloorOpen((v) => !v)}
          title="Show / hide the live office floor"
        >
          ▤ Office Floor
        </button>
      </header>

      <div className={`workbench ${floorOpen ? '' : 'floor-hidden'}`} ref={benchRef}>
        {floorOpen && (
          <>
            <div
              className="floor-dock"
              ref={dockRef}
              style={floorWidth ? { width: `${floorWidth}px` } : undefined}
            >
              <FloorView />
            </div>
            <div
              className="split-resizer"
              role="separator"
              tabIndex={0}
              aria-orientation="vertical"
              aria-label="Resize floor and chat panels"
              onPointerDown={startResize}
              onKeyDown={nudgeResize}
              onDoubleClick={resetResize}
              title="Drag to resize — double-click to reset — ←/→ nudge"
            />
          </>
        )}
        {/* Local chat with the Top Agent team — AgentOS ships no bundled UI,
            so the wrapper provides its own instead of iframing "/" */}
        <ChatPanel />
      </div>
    </div>
  )
}

// ---- chat --------------------------------------------------------------

function loadSessionId() {
  let sid = null
  try {
    sid = localStorage.getItem('cb_session_id')
  } catch {
    /* private mode etc. */
  }
  if (!sid) {
    sid = 'web-' + Math.random().toString(36).slice(2, 10)
    try {
      localStorage.setItem('cb_session_id', sid)
    } catch {
      /* ignore */
    }
  }
  return sid
}

function ChatPanel() {
  const [messages, setMessages] = useState(() => [
    {
      role: 'brain',
      text: 'Chief of Staff online. Sales, clients, pricing, ideas, briefings — what do you need?',
    },
  ])
  const [input, setInput] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState(null)
  const sessionRef = useRef(loadSessionId())
  const scrollRef = useRef(null)

  useEffect(() => {
    const el = scrollRef.current
    if (el) el.scrollTop = el.scrollHeight
  }, [messages, busy])

  async function send() {
    const text = input.trim()
    if (!text || busy) return
    setInput('')
    setError(null)
    setMessages((m) => [...m, { role: 'user', text }])
    setBusy(true)
    try {
      // AgentOS teams API: multipart form, stream=false -> single JSON output
      const body = new FormData()
      body.append('message', text)
      body.append('stream', 'false')
      body.append('session_id', sessionRef.current)
      const res = await fetch(`/teams/${TEAM_ID}/runs`, { method: 'POST', body })
      if (!res.ok) throw new Error(`HTTP ${res.status} ${res.statusText}`)
      const data = await res.json()
      const reply =
        (typeof data?.content === 'string' && data.content) ||
        '(no content returned)'
      setMessages((m) => [...m, { role: 'brain', text: reply }])
    } catch (e) {
      setError(e?.message ? String(e.message) : String(e))
    } finally {
      setBusy(false)
    }
  }

  return (
    <main className="chat-panel">
      <div className="chat-scroll" ref={scrollRef}>
        {messages.map((m, i) => (
          <div key={i} className={`msg ${m.role}`}>
            {m.text}
          </div>
        ))}
        {busy && <div className="msg brain typing">thinking…</div>}
      </div>
      {error && <div className="chat-error">⚠ {error}</div>}
      <footer className="composer">
        <textarea
          value={input}
          rows={2}
          placeholder="Talk to your Chief of Staff…  (Enter to send)"
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === 'Enter' && !e.shiftKey) {
              e.preventDefault()
              send()
            }
          }}
        />
        <button
          className="send-btn"
          onClick={send}
          disabled={busy || !input.trim()}
        >
          Send
        </button>
      </footer>
    </main>
  )
}

// ---- office floor panel (docked beside the chat) ----------------------

function FloorView() {
  const { connected, snapshot, lastEvent } = useAgentStatus()
  const canvasRef = useRef(null)
  const sceneRef = useRef(null)
  const [selected, setSelected] = useState(null)
  const [activity, setActivity] = useState(null)
  const [showSettings, setShowSettings] = useState(false)
  const [settings, setSettings] = useState(null)
  const [pixiReady, setPixiReady] = useState(false)

  // mount pixi once the canvas is in the DOM and visible
  useEffect(() => {
    let disposed = false
    const tryInit = () => {
      if (disposed || !canvasRef.current) return
      const scene = new FloorScene(canvasRef.current, {
        onSelect: (meta) => {
          setSelected(meta)
          setActivity(null)
          fetch(`/api/agent-activity/${meta.agent_id}`)
            .then((r) => (r.ok ? r.json() : null))
            .then((d) => d && setActivity(d))
            .catch(() => {})
        },
      })
      sceneRef.current = scene
      scene
        .init()
        .then(() => {
          if (!disposed) {
            setPixiReady(true)
            if (snapshot) scene.applySnapshot(snapshot)
          }
        })
        .catch((e) => {
          console.error('pixi init failed, keeping DOM floor', e)
          if (!disposed) setPixiReady(false)
        })
    }
    // defer one frame so layout/visibility is settled (fixes blank overlay)
    const t = setTimeout(tryInit, 60)
    return () => {
      disposed = true
      clearTimeout(t)
      try {
        sceneRef.current?.destroy()
      } catch {}
      sceneRef.current = null
    }
  }, [])

  // open settings lazily
  useEffect(() => {
    if (showSettings && !settings) {
      fetch('/api/settings-status')
        .then((r) => r.json())
        .then(setSettings)
        .catch(() => setSettings({ error: 'unavailable' }))
    }
  }, [showSettings, settings])

  // push snapshot into the scene whenever it changes
  useEffect(() => {
    if (sceneRef.current && snapshot) sceneRef.current.applySnapshot(snapshot)
  }, [snapshot])

  // feed raw state events to the scene — this is what makes actors walk to
  // the conference table and envelopes fly on handoffs
  useEffect(() => {
    if (sceneRef.current && lastEvent) sceneRef.current.onStateEvent(lastEvent)
  }, [lastEvent])

  const entries = useMemo(
    () => [...(snapshot?.agents || DEFAULT_AGENTS), ...(snapshot?.clients || [])],
    [snapshot],
  )

  const openAgent = (a) => {
    setSelected(a)
    setActivity(null)
    fetch(`/api/agent-activity/${a.agent_id}`)
      .then((r) => (r.ok ? r.json() : null))
      .then((d) => d && setActivity(d))
      .catch(() => {})
  }

  return (
    <section className="floor-panel pixel-panel">
      <header className="panel-head">
        <h2>
          <span className={connected ? 'live-dot on' : 'live-dot'} />
          Company Brain HQ — live floor
        </h2>
        <button
          className="close-btn"
          style={{ marginLeft: 'auto' }}
          title="Settings & status"
          onClick={() => { setShowSettings((v) => !v); setSelected(null) }}
        >
          ⚙️
        </button>
      </header>

        <div className="canvas-wrap">
          {/* DOM floor is the reliable render — always visible */}
          <FloorFallback entries={entries} onSelect={openAgent} />
          {/* Pixi canvas layers on top once it initializes. It must be
              mounted from the start: init needs the element, and the
              element only existing after init is a chicken-and-egg that
              left the floor static (render: dom, no walking). */}
          <canvas
            ref={canvasRef}
            width={WORLD.width}
            height={WORLD.height}
            style={{
              position: 'absolute',
              inset: 0,
              zIndex: 2,
              visibility: pixiReady ? 'visible' : 'hidden',
              pointerEvents: pixiReady ? 'auto' : 'none',
            }}
          />
          {!snapshot && <div className="loading">connecting to the office…</div>}
          <div className="floor-debug">
            render: {pixiReady ? 'pixi+dom' : 'dom'} · agents: {entries.length}
          </div>
        </div>

        <aside className="roster">
          {entries.map((a) => (
            <div
              key={a.agent_id}
              className={`chip ${a.temporary ? 'temp' : ''}`}
              style={{ cursor: 'pointer' }}
              onClick={() => {
                setSelected(a)
                setActivity(null)
                fetch(`/api/agent-activity/${a.agent_id}`)
                  .then((r) => (r.ok ? r.json() : null))
                  .then((d) => d && setActivity(d))
                  .catch(() => {})
              }}
            >
              <span className="chip-avatar" style={{ background: a.accent }} />
              <span className="chip-name">{a.name}</span>
              <span className="chip-state" style={{ color: stateColor(a.state || 'idle') }}>
                ● {a.state || 'idle'}
              </span>
              {a.task_summary ? (
                <span className="chip-task" title={a.task_summary}>
                  {a.task_summary}
                </span>
              ) : null}
            </div>
          ))}
        </aside>

        {showSettings && (
          <aside className="detail-panel">
            <h3>⚙️ Settings & status</h3>
            {!settings ? (
              <p className="muted">loading…</p>
            ) : settings.error ? (
              <p className="muted">{settings.error}</p>
            ) : (
              <>
                <ul className="kv-list">
                  {Object.entries(settings.keys).map(([k, v]) => (
                    <li key={k}>
                      <span className={`pill ${v.set ? 'ok' : 'missing'}`}>{v.set ? '✅ set' : '❌ not set'}</span>
                      <span className="kv-label">{v.label}</span>
                    </li>
                  ))}
                  <li>
                    <span className="pill ok">🗄️</span>
                    <span className="kv-label">Database: {settings.database}</span>
                  </li>
                  {settings.missing_required && (
                    <li className="warn-note">⚠️ GOOGLE_API_KEY missing — add it to .env and restart Docker</li>
                  )}
                </ul>
                <h4>Agent → model map</h4>
                <ul className="kv-list small">
                  {settings.agents.map((a) => (
                    <li key={a.agent_id}>
                      <span className="kv-label">{a.name}</span>
                      <span className="mono">{a.model}</span>
                    </li>
                  ))}
                </ul>
              </>
            )}
          </aside>
        )}

        {selected && !showSettings && (
          <aside className="detail-panel">
            <h3>
              <span className="chip-avatar" style={{ background: selected.accent }} />{' '}
              {selected.name}
            </h3>
            <p className="muted">{selected.role}</p>
            <p>
              State: <b>{activity?.live?.state || selected.state || 'idle'}</b>
              {' · '}Model: <b>{activity?.model || '…'}</b>
            </p>
            {(activity?.live?.task_summary || selected.task_summary) && (
              <p className="task-now">
                📌 Now: {activity?.live?.task_summary || selected.task_summary}
              </p>
            )}
            <h4>Recent activity</h4>
            {!activity ? (
              <p className="muted">loading…</p>
            ) : activity.history.length === 0 ? (
              <p className="muted">no recorded activity yet</p>
            ) : (
              <ul className="history-list">
                {activity.history.map((h, i) => (
                  <li key={i}>
                    <span className="hist-time">
                      {(h.timestamp || '').slice(0, 16).replace('T', ' ')}
                    </span>
                    <span>{h.action}</span>
                  </li>
                ))}
              </ul>
            )}
          </aside>
        )}

        <footer className="legend">
          <LegendDot color={COLORS.statusIdle} label="idle" />
          <LegendDot color={COLORS.statusWorking} label="working" />
          <LegendDot color={COLORS.statusHandoff} label="handoff" />
          <span className="legend-note">client desks appear while Client Agents are active</span>
        </footer>
    </section>
  )
}

function LegendDot({ color, label }) {
  return (
    <span className="legend-item">
      <span className="dot" style={{ background: color }} /> {label}
    </span>
  )
}
