// Procedural pixel-art portraits — professional dress per job role.
// Technique: hash the agent id for skin/hair, then pick an OUTFIT by role
// so each agent looks like they belong to that department (suit, blazer,
// vest, lab-coat style, etc.). Painted onto an offscreen canvas (scaled 4x).

import { COLORS } from './tokens.js'

function hashCode(str) {
  let h = 2166136261
  for (let i = 0; i < str.length; i++) {
    h ^= str.charCodeAt(i)
    h = Math.imul(h, 16777619)
  }
  return h >>> 0
}

const SKIN_TONES = ['#E8B98F', '#D9A06F', '#B97A50', '#8D5A33', '#F1C9A5']
const HAIR_COLORS = ['#2C221B', '#4A3728', '#6B4A2F', '#1A1423', '#7A5230', '#A8763E']

// Role -> outfit palette + style. Each outfit = {suit, shirt, tie, style}
// style: 'exec' (full suit+tie), 'blazer' (blazer+shirt), 'vest', 'coat', 'casual'
const ROLE_OUTFITS = {
  // Chief of Staff — executive maroon suit, gold tie
  top_agent: { suit: '#6E1423', shirt: '#FBF3E0', tie: '#F4D35E', style: 'exec' },
  // Sales — sharp blue blazer
  sales_agent: { suit: '#2F4B7C', shirt: '#FFFFFF', tie: '#E2574C', style: 'blazer' },
  // Legal — dark charcoal suit, deep red tie
  legal_agent: { suit: '#2B2B33', shirt: '#F4F4F4', tie: '#7A1F2B', style: 'exec' },
  // Finance — navy vest + tie
  finance_agent: { suit: '#1F3A5F', shirt: '#EDEDED', tie: '#3FA7A0', style: 'vest' },
  // Negotiation — burgundy blazer
  negotiation_agent: { suit: '#6B2737', shirt: '#FFFFFF', tie: '#D8A24A', style: 'blazer' },
  // Strategy — green blazer
  strategy_agent: { suit: '#3C6E47', shirt: '#F2F2F2', tie: '#C9A227', style: 'blazer' },
  // Market Research — teal coat (analyst look)
  market_research_agent: { suit: '#2C7A78', shirt: '#FFFFFF', tie: '#E0E0E0', style: 'coat' },
  // Briefing — purple blazer
  briefing_agent: { suit: '#5B4B8A', shirt: '#F4F0FA', tie: '#C0A0E0', style: 'blazer' },
  // Refinement — coral blazer
  refinement_agent: { suit: '#C25B4E', shirt: '#FFF6F2', tie: '#F4D35E', style: 'blazer' },
  // Onboarding — friendly sky-blue coat
  onboarding_agent: { suit: '#3A6EA5', shirt: '#FFFFFF', tie: '#9BC4E8', style: 'coat' },
  // Default fallback
  _default: { suit: '#546170', shirt: '#F0F0F0', tie: '#9AA7B4', style: 'blazer' },
}

function hairStyle(variant, x, y) {
  const top = y === 2
  const upper = y === 3
  const mid = y >= 4 && y <= 6
  switch (variant % 5) {
    case 0: // full crop
      return top || upper || (mid && x >= 5 && x <= 16)
    case 1: // side part
      return top || (upper && x <= 14) || (y === 4 && x <= 6)
    case 2: // center spike
      return top || (upper && x >= 6 && x <= 15)
    case 3: // long hair
      return top || upper || mid
    default: // bald + beard hint
      return y === 7 && x >= 7 && x <= 14
  }
}

export function makeAvatarTexture(agent, scale = 4, withLegs = true) {
  const W = 22
  const H = withLegs ? 30 : 24
  const canvas = document.createElement('canvas')
  canvas.width = W * scale
  canvas.height = H * scale
  const ctx = canvas.getContext('2d')
  ctx.imageSmoothingEnabled = false

  const h = hashCode(agent.agent_id || agent.name || 'agent')
  const skin = SKIN_TONES[h % SKIN_TONES.length]
  const hair = HAIR_COLORS[(h >> 3) % HAIR_COLORS.length]

  const key = (agent.agent_id || '').replace('_agent', '_agent')
  const outfit = ROLE_OUTFITS[agent.agent_id] || ROLE_OUTFITS._default
  const suit = agent.accent_alt && agent.agent_id === 'top_agent' ? '#6E1423' : outfit.suit
  const shirt = outfit.shirt
  const tie = outfit.tie

  const P = (x, y, w, hh, color) => {
    ctx.fillStyle = color
    ctx.fillRect(x * scale, y * scale, w * scale, hh * scale)
  }

  // outline silhouette
  P(2, 1, W - 4, H - 2, COLORS.ink)

  // head
  P(4, 3, 14, 9, skin)
  // hair
  const hairVariant = h >> 5
  for (let y = 1; y <= 8; y++)
    for (let x = 3; x < W - 3; x++)
      if (hairStyle(hairVariant, x, y)) P(x, y - 1, 1, 1, hair)

  // eyes
  P(8, 7, 2, 2, COLORS.ink)
  P(12, 7, 2, 2, COLORS.ink)

  // ---- professional torso ----
  // shirt base
  P(5, 13, 12, 10, shirt)
  // suit jacket / blazer shoulders
  P(4, 13, 3, 9, suit) // left lapel block
  P(15, 13, 3, 9, suit) // right lapel block
  // open jacket showing shirt in the middle
  P(9, 13, 4, 10, shirt)
  // collar (V neck)
  P(8, 13, 1, 2, suit)
  P(13, 13, 1, 2, suit)
  // tie down the center
  P(10, 15, 2, 6, tie)
  P(10, 15, 2, 1, suit) // knot
  // arms (suit sleeves)
  P(3, 13, 2, 8, suit)
  P(17, 13, 2, 8, suit)
  // hands
  P(3, 21, 2, 2, skin)
  P(17, 21, 2, 2, skin)

  // style extras
  if (outfit.style === 'exec') {
    // full suit: jacket closes over shirt lower down
    P(5, 21, 12, 2, suit)
  } else if (outfit.style === 'vest') {
    // vest: suit sides + vest front
    P(6, 19, 10, 4, suit)
  } else if (outfit.style === 'coat') {
    // analyst coat: white-ish coat over shirt
    P(4, 13, 14, 9, shirt)
    P(4, 13, 2, 9, suit)
    P(16, 13, 2, 9, suit)
    P(10, 15, 2, 6, tie)
  }

  // legs / base
  if (withLegs) {
    P(6, 23, 4, 5, COLORS.outfitBase)
    P(12, 23, 4, 5, COLORS.outfitBase)
    P(6, 28, 4, 1, COLORS.ink)
    P(12, 28, 4, 1, COLORS.ink)
  }

  return canvas
}
