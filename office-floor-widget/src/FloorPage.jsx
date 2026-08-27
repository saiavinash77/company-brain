// Standalone Office Floor — rendered as pure DOM/SVG (no WebGL/Pixi).
// Bulletproof: can never go blank. Top Agent sits dead-center; specialists
// arc around him. Live state lights up desks; the current task shows above
// the Chief. Driven by /ws/agent-status + /api/agent-status/snapshot.

import { useEffect, useMemo, useRef, useState } from 'react'
import { useAgentStatus } from './floor/useAgentStatus.js'
import { WORLD } from './floor/tokens.js'

const CENTER = { x: 480, y: 280 }

function AgentAvatar({ meta, selected, onClick }) {
  const state = meta.state || 'idle'
  const working = state === 'working'
  return (
    <button
      className={`agent-avatar ${working ? 'working' : ''} ${selected ? 'sel' : ''}`}
      style={{
        left: `${(meta.desk.x / WORLD.width) * 100}%`,
        top: `${(meta.desk.y / WORLD.height) * 100}%`,
        '--accent': meta.accent || '#4ECDC4',
      }}
      onClick={() => onClick(meta)}
      title={`${meta.name} — ${meta.role}`}
    >
      <span className="avatar-body" />
      <span className="avatar-label">{meta.name.replace(' Agent', '')}</span>
      <span className={`avatar-pill ${working ? 'busy' : 'idle'}`}>{state}</span>
    </button>
  )
}

export default function FloorPage() {
  const { connected, snapshot, lastEvent } = useAgentStatus()
  const [selected, setSelected] = useState(null)
  const [activity, setActivity] = useState(null)
  const [showSettings, setShowSettings] = useState(false)
  const [settings, setSettings] = useState(null)

  const entries = useMemo(
    () => [...(snapshot?.agents || []), ...(snapshot?.clients || [])],
    [snapshot],
  )

  const top = entries.find((a) => a.agent_id === 'top_agent')
  const taskText = lastEvent?.task_summary || top?.task_summary || null

  const loadActivity = (meta) => {
    setSelected(meta)
    setActivity(null)
    fetch(`/api/agent-activity/${meta.agent_id}`)
      .then((r) => (r.ok ? r.json() : null))
      .then((d) => d && setActivity(d))
      .catch(() => {})
  }

  // lazy settings
  useEffect(() => {
    if (showSettings && !settings) {
      fetch('/api/settings-status')
        .then((r) => r.json())
        .then(setSettings)
        .catch(() => setSettings({ error: 'unavailable' }))
    }
  }, [showSettings, settings])

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

      <div className="floor-stage floor-stage-dom">
        {/* task banner above the Chief */}
        {taskText && (
          <div className="task-banner">
            📌 Chief working on: <b>{taskText}</b>
          </div>
        )}

        <div className="floor-room" style={{ aspectRatio: `${WORLD.width} / ${WORLD.height}` }}>
          {/* conference table */}
          <div
            className="conf-table"
            style={{
              left: `${(480 / WORLD.width) * 100}%`,
              top: `${(380 / WORLD.height) * 100}%`,
            }}
          />
          {entries.map((a) => (
            <AgentAvatar
              key={a.agent_id}
              meta={a}
              selected={selected?.agent_id === a.agent_id}
              onClick={loadActivity}
            />
          ))}
        </div>

        <aside className="roster">
          {entries.map((a) => (
            <div
              key={a.agent_id}
              className={`chip ${a.temporary ? 'temp' : ''} ${selected?.agent_id === a.agent_id ? 'sel' : ''}`}
              style={{ cursor: 'pointer' }}
              onClick={() => loadActivity(a)}
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

      <button
        className="fab"
        title="Settings & status"
        onClick={() => { setShowSettings((v) => !v); setSelected(null) }}
      >
        ⚙️
      </button>
    </div>
  )
}
