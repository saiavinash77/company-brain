// Modern "ChatGPT-style" interface — clean, readable, content-first.
// Separate from the office-floor workbench: that one is the fun visual,
// this one is the clear daily driver for actually reading what the team says.

import { useEffect, useRef, useState } from 'react'
import { useAgentStatus } from './floor/useAgentStatus.js'
import './modern.css'

const TEAM_ID = 'company-brain'

// ---------------------------------------------------------------------------
// Who is talking — the company's people. Typed as a slash command (/Sai) in
// the composer or picked from the header dropdown; remembered per browser
// (cb_person). Every run then carries user_id=<person>, which the server
// uses to (a) tag the message so agents know who's asking and (b) store the
// session in that person's own space (sessions are filtered per person).
// ---------------------------------------------------------------------------

const DEFAULT_PEOPLE = [
  { id: 'sai', display: 'Sai', slash: '/Sai', role: 'Owner' },
  { id: 'bruhadish', display: 'Bruhadish', slash: '/Bruhadish', role: 'Operations' },
  { id: 'sravani', display: 'Sravani', slash: '/Sravani', role: 'Finance' },
]

function loadPerson(people) {
  try {
    const saved = localStorage.getItem('cb_person')
    if (saved && people.some((p) => p.id === saved)) return saved
  } catch {
    /* private mode */
  }
  return null // null = "everyone/anonymous" until the first slash or pick
}

// leading "/Sai" (any capitalization) at the start of the input switches
// identity; the command itself is stripped from the message before sending
const SLASH_CMD = /^\s*\/(sai|bruhadish|sravani)\b/i
function parseSlash(text, people) {
  const m = (text || '').match(SLASH_CMD)
  if (!m) return null
  const id = m[1].toLowerCase()
  return people.find((p) => p.id === id) || null
}

function personSessionKey(person) {
  return person ? `cb_session_id_${person}` : 'cb_session_id'
}

// Session id inside a client folder: client/<slug>/<person>-<rand>. The
// prefix is what the server's /api/clients/:slug/sessions filters on.
function folderSessionId(person, client) {
  if (!client) return loadSessionId(person) // general space
  const slug = String(client.id || client.name || '')
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/^-+|-+$/g, '')
    .slice(0, 60)
  const who = person || 'web'
  const key = `cb_session_id_client_${slug}_${who}`
  let sid = null
  try {
    sid = localStorage.getItem(key)
  } catch {
    /* private mode */
  }
  if (!sid) {
    sid = `client/${slug}/${who}-${Math.random().toString(36).slice(2, 10)}`
    try {
      localStorage.setItem(key, sid)
    } catch {
      /* ignore */
    }
  }
  return sid
}

// "/client cake magic" switches into that client's folder (creates it if
// new); the command itself is stripped from the message.
const CLIENT_CMD = /^\s*\/client\s+([\w .&-]+)\s*$/i

// Agno auto-names sessions from the first message — which carries the
// "[Sai is asking — Owner — …]" speaker tag we prepend for the agents.
// Strip it so the sidebar shows the person's actual first words.
function cleanSessionTitle(name) {
  return (name || '').replace(/^\[[^\]]*\]\s*/, '')
}

// Human labels for what the team is doing while the owner waits. Tool names
// arrive in ToolCallStarted/Completed SSE events; without this the raw
// "search_web(max_results=10, query=...) completed in 1.4s" line was shown
// in the chat as if it were the answer.
const TOOL_LABELS = [
  [/^search_web$|serper|duckduck/i, 'Searching the web…'],
  [/memory|get_documents|knowledge|playbook/i, 'Checking our records…'],
  [/send_whatsapp|send_message|twilio|telegram/i, 'Sending a message…'],
  [/gmail|send_email|read_email/i, 'Working with email…'],
  [/price|pricing|calculate|compute/i, 'Running the numbers…'],
  [/convert|lead/i, 'Setting up the client…'],
  [/file|document|extract|read/i, 'Reading documents…'],
]

function toolLabel(toolName) {
  const name = String(toolName || '')
  for (const [re, label] of TOOL_LABELS) if (re.test(name)) return label
  return 'Working…'
}

// A rate limit (or any run error) should read as one calm sentence, not a
// raw RunError JSON dump.
function friendlyError(msg) {
  const s = String(msg || '')
  if (/rate.?limit/i.test(s) || /\b429\b/.test(s)) return 'The team hit its thinking speed-limit — please send that again in about a minute.'
  if (/timeout/i.test(s)) return 'That took too long to answer — please try again.'
  return s.slice(0, 200)
}

