// Modern "ChatGPT-style" interface — clean, readable, content-first.
// Separate from the office-floor workbench: that one is the fun visual,
// this one is the clear daily driver for actually reading what the team says.

import { useEffect, useRef, useState } from 'react'
import { useAgentStatus } from './floor/useAgentStatus.js'
import './modern.css'

const TEAM_ID = 'company-brain'

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

function newSession() {
  const sid = 'web-' + Math.random().toString(36).slice(2, 10)
  try {
    localStorage.setItem('cb_session_id', sid)
  } catch {
    /* ignore */
  }
  return sid
}

// ---------------------------------------------------------------------------
// Sessions — conversations persist server-side (Postgres via AgentOS).
// GET /sessions lists them; GET /sessions/:id/runs replays the messages.
// ---------------------------------------------------------------------------

async function fetchSessions() {
  try {
    const res = await fetch('/sessions?limit=30')
    if (!res.ok) return []
    const data = await res.json()
    const list = Array.isArray(data) ? data : data.data || []
    return list
      .filter((s) => s.session_type === 'team')
      .sort((a, b) => new Date(b.updated_at || b.created_at || 0) - new Date(a.updated_at || a.created_at || 0))
  } catch {
    return []
  }
}

async function fetchSessionMessages(sessionId) {
  try {
    const res = await fetch(`/sessions/${encodeURIComponent(sessionId)}/runs?limit=100`)
    if (!res.ok) return null
    const data = await res.json()
    const runs = Array.isArray(data) ? data : data.data || []
    const msgs = []
    for (const r of runs) {
      const q = (r.run_input || '').trim()
      const a = (r.content || '').trim()
      if (q) msgs.push({ role: 'user', text: q })
      if (a) msgs.push({ role: 'brain', text: a })
    }
    return msgs
  } catch {
    return null
  }
}

function timeAgo(iso) {
  if (!iso) return ''
  const s = Math.floor((Date.now() - new Date(iso).getTime()) / 1000)
  if (!Number.isFinite(s) || s < 0) return ''
  if (s < 60) return 'just now'
  if (s < 3600) return `${Math.floor(s / 60)}m ago`
  if (s < 86400) return `${Math.floor(s / 3600)}h ago`
  if (s < 86400 * 7) return `${Math.floor(s / 86400)}d ago`
  return new Date(iso).toLocaleDateString()
}

// ---------------------------------------------------------------------------
// Attachments — files are read IN THE BROWSER and their text is sent inside
// the message. (The runs API's files[] field only reaches the model as
// image_url/document parts, and Groq rejects document parts — so extracting
// text client-side is the one path that works for every text-bearing file.)
// PDFs are parsed with pdfjs; a page cap keeps giant files bounded.
// ---------------------------------------------------------------------------

const PDF_PAGE_CAP = 40
const TEXT_CHAR_CAP = 60000

const TEXT_EXT = [
  '.txt', '.md', '.markdown', '.csv', '.tsv', '.json', '.yml', '.yaml',
  '.xml', '.html', '.htm', '.log', '.ini', '.cfg', '.py', '.js', '.jsx',
  '.ts', '.tsx', '.css', '.sql', '.sh', '.bat', '.java', '.c', '.cpp',
  '.h', '.go', '.rs', '.rb', '.php',
]

function isTextFile(name, type) {
  if (typeof type === 'string' && type.startsWith('text/')) return true
  const lower = name.toLowerCase()
  return TEXT_EXT.some((ext) => lower.endsWith(ext))
}

