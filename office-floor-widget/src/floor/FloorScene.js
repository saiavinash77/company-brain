// Pixi office floor scene: fixed desks from the backend snapshot, procedural
// avatars, state machine (idle-at-desk / walking / working / talking-handoff),
// and envelope flights on real handoff events. Rebuilt from the munder-difflin
// office-scene concepts as a plain web component driven by WebSocket events —
// no Electron, no PTY payloads, no dynamic floor growth.

import { Application, Container, Graphics, Text, Texture, Sprite } from 'pixi.js'
import { COLORS, WORLD, WALK_SPEED } from './tokens.js'
import { makeAvatarTexture } from './portrait.js'
import { Envelope } from './Envelope.js'

const TILE = 32

export class FloorScene {
  constructor(canvas) {
    this.canvas = canvas
    this.app = null
    this.world = null
    this.actors = new Map() // agent_id -> actor
    this.envelopes = []
    this.destroyed = false
  }

  async init() {
    this.app = new Application()
    await this.app.init({
      canvas: this.canvas,
      width: WORLD.width,
      height: WORLD.height,
      backgroundAlpha: 0,
      antialias: false,
      autoDensity: true,
    })
    this.world = new Container()
    this.app.stage.addChild(this.world)
    drawFloor(this.world)
    this.app.ticker.add((ticker) => this.tick(ticker.deltaMS / 1000))
  }

  destroy() {
    this.destroyed = true
    if (this.app) this.app.destroy(false, { children: true })
    this.actors.clear()
  }

  // ---- snapshot / event API ------------------------------------------

  applySnapshot(snapshot) {
    const entries = [...(snapshot.agents || []), ...(snapshot.clients || [])]
    for (const meta of entries) this.ensureActor(meta)
    const ids = new Set(entries.map((e) => e.agent_id))
    for (const [id, actor] of this.actors) if (!ids.has(id)) this.removeActor(id)
  }

  onStateEvent(ev) {
    const actor = this.actors.get(ev.agent_id)
    if (!actor) return
    if (ev.state === 'working') actor.startWorking(ev.task_summary || '')
    else if (ev.state === 'idle') actor.goIdle()
    else if (ev.state === 'handoff') {
      const target = ev.target_agent_id ? this.actors.get(ev.target_agent_id) : null
      if (target) {
        this.spawnEnvelope(actor.deskPoint(), target.deskPoint())
        actor.faceTowards(target.deskPoint())
        target.receiveHandoff()
      }
    }
  }

  spawnEnvelope(fromPt, toPt) {
    const env = new Envelope(fromPt, toPt)
    this.world.addChild(env.view)
    env.view.zIndex = 500
    this.envelopes.push(env)
  }

  ensureActor(meta) {
    if (this.actors.has(meta.agent_id)) {
      this.actors.get(meta.agent_id).updateMeta(meta)
      return
    }
    const actor = new Actor(this.world, meta)
    this.actors.set(meta.agent_id, actor)
  }

  removeActor(agentId) {
    const actor = this.actors.get(agentId)
    if (!actor) return
    actor.destroy()
    this.actors.delete(agentId)
  }

  tick(dt) {
    if (this.destroyed) return
    for (const actor of this.actors.values()) actor.update(dt)
    for (let i = this.envelopes.length - 1; i >= 0; i--) {
      const env = this.envelopes[i]
      env.update(dt)
      if (env.done && env.burstAge > 0.5) {
        this.world.removeChild(env.view)
        env.view.destroy({ children: true })
        this.envelopes.splice(i, 1)
      } else if (env.done) {
        env.burstAge += dt
      }
    }
  }
}

// ----------------------------------------------------------------------

