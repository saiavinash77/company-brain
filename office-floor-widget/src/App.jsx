import { useEffect, useMemo, useRef, useState } from 'react'
import { FloorScene } from './floor/FloorScene.js'
import { useAgentStatus } from './floor/useAgentStatus.js'
import { COLORS, WORLD, stateColor } from './floor/tokens.js'

const TEAM_ID = 'company-brain'

export default function App() {
  const [floorOpen, setFloorOpen] = useState(false)

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
          title="Live agent office floor"
        >
          ▤ Office Floor
        </button>
      </header>

      {/* Local chat with the Top Agent team — AgentOS ships no bundled UI,
          so the wrapper provides its own instead of iframing "/" */}
      <ChatPanel />

      {floorOpen && <FloorOverlay onClose={() => setFloorOpen(false)} />}
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

// ---- office floor overlay ----------------------------------------------

function FloorOverlay({ onClose }) {
  const { connected, snapshot } = useAgentStatus()
  const canvasRef = useRef(null)
  const sceneRef = useRef(null)

  // mount pixi once
  useEffect(() => {
    let disposed = false
    const scene = new FloorScene(canvasRef.current)
    sceneRef.current = scene
    scene.init().catch((e) => console.error('pixi init failed', e))
    return () => {
      disposed = true
      try {
        scene.destroy()
      } catch {}
      sceneRef.current = null
    }
  }, [])

  // push snapshot into the scene whenever it changes
  useEffect(() => {
    if (sceneRef.current && snapshot) sceneRef.current.applySnapshot(snapshot)
  }, [snapshot])

  const entries = useMemo(
    () => [...(snapshot?.agents || []), ...(snapshot?.clients || [])],
    [snapshot],
  )

  return (
    <div className="overlay-backdrop" onClick={onClose}>
      <section className="floor-panel pixel-panel" onClick={(e) => e.stopPropagation()}>
        <header className="panel-head">
          <h2>
            <span className={connected ? 'live-dot on' : 'live-dot'} />
            Company Brain HQ — live floor
          </h2>
          <button className="close-btn" onClick={onClose} title="Close">
            ✕
          </button>
        </header>

        <div className="canvas-wrap">
          <canvas ref={canvasRef} width={WORLD.width} height={WORLD.height} />
          {!snapshot && <div className="loading">connecting to the office…</div>}
        </div>

        <aside className="roster">
          {entries.map((a) => (
            <div key={a.agent_id} className={`chip ${a.temporary ? 'temp' : ''}`}>
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

        <footer className="legend">
          <LegendDot color={COLORS.statusIdle} label="idle" />
          <LegendDot color={COLORS.statusWorking} label="working" />
          <LegendDot color={COLORS.statusHandoff} label="handoff" />
          <span className="legend-note">client desks appear while Client Agents are active</span>
        </footer>
      </section>
    </div>
  )
}

function LegendDot({ color, label }) {
  return (
    <span className="legend-item">
      <span className="dot" style={{ background: color }} /> {label}
    </span>
  )
}