async function extractFileText(file) {
  const name = file.name || 'file'
  if (name.toLowerCase().endsWith('.pdf') || file.type === 'application/pdf') {
    const pdfjs = await import('pdfjs-dist')
    pdfjs.GlobalWorkerOptions.workerSrc = new URL(
      'pdfjs-dist/build/pdf.worker.min.mjs',
      import.meta.url,
    ).toString()
    const data = new Uint8Array(await file.arrayBuffer())
    const pdf = await pdfjs.getDocument({ data }).promise
    const pages = Math.min(pdf.numPages, PDF_PAGE_CAP)
    let text = ''
    for (let p = 1; p <= pages; p++) {
      const page = await pdf.getPage(p)
      const content = await page.getTextContent()
      text += content.items.map((i) => i.str).join(' ') + '\n\n'
    }
    const more = pdf.numPages > PDF_PAGE_CAP ? ` (only first ${PDF_PAGE_CAP} of ${pdf.numPages} pages read)` : ''
    return { name, text: text.slice(0, TEXT_CHAR_CAP).trim(), note: `PDF, ${pdf.numPages} pages${more}` }
  }
  if (isTextFile(name, file.type)) {
    const raw = await file.text()
    return { name, text: raw.slice(0, TEXT_CHAR_CAP), note: 'text' }
  }
  // Binary we can't read: still tell the team the file exists
  return {
    name,
    text: '',
    note: `${file.type || 'unknown type'}, ${(file.size / 1024).toFixed(0)} KB — contents could not be read in the browser`,
  }
}

// Pretty sizes for the chips
function fmtSize(bytes) {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(0)} KB`
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`
}



// ---------------------------------------------------------------------------
// Tiny markdown renderer — the team replies in markdown (headers, bold,
// lists, code). Escapes HTML first, then applies a fixed set of transforms.
// No dependency: keeps the bundle small and the output predictable.
// ---------------------------------------------------------------------------

function escapeHtml(s) {
  return s
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
}