function loadSessionId(person) {
  const key = personSessionKey(person)
  let sid = null
  try {
    sid = localStorage.getItem(key)
  } catch {
    /* private mode etc. */
  }
  if (!sid) {
    sid = (person ? person + '-' : 'web-') + Math.random().toString(36).slice(2, 10)
    try {
      localStorage.setItem(key, sid)
    } catch {
      /* ignore */
    }
  }
  return sid
}

function newSession(person) {
  const key = personSessionKey(person)
  const sid = (person ? person + '-' : 'web-') + Math.random().toString(36).slice(2, 10)
  try {
    localStorage.setItem(key, sid)
  } catch {
    /* ignore */
  }
  return sid
}

// ---------------------------------------------------------------------------
// Sessions — conversations persist server-side (Postgres via AgentOS).
// GET /sessions lists them; GET /sessions/:id/runs replays the messages.
// ---------------------------------------------------------------------------

async function fetchSessions(person) {
  try {
    // person-aware listing: the server filters by the user_id runs were
    // stored with, so each person only sees their own chats
    const url = person
      ? `/api/sessions/${encodeURIComponent(person)}?limit=30`
      : '/sessions?limit=30'
    const res = await fetch(url)
    if (!res.ok) return []
    const data = await res.json()
    const list = person ? data.sessions || [] : Array.isArray(data) ? data : data.data || []
    return list
      .filter((s) => s.session_type === 'team' || person)
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
const LINK_CHAR_CAP = 12000

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
    const out = { name, text: text.slice(0, TEXT_CHAR_CAP).trim(), note: `PDF, ${pdf.numPages} pages${more}` }
    if (out.text) return out
    // scanned PDF with no text layer → let the server OCR it
    return extractServerSide(file)
  }
  if (isTextFile(name, file.type)) {
    const raw = await file.text()
    return { name, text: raw.slice(0, TEXT_CHAR_CAP), note: 'text' }
  }
  // Images, DOCX, XLSX… — the browser can't read these. The server's OCR
  // endpoint can (Mistral OCR reads screenshots and office documents).
  const server = await extractServerSide(file)
  if (server) return server
  // Binary we can't read anywhere: still tell the team the file exists
  return {
    name,
    text: '',
    note: `${file.type || 'unknown type'}, ${(file.size / 1024).toFixed(0)} KB — contents could not be read`,
  }
}

// Server-side extraction (images / office docs / scanned PDFs) — POST the
// raw file to /api/extract-file, get OCR text (+ visual description for
// images) back.
async function extractServerSide(file) {
  try {
    const body = new FormData()
    body.append('file', file)
    const res = await fetch('/api/extract-file', { method: 'POST', body })
    if (!res.ok) return null
    const d = await res.json()
    if (d && typeof d.text === 'string') {
      return { name: d.name || file.name, text: d.text.slice(0, TEXT_CHAR_CAP), note: d.note || 'OCR' }
    }
    return null
  } catch {
    return null
  }
}