function drawFloor(world) {
  const g = new Graphics()
  // checkerboard grass
  for (let y = 0; y * TILE < WORLD.height; y++) {
    for (let x = 0; x * TILE < WORLD.width; x++) {
      const color = (x + y) % 2 === 0 ? COLORS.grassLight : COLORS.grassDark
      g.rect(x * TILE, y * TILE, TILE, TILE).fill(color)
    }
  }
  // back wall
  g.rect(0, 0, WORLD.width, 26).fill(COLORS.wallTop)
  g.rect(0, 26, WORLD.width, 6).fill(COLORS.wallBottom)
  world.addChild(g)

  // company sign on the wall
  const sign = new Text({
    text: 'COMPANY BRAIN HQ',
    style: {
      fontFamily: '"Press Start 2P", monospace',
      fontSize: 11,
      fill: COLORS.maroonDeep,
      align: 'center',
    },
  })
  sign.anchor.set(0.5)
  sign.position.set(WORLD.width / 2, 13)
  world.addChild(sign)
}

class Actor {
  constructor(world, meta) {
    this.world = world
    this.meta = meta
    this.state = meta.state || 'idle'
    this.summary = meta.task_summary || ''
    this.facing = 1

    this.root = new Container()
    this.root.eventMode = 'none'

    // avatar sprite (pre-rendered procedural portrait)
    const tex = Texture.from(makeAvatarTexture(meta))
    tex.source.scaleMode = 'nearest' // crisp pixels
    this.sprite = new Sprite(tex)
    this.sprite.scale.set(0.9)
    this.sprite.anchor.set(0.5, 1)

    // desk drawn behind/below avatar
    this.deskG = new Graphics()

    // nameplate
    this.label = new Text({
      text: shortName(meta.name),
      style: {
        fontFamily: '"Pixelify Sans", monospace',
        fontSize: 13,
        fontWeight: '700',
        fill: COLORS.textPrimary,
        stroke: { color: COLORS.paper, width: 3 },
      },
    })
    this.label.anchor.set(0.5, 0)

    // status bubble (working dots / zzz)
    this.bubble = new Container()
    this.bubbleBg = new Graphics()
    this.bubbleDots = new Graphics()
    this.bubble.addChild(this.bubbleBg, this.bubbleDots)

    this.root.addChild(this.deskG, this.sprite, this.label, this.bubble)
    this.root.position.set(meta.desk.x, meta.desk.y)
    this.root.zIndex = Math.round(meta.desk.y)
    world.sortableChildren = true
    world.addChild(this.root)

    // position: stand just above own desk
    this.homeX = meta.desk.x
    this.homeY = meta.desk.y - 14
    this.x = this.homeX
    this.y = this.homeY
    this.targetX = this.homeX
    this.targetY = this.homeY

    this.animT = 0
    this.talkUntil = 0
    this.drawDesk()
    this.redrawBubble()
  }

  deskPoint() {
    return { x: this.meta.desk.x, y: this.meta.desk.y - 10 }
  }

  updateMeta(meta) {
    this.meta = { ...this.meta, ...meta }
    if ((meta.state || 'idle') !== this.state) {
      if (meta.state === 'working') this.startWorking(meta.task_summary || '')
      else if (meta.state === 'handoff') this.state = 'handoff'
      else this.goIdle(true)
    } else if (meta.task_summary && meta.task_summary !== this.summary) {
      this.summary = meta.task_summary
    }
  }

  startWorking(summary) {
    this.state = 'working'
    if (summary !== undefined) this.summary = summary
    // walk to desk first if away
    if (Math.hypot(this.x - this.homeX, this.y - this.homeY) > 4) {
      this.targetX = this.homeX
      this.targetY = this.homeY
    }
    this.redrawBubble()
  }

  goIdle(snap = false) {
    this.state = 'idle'
    this.summary = ''
    this.targetX = this.homeX
    this.targetY = this.homeY
    if (snap) {
      this.x = this.homeX
      this.y = this.homeY
    }
    this.redrawBubble()
  }