function renderMarkdown(md) {
  let html = escapeHtml(String(md || ''))

  // fenced code blocks first (protect their contents from other rules)
  const codeBlocks = []
  html = html.replace(/```(\w*)\n([\s\S]*?)```/g, (_m, _lang, code) => {
    codeBlocks.push(`<pre class="mc-code"><code>${code}</code></pre>`)
    return `\u0000CODE${codeBlocks.length - 1}\u0000`
  })

  html = html.replace(/`([^`\n]+)`/g, '<code class="mc-inline">$1</code>')
  html = html.replace(/^#### (.*)$/gm, '<h4>$1</h4>')
  html = html.replace(/^### (.*)$/gm, '<h3>$1</h3>')
  html = html.replace(/^## (.*)$/gm, '<h2>$1</h2>')
  html = html.replace(/^# (.*)$/gm, '<h2>$1</h2>')
  html = html.replace(/^&gt; (.*)$/gm, '<blockquote>$1</blockquote>')
  html = html.replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>')
  html = html.replace(/(^|[^*])\*([^*\n]+)\*/g, '$1<em>$2</em>')
  html = html.replace(/\[([^\]]+)\]\(([^)\s]+)\)/g, '<a href="$2" target="_blank" rel="noreferrer">$1</a>')

  // horizontal rules
  html = html.replace(/^---+$/gm, '<hr/>')

  // pipe tables (agents answer with them a lot — must stay readable here)
  html = html.replace(/(^|\n)((?:\|[^\n]*\n?)+)/g, (m, pre, block) => {
    const isSep = (r) => /^[\s|:\-]+$/.test(r) && r.includes('-')
    const cells = (r) =>
      r
        .replace(/^\|/, '')
        .replace(/\|$/, '')
        .split('|')
        .map((c) => c.trim())
    const rows = block
      .trim()
      .split('\n')
      .map((r) => r.trim())
      .filter(Boolean)
      .filter((r) => !isSep(r))
    if (rows.length === 0) return m
    const [head, ...body] = rows
    const thead = `<tr>${cells(head)
      .map((c) => `<th>${c}</th>`)
      .join('')}</tr>`
    const tbody = body
      .map((r) => `<tr>${cells(r).map((c) => `<td>${c}</td>`).join('')}</tr>`)
      .join('')
    return `${pre}<table class="mc-table"><thead>${thead}</thead><tbody>${tbody}</tbody></table>`
  })

  // unordered lists (consecutive "- " / "* " lines)
  html = html.replace(/(^|\n)((?:[-*] [^\n]*(?:\n|$))+)/g, (_m, pre, block) => {
    const items = block
      .trim()
      .split('\n')
      .map((l) => `<li>${l.replace(/^[-*] /, '')}</li>`)
      .join('')
    return `${pre}<ul>${items}</ul>`
  })
  // ordered lists
  html = html.replace(/(^|\n)((?:\d+\. [^\n]*(?:\n|$))+)/g, (_m, pre, block) => {
    const items = block
      .trim()
      .split('\n')
      .map((l) => `<li>${l.replace(/^\d+\. /, '')}</li>`)
      .join('')
    return `${pre}<ol>${items}</ol>`
  })

  // paragraphs
  html = html
    .split(/\n{2,}/)
    .map((part) => {
      const t = part.trim()
      if (!t) return ''
      if (/^<(h\d|ul|ol|pre|blockquote|hr|table)/.test(t)) return t
      if (/^\u0000CODE/.test(t)) return t
      return `<p>${t.replace(/\n/g, '<br/>')}</p>`
    })
    .filter(Boolean)
    .join('')

  // restore code blocks
  html = html.replace(/\u0000CODE(\d+)\u0000/g, (_m, i) => codeBlocks[Number(i)])
  return html
}

// ---------------------------------------------------------------------------
// Small pieces
// ---------------------------------------------------------------------------

function BrainMark({ size = 28 }) {
  // simple spark mark — brand accent without emoji clutter
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" className="mc-mark" aria-hidden="true">
      <path
        d="M12 2c.5 3-1.7 4.2-3 5.5C7 9.3 6 11 6 13.5 6 17.7 8.7 20 12 20s6-2.3 6-6.5c0-2.5-1-4.2-3-6-1.3-1.3-3.5-2.5-3-5.5Z"
        fill="#F4D35E"
        stroke="#6E1423"
        strokeWidth="1.4"
      />
      <path d="M12 8v9M9.5 11.5h5M9.5 14.5h5" stroke="#6E1423" strokeWidth="1.2" strokeLinecap="round" />
    </svg>
  )
}

function AgentDot({ state }) {
  const cls = state === 'working' ? 'busy' : state === 'handoff' ? 'hand' : 'idle'
  return <span className={`mc-dot ${cls}`} />
}

function CopyButton({ text }) {
  const [done, setDone] = useState(false)
  return (
    <button
      className="mc-copy"
      title="Copy reply"
      onClick={() => {
        navigator.clipboard?.writeText(text).then(
          () => {
            setDone(true)
            setTimeout(() => setDone(false), 1500)
          },
          () => {},
        )
      }}
    >
      {done ? '✓ copied' : 'copy'}
    </button>
  )
}

const SUGGESTIONS = [
  { icon: '◎', title: 'Qualify a lead', text: 'Qualify this lead and score it HOT/WARM/COLD: Acme Corp, 200-person logistics company, $5k/month budget, wants to start next month.' },
  { icon: '⇗', title: 'Draft a pricing brief', text: 'Draft a one-page pricing brief for a mid-market logistics client with a $5k/month budget.' },
  { icon: '⊬', title: 'Scan the market', text: 'Give me a quick scan of the logistics software market: top competitors and where we could differentiate.' },
  { icon: '✎', title: 'Write a follow-up', text: 'Write a short friendly follow-up email to a client who went quiet after our pricing call.' },
]

// Short, human labels for the sidebar/chips ("Top Agent" reads better as
// "Chief of Staff", "Market Research Agent" as "Market Research").
const SHORT_NAME = {
  top_agent: 'Chief of Staff',
  sales_agent: 'Sales',
  onboarding_agent: 'Onboarding',
  negotiation_agent: 'Negotiation',
  finance_agent: 'Finance',
  legal_agent: 'Legal',
  strategy_agent: 'Strategy',
  market_research_agent: 'Market Research',
  briefing_agent: 'Briefing',
  refinement_agent: 'Refinement',
}

function shortName(a) {
  return SHORT_NAME[a.agent_id] || a.name.replace(' Agent', '')
}


// ---------------------------------------------------------------------------
// The view
// ---------------------------------------------------------------------------

const WELCOME = {
  role: 'brain',
  text: "Hi, I'm your **Company Brain** — a Chief of Staff coordinating a team of specialists: sales, finance, legal, market research, strategy and more.\n\nAsk me anything, or start with a suggestion below.",
}

export default function ModernChat({ onExit }) {
  const { connected, snapshot } = useAgentStatus()
  const [messages, setMessages] = useState(() => [WELCOME])
  const [input, setInput] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState(null)
  const [sessions, setSessions] = useState([]) // recent server-side chats
  const [loadingHistory, setLoadingHistory] = useState(false)
  const [attachments, setAttachments] = useState([]) // {id, file, note, text, error}
  const [dragging, setDragging] = useState(false)
  const [extracting, setExtracting] = useState(false)
  const fileInputRef = useRef(null)
  const sessionRef = useRef(loadSessionId())
  const scrollRef = useRef(null)
  const taRef = useRef(null)

  const agents = snapshot?.agents || []

  // agents currently working — shown as live chips above the composer
  const activeAgents = agents.filter((a) => a.state === 'working' || a.state === 'handoff')

  useEffect(() => {
    const el = scrollRef.current
    if (el) el.scrollTop = el.scrollHeight
  }, [messages, busy, activeAgents.length, loadingHistory])

  // composer auto-grow
  const grow = () => {
    const ta = taRef.current
    if (!ta) return
    ta.style.height = 'auto'
    ta.style.height = Math.min(ta.scrollHeight, 200) + 'px'
  }

  const refreshSessions = () => {
    fetchSessions().then(setSessions)
  }

  // load the recent-sessions list once, then after each completed reply
  useEffect(() => {
    refreshSessions()
  }, [messages.length === 1 ? 0 : messages.length])

  // open a past chat: swap the session id, then replay its messages
  const openSession = async (sid) => {
    if (busy || sid === sessionRef.current) return
    sessionRef.current = sid
    try {
      localStorage.setItem('cb_session_id', sid)
    } catch {
      /* ignore */
    }
    setError(null)
    setInput('')
    setLoadingHistory(true)
    setMessages([]) // clear immediately so old text can't bleed into the new chat
    const msgs = await fetchSessionMessages(sid)
    setLoadingHistory(false)
    setMessages(msgs && msgs.length > 0 ? msgs : [WELCOME])
  }

  // ---- attachments ----

  const addFiles = async (fileList) => {
    const files = Array.from(fileList || [])
    if (files.length === 0) return
    const batch = files.map((f) => ({
      id: Math.random().toString(36).slice(2, 9),
      file: f,
      note: 'reading…',
      text: '',
      error: null,
    }))
    setAttachments((a) => [...a, ...batch])
    setExtracting(true)
    await Promise.all(
      batch.map(async (att) => {
        try {
          const { name, text, note } = await extractFileText(att.file)
          setAttachments((a) =>
            a.map((x) => (x.id === att.id ? { ...x, text, note: `${name} · ${note}` } : x)),
          )
        } catch (e) {
          setAttachments((a) =>
            a.map((x) =>
              x.id === att.id
                ? { ...x, note: att.file.name, error: e?.message || 'could not read file' }
                : x,
            ),
          )
        }
      }),
    )
    setExtracting(false)
  }

  const removeAttachment = (id) => setAttachments((a) => a.filter((x) => x.id !== id))

  async function send(preset) {
    const typed = (preset ?? input).trim()
    if ((!typed && attachments.length === 0) || busy) return
    // Build the outgoing message: prompt + extracted file contents. The
    // attachments' text rides inline so the model can actually read them.
    const parts = []
    if (typed) parts.push(typed)
    for (const att of attachments) {
      if (att.error) {
        parts.push(`[Attached file: ${att.file.name} — ${att.error}]`)
      } else if (att.text) {
        parts.push(`[Attached file: ${att.file.name}]\n"""\n${att.text}\n"""`)
      } else {
        parts.push(`[Attached file: ${att.file.name} — ${att.note}]`)
      }
    }
    const text = parts.join('\n\n')
    const shownFiles = attachments.map((a) => a.file.name)
    setInput('')
    setAttachments([])
    if (taRef.current) taRef.current.style.height = 'auto'
    setError(null)
    setMessages((m) => [
      ...m,
      { role: 'user', text: typed || '(sent attachments)', files: shownFiles },
    ])
    setBusy(true)
    try {
      const body = new FormData()
      body.append('message', text)
      body.append('stream', 'false')
      body.append('session_id', sessionRef.current)
      const res = await fetch(`/teams/${TEAM_ID}/runs`, { method: 'POST', body })
      if (!res.ok) throw new Error(`HTTP ${res.status} ${res.statusText}`)
      const data = await res.json()
      const reply =
        (typeof data?.content === 'string' && data.content.trim()) ||
        '(no content returned)'
      setMessages((m) => [...m, { role: 'brain', text: reply }])
      refreshSessions() // the new exchange becomes a visible recent chat
    } catch (e) {
      setError(e?.message ? String(e.message) : String(e))
    } finally {
      setBusy(false)
    }
  }

  const startNewChat = () => {
    if (busy) return
    sessionRef.current = newSession()
    setMessages([WELCOME])
    setError(null)
  }

  return (
    <div className="mc-root">
      <aside className="mc-sidebar">
        <div className="mc-side-top">
          <div className="mc-brand">
            <BrainMark size={26} />
            <span>Company Brain</span>
          </div>
          <button className="mc-newchat" onClick={startNewChat} title="Start a new conversation">
            <span className="mc-plus">+</span> New chat
          </button>
        </div>

        <div className="mc-side-agents">
          <div className="mc-side-label">
            team · live
            <span className={`mc-conn ${connected ? 'on' : ''}`}>{connected ? 'online' : 'offline'}</span>
          </div>
          {agents.length === 0 && <div className="mc-side-empty">connecting…</div>}
          {agents.map((a) => (
            <div key={a.agent_id} className={`mc-agent ${a.state === 'working' ? 'busy' : ''}`}>
              <AgentDot state={a.state || 'idle'} />
              <span className="mc-agent-name">{shortName(a)}</span>
              <span className="mc-agent-state">{a.state || 'idle'}</span>
            </div>
          ))}
        </div>

        <div className="mc-sessions">
          <div className="mc-side-label">
            recent chats
            {sessions.length > 0 && <span className="mc-sess-count">{sessions.length}</span>}
          </div>
          {sessions.length === 0 && <div className="mc-side-empty">no saved chats yet</div>}
          {sessions.map((s) => (
            <button
              key={s.session_id}
              className={`mc-session ${s.session_id === sessionRef.current ? 'active' : ''}`}
              onClick={() => openSession(s.session_id)}
              title={s.session_name || s.session_id}
            >
              <span className="mc-session-icon">✦</span>
              <span className="mc-session-body">
                <span className="mc-session-name">
                  {(s.session_name || s.session_id).slice(0, 60)}
                </span>
                <span className="mc-session-time">{timeAgo(s.updated_at || s.created_at)}</span>
              </span>
            </button>
          ))}
        </div>

        <button className="mc-exit" onClick={onExit} title="Back to the office-floor workbench">
          ▤ Office floor view
        </button>
        <div className="mc-side-foot">
          powered by <b>Company Brain</b> · Agno AgentOS
        </div>
      </aside>

      <main className="mc-main">
        <header className="mc-header">
          <button className="mc-back" onClick={onExit} title="Back to the office-floor workbench">
            ☰
          </button>
          <div className="mc-header-title">
            <BrainMark size={20} />
            <span>Company Brain</span>
          </div>
          <div className="mc-header-sub">
            coordinate-mode team · {agents.length} specialists
          </div>
        </header>

        <div className="mc-scroll" ref={scrollRef}>
          <div className="mc-thread">
            {loadingHistory && (
              <div className="mc-loading-history">loading conversation…</div>
            )}
            {!loadingHistory && messages.map((m, i) =>
              m.role === 'user' ? (
                <div key={i} className="mc-row user">
                  <div className="mc-bubble user">
                    {m.files?.length > 0 && (
                      <div className="mc-bubble-files">
                        {m.files.map((f) => (
                          <span key={f} className="mc-filetag" title={f}>
                            📄 {f}
                          </span>
                        ))}
                      </div>
                    )}
                    {m.text}
                  </div>
                </div>
              ) : (
                <div key={i} className="mc-row brain">
                  <div className="mc-avatar">
                    <BrainMark size={24} />
                  </div>
                  <div className="mc-brain-body">
                    <div className="mc-md" dangerouslySetInnerHTML={{ __html: renderMarkdown(m.text) }} />
                    {i > 0 && <CopyButton text={m.text} />}
                  </div>
                </div>
              ),
            )}
            {busy && (
              <div className="mc-row brain">
                <div className="mc-avatar">
                  <BrainMark size={24} />
                </div>
                <div className="mc-thinking">
                  <span />
                  <span />
                  <span />
                </div>
              </div>
            )}
            {messages.length === 1 && !busy && !loadingHistory && (
              <div className="mc-suggest">
                {SUGGESTIONS.map((s) => (
                  <button key={s.title} className="mc-card" onClick={() => send(s.text)}>
                    <span className="mc-card-icon">{s.icon}</span>
                    <span className="mc-card-title">{s.title}</span>
                    <span className="mc-card-text">{s.text}</span>
                  </button>
                ))}
              </div>
            )}
          </div>
        </div>

        <div
          className="mc-dock"
          onDragOver={(e) => {
            e.preventDefault()
            setDragging(true)
          }}
          onDragLeave={(e) => {
            if (e.currentTarget.contains(e.relatedTarget)) return
            setDragging(false)
          }}
          onDrop={(e) => {
            e.preventDefault()
            setDragging(false)
            addFiles(e.dataTransfer?.files)
          }}
        >
          {dragging && (
            <div className="mc-dropzone">drop files to attach…</div>
          )}
          {activeAgents.length > 0 && (
            <div className="mc-active">
              {activeAgents.map((a) => (
                <span key={a.agent_id} className={`mc-chip ${a.state}`}>
                  <AgentDot state={a.state} />
                  {shortName(a)} {a.state === 'handoff' ? 'handing off…' : 'working…'}
                </span>
              ))}
            </div>
          )}
          {attachments.length > 0 && (
            <div className="mc-attach-strip">
              {attachments.map((att) => (
                <span key={att.id} className={`mc-attach ${att.error ? 'error' : ''}`} title={att.note}>
                  <span className="mc-attach-icon">📄</span>
                  <span className="mc-attach-body">
                    <span className="mc-attach-name">{att.file.name}</span>
                    <span className="mc-attach-note">
                      {att.error ? att.error : att.note}
                      {att.note === 'reading…' ? '' : ` · ${fmtSize(att.file.size)}`}
                    </span>
                  </span>
                  <button
                    className="mc-attach-x"
                    title="Remove"
                    onClick={() => removeAttachment(att.id)}
                  >
                    ✕
                  </button>
                </span>
              ))}
            </div>
          )}
          {error && <div className="mc-error">⚠ {error}</div>}
          <div className="mc-inputwrap">
            <input
              ref={fileInputRef}
              type="file"
              multiple
              hidden
              onChange={(e) => {
                addFiles(e.target.files)
                e.target.value = '' // allow re-adding the same file
              }}
            />
            <button
              className="mc-attachbtn"
              title="Attach files (PDF, text, code, data…)"
              onClick={() => fileInputRef.current?.click()}
            >
              <svg width="17" height="17" viewBox="0 0 24 24" fill="none">
                <path
                  d="M21.44 11.05l-9.19 9.19a6 6 0 01-8.49-8.49l9.2-9.19a4 4 0 015.66 5.66l-9.2 9.19a2 2 0 01-2.83-2.83l8.49-8.48"
                  stroke="currentColor"
                  strokeWidth="2"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                />
              </svg>
            </button>
            <textarea
              ref={taRef}
              className="mc-input"
              rows={1}
              placeholder="Message Company Brain — or drop / paste a file…"
              value={input}
              onChange={(e) => {
                setInput(e.target.value)
                grow()
              }}
              onPaste={(e) => {
                const pasted = e.clipboardData?.files
                if (pasted && pasted.length > 0) {
                  e.preventDefault()
                  addFiles(pasted)
                }
              }}
              onKeyDown={(e) => {
                if (e.key === 'Enter' && !e.shiftKey) {
                  e.preventDefault()
                  send()
                }
              }}
            />
            <button
              className={`mc-send ${busy || (!input.trim() && attachments.length === 0) ? 'disabled' : ''}`}
              onClick={() => send()}
              disabled={busy || (!input.trim() && attachments.length === 0)}
              title="Send"
            >
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none">
                <path d="M12 19V5m0 0l-6 6m6-6l6 6" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round" />
              </svg>
            </button>
          </div>
          <div className="mc-foot">
            Attach PDFs, docs, code or data — drop, paste, or click 📎. Links pasted in the message work too.
          </div>
        </div>
      </main>
    </div>
  )
}
