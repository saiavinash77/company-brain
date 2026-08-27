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
  const [selected, setSelected] = useState(null)       // agent meta from click
  const [activity, setActivity] = useState(null)       // /api/agent-activity payload
  const [showSettings, setShowSettings] = useState(false)
  const [settings, setSettings] = useState(null)

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
          if (!disposed && snapshot) scene.applySnapshot(snapshot)
        })
        .catch((e) => console.error('pixi init failed', e))
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
          <div style={{ marginLeft: 'auto', display: 'flex', gap: 8 }}>
            <button
              className="close-btn"
              title="Settings & status"
              onClick={() => { setShowSettings((v) => !v); setSelected(null) }}
            >
              ⚙️
            </button>
            <button className="close-btn" onClick={onClose} title="Close">
              ✕
            </button>
          </div>
        </header>

        <div className="canvas-wrap">
          <canvas ref={canvasRef} width={WORLD.width} height={WORLD.height} />
          {!snapshot && <div className="loading">connecting to the office…</div>}
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
