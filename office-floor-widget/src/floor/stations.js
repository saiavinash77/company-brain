// Stations & decor — ported from munder-difflin's station catalog (DESIGN.md §9):
// agents WALK to the station matching their current task, work there with a
// tool bubble, then carry an artifact token back to their desk.
//
// All sprites are pure Pixi Graphics (no asset pack), pixel-snapped.
// Each station declares an absolute `stand` point where the actor parks.

import { Graphics } from 'pixi.js'
import { COLORS } from './tokens.js'

export const STATIONS = [
  {
    id: 'portal',
    x: 110,
    y: 112,
    stand: { x: 142, y: 208 },
    label: 'web portal',
    tool: 'searching the web',
    keywords:
      /\b(research|market|competitor|competitors|trend|trends|news|web|search|online|industry|benchmark)\b/i,
    draw(g) {
      // lilac archway with swirl
      g.rect(0, 24, 10, 44).fill('#7A5FA8')
      g.rect(38, 24, 10, 44).fill('#7A5FA8')
      g.rect(4, 12, 40, 14).fill('#8E6FC0')
      g.roundRect(6, -8, 36, 26, 16).fill('#8E6FC0')
      g.circle(24, 22, 11).fill(COLORS.lilac)
      g.circle(24, 22, 6).fill('#D6C5FF')
      g.circle(21, 19, 2).fill('#FFFFFF')
      g.rect(-4, 66, 56, 6).fill(COLORS.woodShadow)
    },
  },
  {
    id: 'terminal',
    x: 852,
    y: 118,
    stand: { x: 880, y: 202 },
    label: 'terminal',
    tool: 'running data queries',
    keywords:
      /\b(invoice|invoices|payment|payments|finance|financial|revenue|billing|sql|data|numbers|spreadsheet|ledger|accounts?)\b/i,
    draw(g) {
      // CRT terminal on a table
      g.rect(-6, 52, 60, 10).fill(COLORS.woodLight)
      g.roundRect(-6, 52, 60, 10, 2).stroke({ width: 2, color: COLORS.woodShadow })
      g.rect(2, 62, 8, 12).fill(COLORS.woodDark)
      g.rect(46, 62, 8, 12).fill(COLORS.woodDark)
      g.roundRect(2, 8, 44, 42, 4).fill('#3A3348')
      g.roundRect(7, 13, 34, 28, 2).fill('#101820')
      g.rect(11, 18, 18, 3).fill(COLORS.mint)
      g.rect(11, 25, 24, 3).fill('#2F5D50')
      g.rect(11, 32, 12, 3).fill(COLORS.mint)
      g.rect(20, 50, 8, 4).fill('#3A3348')
    },
  },
  {
    id: 'shelf',
    x: 66,
    y: 300,
    stand: { x: 156, y: 352 },
    label: 'file shelf',
    tool: 'pulling documents',
    keywords:
      /\b(legal|contract|contracts|doc|docs|document|documents|compliance|risk|clause|terms|policy|nda|agreement)\b/i,
    draw(g) {
      // tall bookshelf, 3 rows of palette-rotated books
      g.rect(0, 0, 56, 84).fill(COLORS.woodLight)
      g.roundRect(0, 0, 56, 84, 2).stroke({ width: 2, color: COLORS.woodShadow })
      const books = [COLORS.coral, COLORS.mint, COLORS.sky, COLORS.lemon, COLORS.lilac, COLORS.peach]
      let bi = 0
      for (let row = 0; row < 3; row++) {
        const ry = 8 + row * 26
        g.rect(4, ry + 18, 48, 4).fill(COLORS.woodShadow)
        for (let bx = 6; bx < 46; bx += 8) {
          g.rect(bx, ry + 4, 6, 14).fill(books[bi++ % books.length])
        }
      }
    },
  },
  {
    id: 'mailbox',
    x: 852,
    y: 306,
    stand: { x: 880, y: 396 },
    label: 'mailbox',
    tool: 'sending messages',
    keywords:
      /\b(whatsapp|message|messages|send|sent|notify|notification|alert|remind|ping|email|outreach)\b/i,
    draw(g) {
      // pole mailbox, flag raised
      g.rect(26, 30, 6, 46).fill(COLORS.woodShadow)
      g.roundRect(6, 6, 46, 26, 8).fill(COLORS.coral)
      g.roundRect(6, 6, 46, 26, 8).stroke({ width: 2, color: '#B23B3B' })
      g.ellipse(52, 19, 5, 13).fill('#B23B3B')
      g.rect(14, -6, 4, 14).fill(COLORS.lemon)
      g.rect(14, -8, 10, 5).fill(COLORS.lemon)
    },
  },
  {
    id: 'board',
    x: 128,
    y: 470,
    stand: { x: 214, y: 512 },
    label: 'task board',
    tool: 'updating the board',
    keywords:
      /\b(briefing|brief|report|digest|summary|plan|planning|strategy|roadmap|todo|tasks?|campaign|schedule)\b/i,
    draw(g) {
      // corkboard with sticky notes
      g.rect(0, 0, 72, 54).fill(COLORS.woodDark)
      g.roundRect(0, 0, 72, 54, 2).stroke({ width: 2, color: COLORS.woodShadow })
      g.rect(4, 4, 64, 46).fill('#C9A66B')
      const notes = [COLORS.lemon, COLORS.sky, COLORS.coral]
      let ni = 0
      for (let row = 0; row < 2; row++)
        for (let col = 0; col < 3; col++) {
          g.rect(9 + col * 20, 9 + row * 20, 13, 13).fill(notes[ni++ % notes.length])
        }
      g.rect(8, 54, 6, 14).fill(COLORS.woodShadow)
      g.rect(58, 54, 6, 14).fill(COLORS.woodShadow)
    },
  },
  {
    id: 'meeting',
    x: 826,
    y: 470,
    stand: { x: 862, y: 440 },
    label: 'meeting table',
    tool: 'in a deal meeting',
    keywords:
      /\b(pricing|price|deal|deals|negotiat\w*|pitch|proposal|quote|discount|onboard\w*|client meeting)\b/i,
    draw(g) {
      // round table, chairs, gold folder on top
      g.circle(36, 64, 26).fill(COLORS.woodLight)
      g.circle(36, 64, 26).stroke({ width: 2, color: COLORS.woodShadow })
      g.circle(36, 64, 17).fill(COLORS.paper)
      g.roundRect(26, 58, 20, 13, 2).fill(COLORS.gold)
      g.rect(26, 61, 20, 3).fill('#F8E28A')
      g.roundRect(-2, 56, 12, 16, 3).fill(COLORS.maroonDeep)
      g.roundRect(62, 56, 12, 16, 3).fill(COLORS.maroonDeep)
    },
  },
]

