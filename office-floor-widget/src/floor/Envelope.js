// Envelope-flying-between-desks — visual pattern ported from munder-difflin's
// MessageEnvelope.ts: quadratic arc, easeInOutCubic progress, fade in/out,
// rotation bob, and an arrival burst ring. Pure Pixi, no Electron/IPC.

import { Container, Graphics } from 'pixi.js'
import { COLORS } from './tokens.js'

function easeInOutCubic(t) {
  return t < 0.5 ? 4 * t * t * t : 1 - Math.pow(-2 * t + 2, 3) / 2
}

export class Envelope {
  constructor(from, to, onArrive) {
    this.view = new Container()
    this.from = from
    this.to = to
    this.t = 0 // 0..1
    this.duration = Math.max(0.7, Math.min(1.6, dist(from, to) / 260)) // seconds
    this.onArrive = onArrive
    this.done = false

    // paper: gold rectangle with a maroon flap + wax dot (brand pair)
    const g = new Graphics()
    g.rect(-9, -6, 18, 12).fill(COLORS.gold)
    g.rect(-9, -6, 18, 5).fill('#F8E28A')
    g.moveTo(-9, -6).lineTo(0, 2).lineTo(9, -6).stroke({ width: 2, color: COLORS.maroonDeep })
    g.circle(0, 3, 2).fill(COLORS.maroonDeep)
    g.stroke({ width: 1, color: COLORS.ink })
    this.view.addChild(g)

    this.burst = new Graphics()
    this.view.addChild(this.burst)
  }

  update(dt) {
    if (this.done) return
    this.t += dt / this.duration
    if (this.t >= 1) {
      this.t = 1
      this.done = true
      drawBurst(this.burst)
      if (this.onArrive) this.onArrive()
      return
    }
    const e = easeInOutCubic(this.t)
    const { x, y } = arcPoint(this.from, this.to, e)
    this.view.x = x
    this.view.y = y
    this.view.alpha = this.t < 0.08 ? this.t / 0.08 : this.t > 0.88 ? (1 - this.t) / 0.12 : 1
    this.view.rotation = Math.sin(e * Math.PI * 4) * 0.25
    this.view.scale.set(1 - 0.15 * Math.sin(e * Math.PI))
  }
}

function dist(a, b) {
  return Math.hypot(b.x - a.x, b.y - a.y)
}

// Quadratic bezier with a control point raised above the midpoint.
export function arcPoint(a, b, t) {
  const midX = (a.x + b.x) / 2
  const midY = (a.y + b.y) / 2
  const d = dist(a, b)
  const cx = midX
  const cy = midY - (d * 0.22 + 40)
  const u = 1 - t
  return {
    x: u * u * a.x + 2 * u * t * cx + t * t * b.x,
    y: u * u * a.y + 2 * u * t * cy + t * t * b.y,
  }
}

function drawBurst(g) {
  g.clear()
  for (let i = 0; i < 8; i++) {
    const ang = (i / 8) * Math.PI * 2
    g.moveTo(Math.cos(ang) * 6, Math.sin(ang) * 6)
      .lineTo(Math.cos(ang) * 14, Math.sin(ang) * 14)
      .stroke({ width: 2, color: COLORS.gold })
  }
}
