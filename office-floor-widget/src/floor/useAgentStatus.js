// Live agent status: REST snapshot on load, then WebSocket events.
// Reconnects with backoff. No mock data — everything comes from the backend.

import { useEffect, useRef, useState } from 'react'

const initial = {
  connected: false,
  snapshot: null, // {agents:[...], clients:[...], floor:{...}}
  lastError: null,
}

export function useAgentStatus() {
  const [state, setState] = useState(initial)
  const wsRef = useRef(null)
  const retryRef = useRef(0)
  const timerRef = useRef(null)

  useEffect(() => {
    let disposed = false

    const connect = () => {
      if (disposed) return
      const proto = location.protocol === 'https:' ? 'wss' : 'ws'
      const ws = new WebSocket(`${proto}://${location.host}/ws/agent-status`)
      wsRef.current = ws

      ws.onopen = () => {
        retryRef.current = 0
        setState((s) => ({ ...s, connected: true, lastError: null }))
      }

      ws.onmessage = (msg) => {
        try {
          const data = JSON.parse(msg.data)
          if (data.kind === 'snapshot') {
            setState((s) => ({ ...s, snapshot: data }))
          } else if (data.kind === 'roster') {
            setState((s) => ({ ...s, snapshot: applyRoster(s.snapshot, data) }))
          } else if (data.kind === 'state') {
            setState((s) => ({
              ...s,
              snapshot: applyState(s.snapshot, data),
              lastEvent: { ...data },
            }))
          }
        } catch {
          /* ignore malformed frames */
        }
      }

      ws.onclose = () => {
        if (disposed) return
        setState((s) => ({ ...s, connected: false }))
        // fetch a fresh snapshot over REST while the socket is down
        fetch('/api/agent-status/snapshot')
          .then((r) => (r.ok ? r.json() : null))
          .then((snap) => {
            if (snap && !disposed) setState((s) => ({ ...s, snapshot: snap }))
          })
          .catch(() => {})
        const delay = Math.min(8000, 500 * 2 ** retryRef.current++)
        timerRef.current = setTimeout(connect, delay)
      }

      ws.onerror = () => ws.close()
    }

    // initial REST snapshot so the floor renders even before WS opens
    fetch('/api/agent-status/snapshot')
      .then((r) => (r.ok ? r.json() : null))
      .then((snap) => {
        if (snap && !disposed) setState((s) => ({ ...s, snapshot: snap }))
      })
      .catch(() => {})

    connect()
    return () => {
      disposed = true
      clearTimeout(timerRef.current)
      if (wsRef.current) wsRef.current.close()
    }
  }, [])

  return state
}

function applyState(snapshot, ev) {
  if (!snapshot) return snapshot
  const patchList = (list) =>
    (list || []).map((a) =>
      a.agent_id === ev.agent_id
        ? { ...a, state: ev.state, task_summary: ev.task_summary ?? '', timestamp: ev.timestamp }
        : a,
    )
  return { ...snapshot, agents: patchList(snapshot.agents), clients: patchList(snapshot.clients) }
}

function applyRoster(snapshot, ev) {
  if (!snapshot) return snapshot
  if (ev.action === 'add') {
    if ((snapshot.clients || []).some((c) => c.agent_id === ev.agent.agent_id)) return snapshot
    return { ...snapshot, clients: [...(snapshot.clients || []), { ...ev.agent }] }
  }
  return {
    ...snapshot,
    clients: (snapshot.clients || []).filter((c) => c.agent_id !== ev.agent.agent_id),
  }
}