export function pickStation(summary) {
  if (!summary) return null
  return STATIONS.find((s) => s.keywords.test(summary)) || null
}

export function artifactFor(stationId) {
  return (
    {
      portal: 'globe',
      terminal: 'term',
      shelf: 'paper',
      mailbox: 'mail',
      board: 'check',
      meeting: 'deal',
    }[stationId] || 'paper'
  )
}

// Artifact token carried above the avatar's hands (DESIGN.md §8.8).
export function drawArtifact(g, kind) {
  g.clear()
  if (kind === 'globe') {
    g.circle(0, 0, 6).fill(COLORS.sky)
    g.circle(0, 0, 6).stroke({ width: 1, color: COLORS.ink })
    g.ellipse(0, 0, 3, 6).stroke({ width: 1, color: '#FFFFFF' })
  } else if (kind === 'term') {
    g.rect(-5, -5, 10, 10).fill(COLORS.ink)
    g.moveTo(-3, -2).lineTo(-1, 0).lineTo(-3, 2).stroke({ width: 1, color: COLORS.mint })
    g.rect(0, 2, 3, 1).fill(COLORS.mint)
  } else if (kind === 'mail') {
    g.rect(-6, -4, 12, 9).fill(COLORS.gold)
    g.moveTo(-6, -4).lineTo(0, 2).lineTo(6, -4).stroke({ width: 1, color: COLORS.maroonDeep })
  } else if (kind === 'check') {
    g.rect(-5, -6, 10, 12).fill(COLORS.paper)
    g.rect(-5, -6, 10, 12).stroke({ width: 1, color: COLORS.ink })
    for (let i = 0; i < 3; i++) g.rect(-3, -3 + i * 3, 6, 1).fill(COLORS.textSecondary)
  } else if (kind === 'deal') {
    g.rect(-4, -4, 8, 8).fill(COLORS.lemon)
    g.rect(-4, -4, 8, 8).stroke({ width: 1, color: COLORS.ink })
  } else {
    // folded paper
    g.rect(-4, -6, 9, 12).fill('#FFFDF5')
    g.rect(-4, -6, 9, 12).stroke({ width: 1, color: COLORS.ink })
    g.rect(-2, -2, 5, 1).fill(COLORS.textSecondary)
    g.rect(-2, 1, 5, 1).fill(COLORS.textSecondary)
  }
}

