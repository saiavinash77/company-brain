// Procedural pixel-art portraits — technique extracted from munder-difflin's
// portraitArt.ts: hash the agent id into palette slots (hair/skin/outfit) and
// paint a tiny sprite buffer, no external asset pack required.
//
// We paint one 22x30-pixel sprite per agent onto an offscreen canvas (scaled
// 4x for crispness) and hand it to Pixi as a texture.

import { COLORS } from './tokens.js'

function hashCode(str) {
  let h = 2166136261
  for (let i = 0; i < str.length; i++) {
    h ^= str.charCodeAt(i)
    h = Math.imul(h, 16777619)
  }
  return h >>> 0
}

const SKIN_TONES = ['#E8B98F', '#D9A06F', '#B97A50', '#8D5A33']
const HAIR_COLORS = ['#4A3728', '#2C221B', '#6B4A2F', '#1A1423', '#7A5230']

// 5 hair variants as bitmask rows over the head area (x: 3..18, y: 2..8)
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

export function makeAvatarTexture(agent, scale = 4) {
  const W = 22
  const H = 30
  const canvas = document.createElement('canvas')
  canvas.width = W * scale
  canvas.height = H * scale
  const ctx = canvas.getContext('2d')
  ctx.imageSmoothingEnabled = false

  const h = hashCode(agent.agent_id || agent.name || 'agent')
  const skin = SKIN_TONES[h % SKIN_TONES.length]
  const hair = HAIR_COLORS[(h >> 3) % HAIR_COLORS.length]
  const outfit = agent.accent || COLORS.sky
  const accentAlt = agent.accent_alt || COLORS.gold

  const P = (x, y, w, hh, color) => {
    ctx.fillStyle = color
    ctx.fillRect(x * scale, y * scale, w * scale, hh * scale)
  }

  // ink outline silhouette (1px border around body box)
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

  // torso (outfit with accent collar stripe)
  P(5, 13, 12, 10, outfit)
  P(5, 13, 12, 2, accentAlt)

  // arms
  P(3, 13, 2, 8, outfit)
  P(17, 13, 2, 8, outfit)
  // hands
  P(3, 21, 2, 2, skin)
  P(17, 21, 2, 2, skin)

  // legs / base
  P(6, 23, 4, 5, COLORS.outfitBase)
  P(12, 23, 4, 5, COLORS.outfitBase)
  // shoes
  P(6, 28, 4, 1, COLORS.ink)
  P(12, 28, 4, 1, COLORS.ink)

  return canvas
}
