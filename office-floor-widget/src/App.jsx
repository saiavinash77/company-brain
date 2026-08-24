import { useEffect, useMemo, useRef, useState } from 'react'
import { FloorScene } from './floor/FloorScene.js'
import { useAgentStatus } from './floor/useAgentStatus.js'
import { COLORS, WORLD, stateColor } from './floor/tokens.js'

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

      {/* The real AgentOS UI, exactly as today */}
      <iframe className="agentos-frame" src="/" title="AgentOS" />

      {floorOpen && <FloorOverlay onClose={() => setFloorOpen(false)} />}
    </div>
  )
}

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

  // feed live state events straight into the scene (bypasses React re-render
  // for animation smoothness — we subscribe again at the socket layer? No:
  // useAgentStatus already mirrors events into the snapshot, which flows here.
  // Handoff envelopes are driven from the mirrored state diff below.)

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