  faceTowards(pt) {
    this.facing = pt.x < this.x ? -1 : 1
    this.sprite.scale.x = Math.abs(this.sprite.scale.x) * this.facing
  }

  receiveHandoff() {
    this.talkUntil = performance.now() + 1400
    this.state = 'handoff'
    this.redrawBubble()
  }

  update(dt) {
    this.animT += dt

    // walking toward target at WALK_SPEED
    const dx = this.targetX - this.x
    const dy = this.targetY - this.y
    const d = Math.hypot(dx, dy)
    const moving = d > 2
    if (moving) {
      const step = Math.min(d, WALK_SPEED * dt)
      this.x += (dx / d) * step
      this.y += (dy / d) * step
      if (Math.abs(dx) > 1) {
        this.facing = dx < 0 ? -1 : 1
        this.sprite.scale.x = Math.abs(this.sprite.scale.x) * this.facing
      }
    }

    // idle bob / walk bob / work bounce
    let bob = 0
    if (moving) bob = Math.round(Math.abs(Math.sin(this.animT * 8)) * 2)
    else if (this.state === 'working') bob = Math.sin(this.animT * 5) * 0.6
    else bob = Math.sin(this.animT * 2.2) * 0.8

    // root is anchored at the desk point; avatar floats relative to it
    this.sprite.position.set(0, this.y - this.meta.desk.y + bob)
    this.label.position.set(0, this.y - this.meta.desk.y + 4)

    // handoff timeout back to previous visual state
    if (this.state === 'handoff' && performance.now() > this.talkUntil) {
      this.state = this.summary ? 'working' : 'idle'
      this.redrawBubble()
    }

    // working typing dots animation
    if (this.state === 'working') {
      const frame = Math.floor(this.animT * 3) % 3
      this.bubbleDots.clear()
      for (let i = 0; i < 3; i++) {
        const on = i <= frame
        this.bubbleDots.circle(-6 + i * 6, 7, 2.4).fill(on ? COLORS.ink : '#C9BBA6')
      }
    }
  }

  redrawBubble() {
    this.bubbleBg.clear()
    this.bubbleDots.clear()
    if (this.state === 'idle' && !this.summary) {
      this.bubble.visible = false
      return
    }
    this.bubble.visible = true
    const color =
      this.state === 'handoff'
        ? COLORS.statusHandoff
        : this.state === 'working'
          ? COLORS.statusWorking
          : COLORS.statusIdle
    // hard-offset pixel panel per DESIGN.md §4.1
    this.bubbleBg.roundRect(-16, -34, 32, 20, 4).fill(color)
    this.bubbleBg.rect(-12, -15, 24, 3).fill(color)
    this.bubbleBg.stroke({ width: 2, color: COLORS.ink })
    // tail points down to avatar
    this.bubbleBg.moveTo(-4, -15).lineTo(0, -10).lineTo(4, -15).fill(color)
  }

  drawDesk() {
    const g = this.deskG
    const accent = this.meta.accent || COLORS.sky
    // monitor
    g.roundRect(-14, 6, 28, 18, 3).fill(COLORS.woodLight)
    g.roundRect(-14, 6, 28, 18, 3).stroke({ width: 2, color: COLORS.woodShadow })
    g.roundRect(-10, 9, 20, 11, 2).fill(accent)
    g.rect(-2, 24, 4, 4).fill(COLORS.woodShadow)
    // keyboard strip
    g.rect(-9, 30, 18, 3).fill(COLORS.woodDark)
    // temporary client desks get dashed outline feel via lighter wood
    if (this.meta.temporary) g.rect(-14, 6, 28, 2).fill('#EED9B0')
  }

  destroy() {
    this.world.removeChild(this.root)
    this.root.destroy({ children: true })
  }
}

function shortName(name) {
  if (!name) return '?'
  const clean = name.replace(' Agent', '')
  return clean.length > 18 ? clean.slice(0, 17) + '…' : clean
}
