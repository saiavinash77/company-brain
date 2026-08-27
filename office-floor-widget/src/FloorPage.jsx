// Standalone Office Floor page — separated from the chat UI per request.
// Loaded at /floor via its own HTML entry (floor.html).
// Talks to /ws/agent-status + /api/agent-status/snapshot only. No chat here.

import { useEffect, useMemo, useRef, useState } from 'react'
import { FloorScene } from './floor/FloorScene.js'
import { useAgentStatus } from './floor/useAgentStatus.js'
import { WORLD } from './floor/tokens.js'

export default function FloorPage() {
  const { connected, snapshot } = useAgentStatus()
  const canvasRef = useRef(null)
  const sceneRef = useRef(null)
  const [selected, setSelected] = useState(null)
  const [activity, setActivity] = useState(null)
  const [showSettings, setShowSettings] = useState(false)
  const [settings, setSettings] = useState(null)
  const [initError, setInitError] = useState(null)
  const [bootError, setBootError] = useState(null)

  // surface any uncaught error visibly instead of a blank screen
  useEffect(() => {
    const onErr = (e) => setBootError(String(e.message || e.error || e))
    window.addEventListener('error', onErr)
    window.addEventListener('unhandledrejection', (e) =>
      setBootError('Promise: ' + (e.reason?.message || e.reason)),
    )
    return () => window.removeEventListener('error', onErr)
  }, [])

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
          if (snapshot) scene.applySnapshot(snapshot)
        })
        .catch((e) => {
          console.error('pixi init failed', e)
          if (!disposed) setInitError(String(e?.message || e))
        })
    }
    // defer one frame so layout/visibility is settled
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

  // push live snapshots into the scene
  useEffect(() => {
    if (sceneRef.current && snapshot) sceneRef.current.applySnapshot(snapshot)
  }, [snapshot])

  // lazy settings
  useEffect(() => {
    if (showSettings && !settings) {
      fetch('/api/settings-status')
        .then((r) => r.json())
        .then(setSettings)
        .catch(() => setSettings({ error: 'unavailable' }))
    }
  }, [showSettings, settings])

  const entries = useMemo(
    () => [...(snapshot?.agents || []), ...(snapshot?.clients || [])],
    [snapshot],
  )

  return (
    <div className="floor-shell">
      <header className="topbar floor-topbar">
        <div className="brand">
          <span className="brand-dot" />
          <span>Company Brain — HQ</span>
        </div>
        <div style={{ marginLeft: 'auto', display: 'flex', gap: 8, alignItems: 'center' }}>
          <span className={connected ? 'live-dot on' : 'live-dot'} />
          <span className="muted">{connected ? 'live' : 'reconnecting…'}</span>
          <a className="back-btn" href="/">← Back to Chat</a>
        </div>
      </header>

      <div className="floor-stage">
        <div className="canvas-wrap floor-canvas-wrap">
          <canvas ref={canvasRef} width={WORLD.width} height={WORLD.height} />
          {initError && (
            <div className="loading" style={{ color: '#e2574c' }}>
              ⚠️ floor render error: {initError}
            </div>
          )}
          {!snapshot && !initError && <div className="loading">connecting to the office…</div>}
        </div>

        <aside className="roster">
          {entries.map((a) => (
            <div
              key={a.agent_id}
              className={`chip ${a.temporary ? 'temp' : ''} ${selected?.agent_id === a.agent_id ? 'sel' : ''}`}
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
              <span className="chip-avatar" style={{ background: a.accent || '#4ECDC4' }} />
              <span className="chip-name">{a.name.replace(' Agent', '')}</span>
              <span className={`pill ${a.state === 'working' ? 'busy' : 'idle'}`}>
                {a.state || 'idle'}
              </span>
            </div>
          ))}
        </aside>

        {showSettings && (
          <aside className="detail-panel">
            <h3>⚙️ Settings &amp; Status</h3>
            {!settings ? (
              <p className="muted">loading…</p>
            ) : settings.error ? (
              <p className="muted">{settings.error}</p>
            ) : (
              <>
                <ul className="kv-list">
                  {Object.entries(settings.keys || {}).map(([k, v]) => (
                    <li key={k}>
                      <span className={`pill ${v.set ? 'ok' : 'missing'}`}>
                        {v.set ? '✅ set' : '❌ not set'}
                      </span>
                      <span className="kv-label">{v.label}</span>
                    </li>
                  ))}
                  <li>
                    <span className="pill ok">🗄️</span>
                    <span className="kv-label">Database: {settings.database}</span>
                  </li>
                  {settings.missing_required && (
                    <li className="warn-note">
                      ⚠️ GOOGLE_API_KEY missing — add it to .env and restart Docker
                    </li>
                  )}
                </ul>
                <h4>Agent → model map</h4>
                <ul className="kv-list small">
                  {(settings.agents || []).map((a) => (
                    <li key={a.agent_id}>
                      <span className="kv-label">{a.name}</span>
                      <span className="mono">{a.model}</span>
                    </li>
                  ))}
                </ul>
              </>
            )}
            <button className="close-btn" onClick={() => setShowSettings(false)}>✕</button>
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
            ) : (activity.history || []).length === 0 ? (
              <p className="muted">no recorded activity yet</p>
            ) : (
              <ul className="history-list">
                {activity.history.slice(0, 12).map((h, i) => (
                  <li key={i}>
                    <span className="hist-time">{h.time}</span>
                    <span className="hist-text">{h.text}</span>
                  </li>
                ))}
              </ul>
            )}
            <button className="close-btn" onClick={() => setSelected(null)}>✕</button>
          </aside>
        )}
      </div>

      {/* settings toggle, bottom-left */}
      <button
        className="fab"
        title="Settings & status"
        onClick={() => { setShowSettings((v) => !v); setSelected(null) }}
      >
        ⚙️
      </button>

      {bootError && (
        <div className="boot-error">
          🛑 Page error: {bootError}
          <button onClick={() => setBootError(null)}>dismiss</button>
        </div>
      )}
    </div>
  )
}
