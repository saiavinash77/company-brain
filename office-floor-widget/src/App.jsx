import { useEffect, useMemo, useRef, useState } from 'react'
import { useAgentStatus } from './floor/useAgentStatus.js'
import { COLORS, WORLD, stateColor } from './floor/tokens.js'

const TEAM_ID = 'company-brain'

export default function App() {
  return (
    <div className="shell">
      <header className="topbar">
        <div className="brand">
          <span className="brand-dot" />
          <span>Company Brain</span>
        </div>
        <a className="floor-btn" href="/floor" title="Live agent office floor">
          ▤ Office Floor
        </a>
      </header>

      <ChatPanel />
    </div>
  )
}

// ---- chat --------------------------------------------------------------

function loadSessionId() {
  let sid = null
  try {
    sid = localStorage.getItem('cb_session')
  } catch {}
  if (!sid) {
    sid = 'web-' + Math.random().toString(36).slice(2, 10)
    try {
      localStorage.setItem('cb_session', sid)
    } catch {}
  }
  return sid
}

function ChatPanel() {
  const [input, setInput] = useState('')
  const [messages, setMessages] = useState([])
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState(null)
  const [sessionId] = useState(loadSessionId)
  const [streaming, setStreaming] = useState('')
  const scrollRef = useRef(null)

  useEffect(() => {
    if (scrollRef.current) scrollRef.current.scrollTop = scrollRef.current.scrollHeight
  }, [messages, streaming])

  async function send() {
    const text = input.trim()
    if (!text || busy) return
    setInput('')
    setError(null)
    setMessages((m) => [...m, { role: 'user', text }])
    setBusy(true)
    setStreaming('')

    try {
      const resp = await fetch(`/api/chat`, {
        method: 'POST',
        headers: { Accept: 'text/event-stream' },
        body: (() => {
          const fd = new FormData()
          fd.append('message', text)
          fd.append('session_id', sessionId)
          fd.append('user_id', sessionId)
          return fd
        })(),
      })
      if (!resp.ok || !resp.body) {
        const detail = await resp.text().catch(() => '')
        throw new Error(`API ${resp.status}: ${detail.slice(0, 200)}`)
      }
      const reader = resp.body.getReader()
      const decoder = new TextDecoder()
      let buf = ''
      let full = ''
      while (true) {
        const { value, done } = await reader.read()
        if (done) break
        buf += decoder.decode(value, { stream: true })
        const lines = buf.split('\n')
        buf = lines.pop() || ''
        for (const line of lines) {
          const trimmed = line.trim()
          if (!trimmed.startsWith('data:')) continue
          const payload = trimmed.slice(5).trim()
          if (!payload || payload === '[DONE]') continue
          try {
            const evt = JSON.parse(payload)
            if ((evt.event === 'TeamRunContent' || evt.type === 'TeamRunResponse') && evt.content) {
              full += evt.content
              setStreaming(full)
            } else if (evt.event === 'RunResponse' && evt.content) {
              full += evt.content
              setStreaming(full)
            } else if (evt.event === 'RunCompleted' || evt.event === 'TeamRunCompleted') {
              // finalize
              setMessages((m) => [...m, { role: 'assistant', text: full || '(no response)' }])
              setStreaming('')
              setBusy(false)
              return
            }
          } catch {
            /* ignore malformed frame */
          }
        }
      }
      if (full) setMessages((m) => [...m, { role: 'assistant', text: full }])
      setStreaming('')
    } catch (e) {
      setError(String(e.message || e))
      setMessages((m) => [...m, { role: 'assistant', text: '⚠️ ' + (e.message || 'request failed') }])
    } finally {
      setBusy(false)
      setStreaming('')
    }
  }

  return (
    <div className="chat">
      <div className="messages" ref={scrollRef}>
        {messages.length === 0 && (
          <div className="empty">
            <p>Talk to your Chief of Staff. It routes to the right specialist.</p>
            <p className="muted">Tip: open ▤ Office Floor to watch agents work live.</p>
          </div>
        )}
        {messages.map((m, i) => (
          <div key={i} className={`row ${m.role}`}>
            <div className="bubble">{m.text}</div>
          </div>
        ))}
        {streaming && (
          <div className="row assistant">
            <div className="bubble streaming">{streaming}▌</div>
          </div>
        )}
        {busy && !streaming && (
          <div className="row assistant">
            <div className="bubble muted">thinking…</div>
          </div>
        )}
      </div>

      {error && <div className="errbar">⚠️ {error}</div>}

      <div className="composer">
        <textarea
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === 'Enter' && !e.shiftKey) {
              e.preventDefault()
              send()
            }
          }}
          placeholder="Talk to your Chief of Staff…  (Enter to send)"
          rows={2}
        />
        <button className="send-btn" onClick={send} disabled={busy || !input.trim()}>
          Send
        </button>
      </div>
    </div>
  )
}