// Read a web page the user pasted, server-side: page text (or image
// description) rides inline so the agents actually see the link's content.
async function fetchLinkText(url) {
  try {
    const res = await fetch('/api/fetch-link', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ url }),
    })
    if (!res.ok) return null
    const d = await res.json()
    if (d && typeof d.text === 'string' && d.text) {
      return { title: d.title || url, text: d.text.slice(0, LINK_CHAR_CAP) }
    }
    return null
  } catch {
    return null
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

export function renderMarkdown(md) {
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

// Professional inline icon set — stroke-based, inherits the text color.
function Icon({ name, size = 16 }) {
  const paths = {
    // sidebar + folders
    agents: <><rect x="3" y="7" width="18" height="13" rx="2" /><path d="M3 7l2-4h6l2 4" /></>,
    chat: <path d="M21 12a8 8 0 0 1-8 8H4l2-3a8 8 0 1 1 15-5z" />,
    folder: <path d="M3 7a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v9a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z" />,
    plus: <><path d="M12 5v14" /><path d="M5 12h14" /></>,
    // suggestion cards
    target: <><circle cx="12" cy="12" r="9" /><circle cx="12" cy="12" r="5" /><circle cx="12" cy="12" r="1" /></>,
    doc: <><path d="M14 3H6a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V9z" /><path d="M14 3v6h6" /></>,
    scan: <><path d="M3 7V5a2 2 0 0 1 2-2h2" /><path d="M17 3h2a2 2 0 0 1 2 2v2" /><path d="M21 17v2a2 2 0 0 1-2 2h-2" /><path d="M7 21H5a2 2 0 0 1-2-2v-2" /><circle cx="12" cy="12" r="3" /></>,
    send: <><path d="M22 2L11 13" /><path d="M22 2l-7 20-4-9-9-4z" /></>,
    // misc
    menu: <><path d="M4 6h16" /><path d="M4 12h16" /><path d="M4 18h16" /></>,
    attach: <path d="M21.4 11.1l-8.5 8.5a5.5 5.5 0 0 1-7.8-7.8l8.5-8.5a3.7 3.7 0 0 1 5.2 5.2l-8.5 8.5a1.8 1.8 0 0 1-2.6-2.6l7.9-7.8" />,
  }
  return (
    <svg
      className="mc-icon"
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.8"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      {paths[name] || paths.chat}
    </svg>
  )
}

function BrainMark({ size = 28 }) {
  // The user's Company Brain logo — white tile, periwinkle mark.
  return (
    <img
      src="/floor/logo.png"
      alt="Company Brain"
      className="mc-mark"
      style={{ width: size, height: size }}
      draggable={false}
    />
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

// ---------------------------------------------------------------------------
// Reader settings — text size and font, remembered per browser.
// ---------------------------------------------------------------------------

const FONT_CHOICES = [
  { id: 'josefin', label: 'Josefin Sans', stack: "'Josefin Sans', 'Segoe UI', sans-serif" },
  { id: 'system', label: 'System', stack: "'Segoe UI', system-ui, sans-serif" },
  { id: 'georgia', label: 'Bookish', stack: "Georgia, 'Times New Roman', serif" },
  { id: 'mono', label: 'Mono', stack: "'Cascadia Mono', 'Consolas', monospace" },
]

const SIZE_CHOICES = [
  { id: 'small', label: 'A', cls: 'mc-size-small', px: '14px' },
  { id: 'medium', label: 'A', cls: 'mc-size-medium', px: '15.5px' },
  { id: 'large', label: 'A', cls: 'mc-size-large', px: '17.5px' },
]

function loadReaderPrefs() {
  let font = 'josefin'
  let size = 'medium'
  try {
    font = localStorage.getItem('cb_font') || font
    size = localStorage.getItem('cb_text_size') || size
  } catch {
    /* private mode */
  }
  return { font, size }
}

export default function ModernChat({ onExit }) {
  const { connected, snapshot } = useAgentStatus()
  const [messages, setMessages] = useState(() => [])
  const [input, setInput] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState(null)
  const [sessions, setSessions] = useState([]) // recent server-side chats
  const [loadingHistory, setLoadingHistory] = useState(false)
  const [attachments, setAttachments] = useState([]) // {id, file, note, text, error}
  const [dragging, setDragging] = useState(false)
  const [extracting, setExtracting] = useState(false)
  const [showSettings, setShowSettings] = useState(false)
  const [showPeople, setShowPeople] = useState(false)
  const [showAgents, setShowAgents] = useState(false)
  const [clients, setClients] = useState([]) // client folders
  const [activeClient, setActiveClient] = useState(null) // {id, name} | null
  const [showNewClient, setShowNewClient] = useState(false)
  const [newClientName, setNewClientName] = useState('')
  const [people, setPeople] = useState(DEFAULT_PEOPLE)
  const [person, setPerson] = useState(null) // 'sai' | 'bruhadish' | 'sravani' | null
  const [prefs, setPrefs] = useState(loadReaderPrefs)
  const fileInputRef = useRef(null)
  const sessionRef = useRef(null)
  const scrollRef = useRef(null)
  const taRef = useRef(null)
  const abortRef = useRef(null) // AbortController for the in-flight run (Stop button)
  const stoppedRef = useRef(false) // distinguishes user-stop from a real error

  // registry + last-used person, then the matching session id
  useEffect(() => {
    let alive = true
    fetch('/api/people')
      .then((r) => (r.ok ? r.json() : null))
      .then((d) => {
        if (!alive || !d?.people?.length) return
        setPeople(d.people)
        setPerson((cur) => cur || loadPerson(d.people))
      })
      .catch(() => {})
    return () => {
      alive = false
    }
  }, [])

  // (re)load the session for the active person
  useEffect(() => {
    setPerson((cur) => {
      if (cur === undefined) return loadPerson(DEFAULT_PEOPLE)
      return cur
    })
  }, [])

  // ---- client folders ----------------------------------------------------
  const refreshClients = () => {
    fetch('/api/clients')
      .then((r) => (r.ok ? r.json() : null))
      .then((d) => d?.clients && setClients(d.clients))
      .catch(() => {})
  }
  useEffect(() => {
    refreshClients()
  }, [])

  const selectClient = (client) => {
    if (busy) return
    setActiveClient(client)
    try {
      if (client) localStorage.setItem('cb_client', client.id)
      else localStorage.removeItem('cb_client')
    } catch {
      /* ignore */
    }
    // swap to the folder's session space (each folder = its own session id)
    sessionRef.current = folderSessionId(person, client)
    setMessages([])
    setError(null)
    setInput('')
    // load this folder's chats (or the person's general chats)
    loadFolderSessions()
  }

  const createClient = (name) => {
    fetch('/api/clients', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ name }),
    })
      .then((r) => (r.ok ? r.json() : null))
      .then((d) => {
        if (!d?.client) return
        refreshClients()
        selectClient(d.client)
      })
      .catch(() => {})
  }

  const loadFolderSessions = () => {
    if (activeClient || true) {
      // current folder's chats: client → /api/clients/:slug/sessions,
      // general → the person's session list
      const loader = activeClient
        ? fetch(`/api/clients/${encodeURIComponent(activeClient.id)}/sessions?limit=30`)
            .then((r) => (r.ok ? r.json() : { sessions: [] }))
            .then((d) => d.sessions || [])
        : fetchSessions(person)
      loader.then(setSessions).catch(() => setSessions([]))
    }
  }

  // re-focus the folder when the person changes (folders are per person too)
  useEffect(() => {
    const saved = localStorage.getItem('cb_client')
    if (saved && clients.length > 0) {
      const c = clients.find((x) => x.id === saved)
      if (c) setActiveClient(c)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [clients.length])
  useEffect(() => {
    sessionRef.current = loadSessionId(person)
    refreshSessions()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [person])

  // apply reader prefs: size class + font var on the whole chat root
  useEffect(() => {
    const font = FONT_CHOICES.find((f) => f.id === prefs.font) || FONT_CHOICES[0]
    const size = SIZE_CHOICES.find((s) => s.id === prefs.size) || SIZE_CHOICES[1]
    const root = document.documentElement
    root.style.setProperty('--mc-font', font.stack)
    root.classList.remove('mc-size-small', 'mc-size-medium', 'mc-size-large')
    root.classList.add(size.cls)
  }, [prefs])

  // (welcome-screen news/recap briefing removed — a clean, focused start)

  const agents = snapshot?.agents || []
  const personObj = person ? people.find((p) => p.id === person) : null

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
    if (activeClient) {
      fetch(`/api/clients/${encodeURIComponent(activeClient.id)}/sessions?limit=30`)
        .then((r) => (r.ok ? r.json() : { sessions: [] }))
        .then((d) => setSessions(d.sessions || []))
        .catch(() => {})
    } else {
      fetchSessions(person).then(setSessions)
    }
  }

  // switch person: remember it, swap to that person's session + chats
  const switchPerson = (id) => {
    setShowPeople(false)
    if (busy || id === person) return
    setPerson(id)
    try {
      if (id) localStorage.setItem('cb_person', id)
      else localStorage.removeItem('cb_person')
    } catch {
      /* ignore */
    }
    setMessages([])
    setError(null)
    setInput('')
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
      localStorage.setItem(personSessionKey(person), sid)
    } catch {
      /* ignore */
    }
    setError(null)
    setInput('')
    setLoadingHistory(true)
    setMessages([]) // clear immediately so old text can't bleed into the new chat
    const msgs = await fetchSessionMessages(sid)
    setLoadingHistory(false)
    setMessages(msgs && msgs.length > 0 ? msgs : [])
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
    let typed = (preset ?? input).trim()
    if ((!typed && attachments.length === 0) || busy) return
    // "/client <name>" — switch into (or create) that client's folder first
    const clientMatch = typed.match(CLIENT_CMD)
    if (clientMatch) {
      const name = clientMatch[1].trim()
      const existing = clients.find(
        (c) => c.name.toLowerCase() === name.toLowerCase() || c.id === name.toLowerCase().replace(/[^a-z0-9]+/g, '-'),
      )
      if (existing) {
        selectClient(existing)
      } else {
        createClient(name)
      }
      setInput('')
      return
    }
    // "/Sai <msg>" at the start switches the speaker and is stripped from
    // the message; the chosen person rides along as user_id on every run
    const slash = parseSlash(typed, people)
    if (slash) {
      if (slash.id !== person) {
        setPerson(slash.id)
        try {
          localStorage.setItem('cb_person', slash.id)
        } catch {
          /* ignore */
        }
        sessionRef.current = loadSessionId(slash.id)
        setMessages([])
      }
      typed = typed.replace(SLASH_CMD, '').trim()
    }
    const speaker = slash ? slash.id : person
    if (!typed && attachments.length === 0) return
    // Links pasted in the message: fetch their content server-side so the
    // agents read the page instead of dead-ending at "I can't open links".
    const urls = [...new Set((typed.match(/https?:\/\/[^\s)>\]]+/g) || []))]
      .slice(0, 3) // cap: 3 links per message keeps runs bounded
    const linkParts = []
    if (urls.length > 0) {
      const fetched = await Promise.all(urls.map((u) => fetchLinkText(u)))
      fetched.forEach((res, i) => {
        if (res) linkParts.push(`[Link: ${urls[i]} — "${res.title}"]\n"""\n${res.text}\n"""`)
      })
    }
    // Build the outgoing message: prompt + extracted file contents. The
    // attachments' text rides inline so the model can actually read them.
    const parts = []
    if (typed) parts.push(typed)
    parts.push(...linkParts)
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
    stoppedRef.current = false
    abortRef.current = new AbortController()
    try {
      // stream=true: reply tokens arrive as SSE and render progressively.
      // The event payload shape is tolerant (content | delta | text fields,
      // bare strings, JSON-wrapped) because AgentOS event classes vary.
      const body = new FormData()
      body.append('message', text)
      body.append('stream', 'true')
      body.append('session_id', sessionRef.current)
      if (speaker) body.append('user_id', speaker) // who is asking → speaker tag + own session space
      const res = await fetch(`/teams/${TEAM_ID}/runs`, { method: 'POST', body, signal: abortRef.current.signal })
      if (!res.ok) throw new Error(`HTTP ${res.status} ${res.statusText}`)
      const ctype = res.headers.get('content-type') || ''

        let streamed = ''
        let toolStatus = ''
        if (ctype.includes('text/event-stream')) {
          const reader = res.body.getReader()
          const decoder = new TextDecoder()
          let buf = ''
          let dispatch = () => {}
          // placeholder brain message; its text is updated as tokens arrive
          setMessages((m) => [...m, { role: 'brain', text: '' }])
          const updateLast = (chunk) => {
            streamed += chunk
            setMessages((m) => m.map((x, i) => (i === m.length - 1 ? { ...x, text: streamed } : x)))
          }
          const setBusyStatus = (label) => {
            if (label === toolStatus) return
            toolStatus = label
            setMessages((m) =>
              m.map((x, i) => (i === m.length - 1 ? { ...x, status: label } : x)),
            )
          }
          // SSE frames: blank-line separated; each has "event:" and/or "data:"
          // AgentOS team events observed live:
          //   TeamRunContent        — incremental answer tokens in `content`
          //                           (gpt-oss also streams `reasoning_content`
          //                           thinking chunks, which we skip)
          //   TeamToolCallStarted / TeamToolCallCompleted — the team is using
          //                           a tool; shown as a friendly status line
          //                           under the reply, never as reply text
          //   TeamRunContentCompleted / TeamRunCompleted — full final text
          const handleFrame = (frame) => {
            let evName = ''
            let dataStr = ''
            for (const line of frame.split('\n')) {
              if (line.startsWith('event:')) evName = line.slice(6).trim()
              else if (line.startsWith('data:')) dataStr += line.slice(5).trim()
            }
            if (!dataStr) return
            let d = null
            try {
              d = JSON.parse(dataStr)
            } catch {
              return // keep-alive comment or non-JSON payload
            }
            const ev = d.event || evName || ''
            if (ev === 'TeamToolCallStarted') {
              setBusyStatus(toolLabel(d.tool?.tool_name))
              return
            }
            if (ev === 'TeamToolCallCompleted') {
              // the tool's raw result text must never become the answer
              if (typeof d.content === 'string' && !streamed) {
                setBusyStatus(toolLabel(d.tool?.tool_name))
              }
              return
            }
            if (ev.includes('Error') || evName.includes('error')) {
              const detail = d.content?.error || d.content || d.message || dataStr
              throw new Error(friendlyError(typeof detail === 'string' ? detail : JSON.stringify(detail)))
            }
            if (ev === 'TeamRunContent') {
              const c = d.content
              if (typeof c === 'string' && c && !d.reasoning_content) updateLast(c)
              return
            }
            if (ev === 'TeamRunCompleted' || ev === 'TeamRunContentCompleted') {
              // authoritative final text — replace whatever we accumulated
              // (identical when streaming worked; a fix-up if chunks were missed)
              const full = typeof d.content === 'string' ? d.content : ''
              if (full) {
                streamed = full
                setMessages((m) => m.map((x, i) => (i === m.length - 1 ? { ...x, text: full, status: '' } : x)))
              }
              return
            }
            // any other streaming format: tolerate delta/text fields — but
            // never anything from a tool event (those carry tool results)
            if (ev.includes('Tool') || ev.includes('tool')) return
            const piece =
              (typeof d.delta === 'string' && d.delta) ||
              (typeof d.text === 'string' && d.text) ||
              (typeof d.content === 'string' && d.content) ||
              (typeof d === 'string' && d) ||
              ''
            if (piece && !d.reasoning_content) updateLast(piece)
          }
          dispatch = handleFrame
          let reading = true
          while (reading) {
            const { done, value } = await reader.read()
            if (done) break
            buf += decoder.decode(value, { stream: true })
            let idx
            while ((idx = buf.indexOf('\n\n')) >= 0) {
              const frame = buf.slice(0, idx)
              buf = buf.slice(idx + 2)
              dispatch(frame)
            }
          }
          if (buf.trim()) dispatch(buf)
          // clear the status chip once the stream ends
          setMessages((m) => m.map((x, i) => (i === m.length - 1 ? { ...x, status: '' } : x)))
        // ensure the last message carries the final text
        if (streamed) {
          setMessages((m) => m.map((x, i) => (i === m.length - 1 ? { ...x, text: streamed } : x)))
        } else {
          // stream produced no usable tokens — fall back to a plain run
          const body2 = new FormData()
          body2.append('message', text)
          body2.append('stream', 'false')
          body2.append('session_id', sessionRef.current)
          if (speaker) body2.append('user_id', speaker)
          const res2 = await fetch(`/teams/${TEAM_ID}/runs`, { method: 'POST', body: body2 })
          if (!res2.ok) throw new Error(`HTTP ${res2.status} ${res2.statusText}`)
          const data2 = await res2.json()
          const reply2 =
            (typeof data2?.content === 'string' && data2.content.trim()) ||
            '(no content returned)'
          setMessages((m) => m.map((x, i) => (i === m.length - 1 ? { ...x, text: reply2 } : x)))
        }
      } else {
        // not SSE — server answered with plain JSON
        const data = await res.json()
        const reply =
          (typeof data?.content === 'string' && data.content.trim()) ||
          '(no content returned)'
        setMessages((m) => [...m, { role: 'brain', text: reply }])
      }
      refreshSessions() // the new exchange becomes a visible recent chat
    } catch (e) {
      if (e?.name === 'AbortError' || stoppedRef.current) {
        // user pressed Stop — keep whatever streamed in so far, mark it done
        setMessages((m) =>
          m.map((x, i) =>
            i === m.length - 1 && x.role === 'brain'
              ? { ...x, text: x.text || '*(stopped before any reply arrived)*', status: '' }
              : x,
          ),
        )
      } else {
        setError(friendlyError(e?.message ? String(e.message) : String(e)))
        // drop the empty streaming placeholder if nothing arrived
        setMessages((m) => (m.length > 1 && m[m.length - 1].role === 'brain' && !m[m.length - 1].text ? m.slice(0, -1) : m))
      }
    } finally {
      stoppedRef.current = false
      abortRef.current = null
      setBusy(false)
    }
  }

  const stop = () => {
    stoppedRef.current = true
    abortRef.current?.abort()
  }

  const startNewChat = () => {
    if (busy) return
    if (activeClient) {
      // new chat INSIDE the client's folder (fresh folder session id)
      const who = person || 'web'
      const slug = activeClient.id
      sessionRef.current = `client/${slug}/${who}-${Math.random().toString(36).slice(2, 10)}`
      try {
        localStorage.setItem(`cb_session_id_client_${slug}_${who}`, sessionRef.current)
      } catch {
        /* ignore */
      }
    } else {
      sessionRef.current = newSession(person)
    }
    setMessages([])
    setError(null)
  }

  const setPref = (key, value) => {
    setPrefs((p) => {
      const next = { ...p, [key]: value }
      try {
        localStorage.setItem('cb_font', next.font)
        localStorage.setItem('cb_text_size', next.size)
      } catch {
        /* private mode */
      }
      return next
    })
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
          {agents.length > 0 && (
            <button className="mc-agents-folder" onClick={() => setShowAgents((v) => !v)}>
              <span className="mc-folder-icon"><Icon name="agents" size={15} /></span>
              <span className="mc-agent-name">Agents</span>
              <span className="mc-folder-count">{agents.length}</span>
              <span className={`mc-folder-arrow ${showAgents ? 'open' : ''}`}>▸</span>
            </button>
          )}
          {showAgents &&
            agents.map((a) => (
              <div key={a.agent_id} className={`mc-agent ${a.state === 'working' ? 'busy' : ''}`}>
                <AgentDot state={a.state || 'idle'} />
                <span className="mc-agent-name">{shortName(a)}</span>
                <span className="mc-agent-state">{a.state || 'idle'}</span>
              </div>
            ))}
        </div>

        <div className="mc-side-clients">
          <div className="mc-side-label">
            clients
            {activeClient && <span className="mc-client-active"> · {activeClient.name}</span>}
          </div>
          <button
            className={`mc-client-row ${!activeClient ? 'sel' : ''}`}
            onClick={() => selectClient(null)}
            title="Chats that belong to no client"
          >
            <span className="mc-folder-icon"><Icon name="chat" size={15} /></span>
            <span className="mc-agent-name">General</span>
          </button>
          {clients.map((c) => (
            <button
              key={c.id}
              className={`mc-client-row ${activeClient?.id === c.id ? 'sel' : ''}`}
              onClick={() => selectClient(c)}
              title={`Open ${c.name}'s folder`}
            >
              <span className="mc-folder-icon"><Icon name="folder" size={15} /></span>
              <span className="mc-agent-name">{c.name}</span>
            </button>
          ))}
          <button className="mc-client-new" onClick={() => setShowNewClient((v) => !v)} title="Start a folder for a new client">
            <span className="mc-plus"><Icon name="plus" size={13} /></span> New client
          </button>
          {showNewClient && (
            <form
              className="mc-client-form"
              onSubmit={(e) => {
                e.preventDefault()
                const name = newClientName.trim()
                if (!name) return
                createClient(name)
                setNewClientName('')
                setShowNewClient(false)
              }}
            >
              <input
                autoFocus
                value={newClientName}
                onChange={(e) => setNewClientName(e.target.value)}
                placeholder="client name…"
                maxLength={60}
              />
              <button type="submit">Create</button>
            </form>
          )}
        </div>

        <div className="mc-sessions">
          <div className="mc-side-label">
            {activeClient
              ? `${activeClient.name} · chats`
              : person
                ? `${personObj?.display}'s chats`
                : 'recent chats'}
            {sessions.length > 0 && <span className="mc-sess-count">{sessions.length}</span>}
          </div>
          {sessions.length === 0 && <div className="mc-side-empty">no saved chats yet</div>}
          {sessions.map((s) => (
            <button
              key={s.session_id}
              className={`mc-session ${s.session_id === sessionRef.current ? 'active' : ''}`}
              onClick={() => openSession(s.session_id)}
              title={cleanSessionTitle(s.session_name) || s.session_id}
            >
              <span className="mc-session-icon"><Icon name="chat" size={13} /></span>
              <span className="mc-session-body">
                <span className="mc-session-name">
                  {(cleanSessionTitle(s.session_name) || s.session_id).slice(0, 60)}
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
            <Icon name="menu" size={18} />
          </button>
          <div className="mc-header-title">
            <BrainMark size={20} />
            <span>Company Brain</span>
          </div>
          <div className="mc-header-sub">
            {activeClient ? `${activeClient.name}` : 'coordinate-mode team'} · {agents.length} specialists
          </div>
          <div className="mc-header-actions">
            {/* who is talking — /Sai-style slash names; agents tailor answers
                to this person and the session lives in their own space */}
            <div className="mc-who">
              <button
                className={`mc-who-btn ${person ? 'on' : ''} ${showPeople ? 'open' : ''}`}
                onClick={() => {
                  setShowPeople((v) => !v)
                  setShowSettings(false)
                }}
                title="Who is talking — agents answer as this person"
              >
                <span className="mc-who-avatar">{(personObj?.display || '?').slice(0, 1)}</span>
                <span className="mc-who-name">{personObj?.display || 'who?'}</span>
                <span className="mc-who-caret">▾</span>
              </button>
              {showPeople && (
                <div className="mc-people">
                  <div className="mc-people-head">who is talking?</div>
                  {people.map((p) => (
                    <button
                      key={p.id}
                      className={`mc-person ${person === p.id ? 'sel' : ''}`}
                      onClick={() => switchPerson(p.id)}
                    >
                      <span className="mc-person-avatar">{p.display.slice(0, 1)}</span>
                      <span className="mc-person-body">
                        <span className="mc-person-name">{p.display}</span>
                        <span className="mc-person-role">{p.role}</span>
                      </span>
                      {person === p.id && <span className="mc-person-check">✓</span>}
                    </button>
                  ))}
                  <div className="mc-people-foot">
                    or start any message with <b>{personObj?.slash || '/Sai'}</b>
                  </div>
                </div>
              )}
            </div>
            <button
              className={`mc-gear ${showSettings ? 'on' : ''}`}
              title="Text size & font"
              onClick={() => {
                setShowSettings((v) => !v)
                setShowPeople(false)
              }}
            >
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none">
                <path
                  d="M4 7h9m4 0h3M4 17h3m4 0h9M15 4v6M9 14v6"
                  stroke="currentColor"
                  strokeWidth="2"
                  strokeLinecap="round"
                />
                <circle cx="15" cy="7" r="2" stroke="currentColor" strokeWidth="2" />
                <circle cx="9" cy="17" r="2" stroke="currentColor" strokeWidth="2" />
              </svg>
            </button>
            {showSettings && (
              <div className="mc-prefs">
                <div className="mc-prefs-row">
                  <span className="mc-prefs-label">text size</span>
                  <div className="mc-prefs-opts">
                    {SIZE_CHOICES.map((s) => (
                      <button
                        key={s.id}
                        className={`mc-opt ${prefs.size === s.id ? 'sel' : ''}`}
                        style={{ fontSize: s.px }}
                        onClick={() => setPref('size', s.id)}
                      >
                        {s.label}
                      </button>
                    ))}
                  </div>
                </div>
                <div className="mc-prefs-row">
                  <span className="mc-prefs-label">font</span>
                  <div className="mc-prefs-opts">
                    {FONT_CHOICES.map((f) => (
                      <button
                        key={f.id}
                        className={`mc-opt ${prefs.font === f.id ? 'sel' : ''}`}
                        style={{ fontFamily: f.stack }}
                        onClick={() => setPref('font', f.id)}
                      >
                        {f.label}
                      </button>
                    ))}
                  </div>
                </div>
              </div>
            )}
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
                            <Icon name="doc" size={12} /> {f}
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
                    {m.status && !m.text && (
                      <div className="mc-tool-status">
                        <span className="mc-tool-dot" />
                        {m.status}
                      </div>
                    )}
                    {i > 0 && m.text && <CopyButton text={m.text} />}
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
            {messages.length === 0 && !busy && !loadingHistory && (
              <div className="mc-empty-hint">Type a message below to get started.</div>
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
                  <span className="mc-attach-icon"><Icon name="doc" size={13} /></span>
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
          {error && <div className="mc-error">{error}</div>}
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
              placeholder={
                activeClient
                  ? `Message ${activeClient.name}'s team — /Sai, /Bruhadish or /Sravani…`
                  : person
                    ? `Message Company Brain as ${personObj?.display}… (/Bruhadish, /Sravani to switch)`
                    : 'Message Company Brain — /Sai, /Bruhadish or /Sravani to say who you are…'
              }
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
            {busy ? (
              <button className="mc-send mc-stop" onClick={stop} title="Stop generating">
                <svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor">
                  <rect x="6" y="6" width="12" height="12" rx="2" />
                </svg>
              </button>
            ) : (
              <button
                className={`mc-send ${!input.trim() && attachments.length === 0 ? 'disabled' : ''}`}
                onClick={() => send()}
                disabled={!input.trim() && attachments.length === 0}
                title="Send"
              >
                <svg width="18" height="18" viewBox="0 0 24 24" fill="none">
                  <path d="M12 19V5m0 0l-6 6m6-6l6 6" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round" />
                </svg>
              </button>
            )}
          </div>
          <div className="mc-foot">
            Attach PDFs, docs, images or data — drop, paste, or click the clip. Links pasted in the message are read automatically.
          </div>
        </div>
      </main>
    </div>
  )
}