// Static office decor: plants, water cooler, welcome mat.
export function drawDecor(world) {
  const d = new Graphics()
  const plant = (x, y, s = 1) => {
    d.rect(x - 8 * s, y - 6 * s, 16 * s, 12 * s).fill('#B0623F')
    d.rect(x - 8 * s, y - 6 * s, 16 * s, 12 * s).stroke({ width: 2, color: '#8A4A30' })
    d.circle(x - 5 * s, y - 12 * s, 6 * s).fill(COLORS.mint)
    d.circle(x + 5 * s, y - 13 * s, 7 * s).fill('#57B96A')
    d.circle(x, y - 18 * s, 6 * s).fill(COLORS.mint)
  }
  plant(255, 62, 0.8)
  plant(706, 58, 0.8)
  plant(935, 210, 0.9)
  plant(28, 205, 0.9)
  plant(935, 420, 0.8)

  // water cooler next to the task board
  d.rect(96, 520, 14, 26).fill('#DDE7EE')
  d.rect(96, 520, 14, 26).stroke({ width: 2, color: '#9FB2BF' })
  d.roundRect(93, 504, 20, 18, 5).fill('#BFE3F5')
  d.roundRect(93, 504, 20, 18, 5).stroke({ width: 2, color: '#8FC4DE' })

  // welcome mat bottom-center
  d.rect(430, 538, 100, 14).fill('#C9803A')
  d.rect(430, 538, 100, 14).stroke({ width: 2, color: '#8A5423' })

  // conference table (center of the room — the Chief gathers the crew here)
  const tx = 480, ty = 330
  // chairs around it
  const chair = (cx, cy) => {
    d.roundRect(cx - 7, cy - 6, 14, 12, 3).fill(COLORS.maroonDeep)
    d.roundRect(cx - 7, cy - 6, 14, 4, 2).fill('#8A1F31')
  }
  chair(tx - 46, ty + 8)
  chair(tx + 46, ty + 8)
  chair(tx, ty + 40)
  chair(tx - 30, ty - 26)
  chair(tx + 30, ty - 26)
  // oval table
  d.circle(tx, ty, 34).fill(COLORS.woodLight)
  d.circle(tx, ty, 34).stroke({ width: 3, color: COLORS.woodShadow })
  d.circle(tx, ty, 24).fill(COLORS.paper)
  // gold folder + coffee cups on top
  d.roundRect(tx - 10, ty - 6, 20, 12, 2).fill(COLORS.gold)
  d.rect(tx - 10, ty - 2, 20, 3).fill('#F8E28A')
  d.circle(tx - 22, ty + 8, 4).fill('#FFFFFF')
  d.circle(tx - 22, ty + 8, 3).fill('#6B4A2B')
  d.circle(tx + 24, ty - 4, 4).fill('#FFFFFF')
  d.circle(tx + 24, ty - 4, 3).fill('#6B4A2B')

  world.addChildAt(d, 1) // above floor tiles, below actors
}
