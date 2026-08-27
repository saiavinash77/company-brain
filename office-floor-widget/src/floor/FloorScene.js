// Pixi office floor scene — Company Brain HQ.
//
// Ported from munder-difflin's office scene concepts: animated walk-cycle
// legs, task-keyword station routing (walk → tool bubble at the station →
// carry artifact back), speech bubbles with live task text, success sparkles,
// clickable actors, and envelope flights on real handoff events.
//
// Driven entirely by backend WebSocket events; no mock data.

import { Application, Container, Graphics, Text, Texture, Sprite } from 'pixi.js'
import { COLORS, WORLD, WALK_SPEED } from './tokens.js'
import { makeAvatarTexture } from './portrait.js'
import { Envelope } from './Envelope.js'
import { STATIONS, pickStation, artifactFor, drawArtifact, drawDecor } from './stations.js'

// Conference table world position — keep in sync with the backend floor_config.
const CONFERENCE_TABLE = { x: 480, y: 330 }

const TILE = 32

export class FloorScene {
  constructor(canvas, callbacks = {}) {
    this.canvas = canvas
    this.app = null
    this.world = null
    this.actors = new Map() // agent_id -> Actor
    this.envelopes = []
    this.sparkles = []
    this.destroyed = false
    this.callbacks = callbacks // { onSelect(meta), onToast({fromName,toName}), onMoment(text) }
  }

  setCallbacks(cb) {
    this.callbacks = cb || {}
  }

  async init() {
    // Build a fresh Application per attempt — reusing one instance across
    // retries throws "already initialized" in Pixi v8 and leaves a blank canvas.
    for (const preference of ['canvas', 'webgl']) {
      try {
        this.app = new Application()
        await this.app.init({
          canvas: this.canvas,
          width: WORLD.width,
          height: WORLD.height,
          backgroundAlpha: 0,
          antialias: false,
          autoDensity: false,
          preference,
          failIfMajorPerformanceCaveat: false,
          powerPreference: 'low-power',
        })
        console.log(`[floor] pixi init OK with ${preference}`)
        break
      } catch (err) {
        console.warn(`[floor] pixi init with ${preference} failed:`, err?.message || err)
        try {
          this.app?.destroy(true)
        } catch {}
        this.app = null
        if (preference === 'webgl') {
          this.initError = String(err?.message || err)
          throw err
        }
      }
    }
    if (!this.app) {
      this.initError = 'pixi failed to initialize'
      throw new Error('pixi failed to initialize')
    }
    this.world = new Container()
    this.app.stage.addChild(this.world)
    drawFloor(this.world)
    drawDecor(this.world)
    for (const st of STATIONS) {
      const g = new Graphics()
      st.draw(g)
      g.position.set(st.x, st.y)
      g.zIndex = Math.round(st.y)
      const lbl = new Text({
        text: st.label,
        style: {
          fontFamily: '"Pixelify Sans", monospace',
          fontSize: 11,
          fill: '#5C4A38',
          stroke: { color: COLORS.paper, width: 3 },
        },
      })
      lbl.anchor.set(0.5, 1)
      lbl.position.set(st.x + 30, st.y - 6)
      lbl.zIndex = Math.round(st.y) + 1
      this.world.addChild(g, lbl)
    }
    this.world.sortableChildren = true
    this.app.ticker.add((ticker) => {
      try {
        this.tick(ticker.deltaMS / 1000)
      } catch (e) {
        console.error('[floor] tick error', e)
      }
    })
  }

  destroy() {
    this.destroyed = true
    if (this.app) this.app.destroy(false, { children: true })
    this.actors.clear()
  }

  // ---- snapshot / event API ------------------------------------------

  applySnapshot(snapshot) {
    const entries = [...(snapshot.agents || []), ...(snapshot.clients || [])]
    for (const meta of entries) {
      try {
        this.ensureActor(meta)
      } catch (e) {
        console.error('[floor] failed to create actor', meta?.agent_id, e)
      }
    }
    const ids = new Set(entries.map((e) => e.agent_id))
    for (const [id, actor] of this.actors) if (!ids.has(id)) this.removeActor(id)
  }

  onStateEvent(ev) {
    const actor = this.actors.get(ev.agent_id)
    if (!actor) return
    if (ev.state === 'working') actor.startWorking(ev.task_summary || '')
    else if (ev.state === 'idle') actor.goIdle()
    else if (ev.state === 'blocked') actor.setBlocked(true)
    else if (ev.state === 'handoff') {
      const target = ev.target_agent_id ? this.actors.get(ev.target_agent_id) : null
      if (target) {
        actor.faceTowards(target.deskPoint())
        // BOSS DIRECTS: Chief walks to the conference table; specialist
        // receives the envelope at the table too — a real gathering.
        const boss = ev.agent_id === 'top_agent'
        const table = CONFERENCE_TABLE
        if (boss) {
          actor.summonTo(table.x, table.y - 40)
          target.summonTo(table.x + 70, table.y - 10)
        }
        target.receiveHandoff()
        this.spawnEnvelope(actor.deskPoint(), boss ? { x: table.x + 70, y: table.y - 24 } : target.deskPoint(), {
          fromName: actor.meta.name,
          toName: target.meta.name,
        })
        this.callbacks.onToast?.({
          fromName: actor.meta.name,
          toName: target.meta.name,
          summary: ev.task_summary || 'delegation',
          kind: 'handoff',
        })
      }
    }
  }

  spawnEnvelope(fromPt, toPt, meta = {}) {
    const env = new Envelope(fromPt, toPt, () => {
      this.callbacks.onToast?.(meta)
    })
    this.world.addChild(env.view)
    env.view.zIndex = 500
    this.envelopes.push(env)
  }

  ensureActor(meta) {
    if (this.actors.has(meta.agent_id)) {
      this.actors.get(meta.agent_id).updateMeta(meta)
      return
    }
    const actor = new Actor(this.world, meta, {
      onSelect: (m) => this.callbacks.onSelect?.(m),
      onSparkle: (pt, color) => this.spawnSparkle(pt, color),
    })
    this.actors.set(meta.agent_id, actor)
  }

  removeActor(agentId) {
    const actor = this.actors.get(agentId)
    if (!actor) return
    actor.destroy()
    this.actors.delete(agentId)
  }

  spawnSparkle(pt, color = COLORS.statusSuccess) {
    const g = new Graphics()
    const view = new Container()
    view.addChild(g)
    view.position.set(pt.x, pt.y)
    view.zIndex = 600
    this.world.addChild(view)
    this.sparkles.push({ view, g, t: 0, color })
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

    for (let i = this.sparkles.length - 1; i >= 0; i--) {
      const sp = this.sparkles[i]
      sp.t += dt
      sp.g.clear()
      const r = 4 + sp.t * 26
      for (let k = 0; k < 6; k++) {
        const a = (k / 6) * Math.PI * 2 + sp.t * 2
        sp.g.circle(Math.cos(a) * r, Math.sin(a) * r * 0.6, 2).fill(sp.color)
      }
      sp.view.alpha = Math.max(0, 1 - sp.t / 0.7)
      if (sp.t > 0.7) {
        this.world.removeChild(sp.view)
        sp.view.destroy({ children: true })
        this.sparkles.splice(i, 1)
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

// 4-frame leg cycle per DESIGN.md §8.5 — frames [idle, stepA, idle, stepB].
// Drawn in portrait-pixel units (1 unit = 4 canvas px); the container shares
// the sprite's 0.9 scale and is anchored at the hip line.
function drawLegsFrame(g, frame) {
  g.clear()
  const LEG = COLORS.outfitBase
  const SHOE = COLORS.ink
  if (frame === 1) {
    // step-A: left foot raised
    g.rect(-16, 0, 14, 18).fill(LEG)
    g.rect(-17, 16, 16, 4).fill(SHOE)
    g.rect(2, 0, 14, 24).fill(LEG)
    g.rect(1, 22, 16, 4).fill(SHOE)
  } else if (frame === 3) {
    // step-B: right foot raised
    g.rect(-16, 0, 14, 24).fill(LEG)
    g.rect(-17, 22, 16, 4).fill(SHOE)
    g.rect(2, 0, 14, 18).fill(LEG)
    g.rect(1, 16, 16, 4).fill(SHOE)
  } else {
    // idle stance
    g.rect(-16, 0, 14, 24).fill(LEG)
    g.rect(-17, 22, 16, 4).fill(SHOE)
    g.rect(2, 0, 14, 24).fill(LEG)
    g.rect(1, 22, 16, 4).fill(SHOE)
  }
}

class Actor {
  constructor(world, meta, hooks = {}) {
    this.world = world
    this.hooks = hooks
    this.meta = meta
    this.state = meta.state || 'idle'
    this.summary = meta.task_summary || ''
    this.facing = 1

    this.root = new Container()

    // avatar sprite WITHOUT baked legs — legs animate separately below hips
    const tex = Texture.from(makeAvatarTexture(meta, 4, false))
    tex.source.scaleMode = 'nearest'
    this.sprite = new Sprite(tex)
    this.sprite.scale.set(0.9)
    this.sprite.anchor.set(0.5, 1)

    // animated legs (own container sharing the sprite scale)
    this.legs = new Container()
    this.legsG = new Graphics()
    this.legs.addChild(this.legsG)
    this.legs.scale.set(0.9)

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

    // speech/status bubble
    this.bubble = new Container()
    this.bubbleBg = new Graphics()
    this.bubbleDots = new Graphics()
    this.bubbleText = null
    this.bubble.addChild(this.bubbleBg, this.bubbleDots)

    // artifact carried in hands while returning from a station
    this.artifact = new Graphics()
    this.carrying = null

    // blocked "!" overlay
    this.blockedMark = new Text({
      text: '!',
      style: {
        fontFamily: '"Press Start 2P", monospace',
        fontSize: 12,
        fill: COLORS.statusBlocked,
        stroke: { color: COLORS.paper, width: 3 },
      },
    })
    this.blockedMark.visible = false
    this.blockedMark.anchor.set(0.5)

    this.root.addChild(
      this.deskG,
      this.sprite,
      this.legs,
      this.label,
      this.blockedMark,
      this.bubble,
      this.artifact,
    )
    this.root.position.set(meta.desk.x, meta.desk.y)
    this.root.zIndex = Math.round(meta.desk.y)
    world.sortableChildren = true
    world.addChild(this.root)

    // click-to-select
    this.root.eventMode = 'static'
    this.root.cursor = 'pointer'
    this.root.on('pointertap', () => this.hooks.onSelect?.({ ...this.meta }))

    this.homeX = meta.desk.x
    this.homeY = meta.desk.y - 14
    this.x = this.homeX
    this.y = this.homeY

    this.route = [] // [{x,y}, ...] remaining waypoints
    this.stationId = null
    this.arrivedAtStation = false
    this.lastStationId = null
    this.showingTool = false
    this.toolUntil = 0
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
      else if (meta.state === 'handoff') {
        this.state = 'handoff'
        this.redrawBubble()
      } else if (meta.state === 'blocked') this.setBlocked(true)
      else this.goIdle(true)
    } else if (meta.task_summary && meta.task_summary !== this.summary) {
      this.summary = meta.task_summary
      this.redrawBubble()
    }
  }

  startWorking(summary) {
    this.state = 'working'
    if (summary !== undefined) this.summary = summary
    this.blockedMark.visible = false
    this.carrying = null
    this.artifact.clear()

    const station = pickStation(summary)
    this.stationId = station ? station.id : null
    this.arrivedAtStation = false
    this.route = station
      ? [{ x: station.stand.x, y: station.stand.y }]
      : [{ x: this.homeX, y: this.homeY }]
    this.redrawBubble()
  }

  goIdle(snap = false) {
    const finishedAtStation = this.arrivedAtStation && !!this.lastStationId
    const hadTask = !!this.summary
    this.state = 'idle'
    this.summary = ''
    this.stationId = null
    this.arrivedAtStation = false
    this.showingTool = false
    this.blockedMark.visible = false

    if (finishedAtStation) {
      // walk home carrying what the station produced (DESIGN.md §8.8)
      this.carrying = artifactFor(this.lastStationId)
      drawArtifact(this.artifact, this.carrying)
      this.route = [{ x: this.homeX, y: this.homeY }]
    } else if (hadTask) {
      // finished at own desk — success sparkle
      this.hooks.onSparkle?.(
        { x: this.meta.desk.x, y: this.meta.desk.y - 20 },
        COLORS.statusSuccess,
      )
      this.route = [{ x: this.homeX, y: this.homeY }]
    } else if (!snap && Math.hypot(this.x - this.homeX, this.y - this.homeY) > 6) {
      // interrupted mid-walk — head back to the desk
      this.route = [{ x: this.homeX, y: this.homeY }]
    } else {
      this.route = []
    }
    if (snap) {
      this.x = this.homeX
      this.y = this.homeY
      this.route = []
    }
    this.redrawBubble()
  }

  setBlocked(on) {
    this.blockedMark.visible = !!on
    if (on) this.state = 'blocked'
    this.redrawBubble()
  }

  faceTowards(pt) {
    this.facing = pt.x < this.x ? -1 : 1
    this.sprite.scale.x = Math.abs(this.sprite.scale.x) * this.facing
  }

  /** Walk to a summoned point (conference table), linger, then return to desk. */
  summonTo(x, y) {
    this.route = [{ x, y }]
    this.summonedAt = { x, y }
    if (!this.state || this.state === 'idle') {
      this.state = 'handoff'
      this.redrawBubble()
    }
  }

  receiveHandoff() {
    this.talkUntil = performance.now() + 1400
    this.state = 'handoff'
    this.redrawBubble()
  }

  update(dt) {
    this.animT += dt

    // tool chip expiry → fall back to summary/dots bubble
    if (this.showingTool && performance.now() > this.toolUntil) {
      this.showingTool = false
      this.redrawBubble()
    }

    // waypoint following
    let moving = false
    if (this.route.length > 0) {
      const wp = this.route[0]
      const dx = wp.x - this.x
      const dy = wp.y - this.y
      const d = Math.hypot(dx, dy)
      if (d <= 2.5) {
        this.route.shift()
        this.onArrive()
      } else {
        const step = Math.min(d, WALK_SPEED * dt)
        this.x += (dx / d) * step
        this.y += (dy / d) * step
        if (Math.abs(dx) > 1) {
          this.facing = dx < 0 ? -1 : 1
          this.sprite.scale.x = Math.abs(this.sprite.scale.x) * this.facing
        }
        moving = true
      }
    }

    // bob styles: walking bob / working bounce / idle breathe
    let bob = 0
    if (moving) bob = Math.round(Math.abs(Math.sin(this.animT * 8)) * 2)
    else if (this.state === 'working' && !this.stationId) bob = Math.sin(this.animT * 5) * 0.6
    else bob = Math.sin(this.animT * 2.2) * 0.8

    const relY = this.y - this.meta.desk.y + bob
    this.sprite.position.set(0, relY)
    this.legs.position.set(0, relY + 1)
    this.label.position.set(0, relY + 26)
    if (this.carrying) this.artifact.position.set(0, relY - 40)
    this.blockedMark.position.set(0, relY - 66)

    // legs animate only while moving
    const frame = moving ? [0, 1, 0, 3][Math.floor(this.animT * 8) % 4] : 0
    drawLegsFrame(this.legsG, frame)

    // typing dots when there is no summary text
    if ((this.state === 'working' || this.state === 'handoff') && !this.summary && !moving) {
      const f = Math.floor(this.animT * 3) % 3
      this.bubbleDots.clear()
      for (let i = 0; i < 3; i++) {
        const on = i <= f
        this.bubbleDots.circle(-6 + i * 6, -26, 2.4).fill(on ? COLORS.ink : '#C9BBA6')
      }
    } else {
      this.bubbleDots.clear()
    }
  }

  onArrive() {
    if (this.state === 'working' && this.stationId && !this.arrivedAtStation) {
      this.arrivedAtStation = true
      this.lastStationId = this.stationId
      // show the tool chip for a moment ("running data queries" etc.)
      this.showingTool = true
      this.toolUntil = performance.now() + 2800
      this.redrawBubble()
    }
    if (this.summonedAt && Math.hypot(this.x - this.summonedAt.x, this.y - this.summonedAt.y) < 6) {
      // arrived at the conference table — linger, then head home
      const here = this.summonedAt
      this.summonedAt = null
      setTimeout(() => {
        if (this.state === 'handoff') {
          this.route = [{ x: this.homeX, y: this.homeY }]
          this.state = 'idle'
          this.redrawBubble()
        }
      }, 2600)
    }
    if (this.carrying) {
      // artifact dropped onto the desk — sparkle
      this.carrying = null
      this.artifact.clear()
      this.hooks.onSparkle?.(
        { x: this.meta.desk.x, y: this.meta.desk.y - 20 },
        COLORS.statusSuccess,
      )
    }
  }

  redrawBubble() {
    this.bubbleBg.clear()
    this.bubbleDots.clear()
    if (this.bubbleText) {
      this.bubble.removeChild(this.bubbleText)
      this.bubbleText.destroy()
      this.bubbleText = null
    }

    const toolActive =
      this.showingTool && performance.now() < this.toolUntil && !!this.lastStationId
    const showBubble =
      this.state === 'working' ||
      this.state === 'handoff' ||
      this.state === 'blocked' ||
      toolActive
    if (!showBubble) {
      this.bubble.visible = false
      return
    }
    this.bubble.visible = true

    const color =
      this.state === 'handoff'
        ? COLORS.statusHandoff
        : this.state === 'blocked'
          ? COLORS.statusBlocked
          : this.state === 'working'
            ? COLORS.statusWorking
            : COLORS.statusIdle

    let text = null
    if (toolActive && !this.summary) {
      text = STATIONS.find((s) => s.id === this.lastStationId)?.tool || null
    } else if (this.summary) {
      text = this.summary
    }

    if (text) {
      const wrapped = wrapText(text, 24, 2)
      this.bubbleText = new Text({
        text: wrapped,
        style: {
          fontFamily: '"Pixelify Sans", monospace',
          fontSize: 12,
          lineHeight: 14,
          fill: COLORS.ink,
        },
      })
      this.bubbleText.anchor.set(0.5, 1)
      const w = Math.max(52, this.bubbleText.width + 16)
      const h = this.bubbleText.height + 12
      this.bubbleBg.roundRect(-w / 2, -h - 18, w, h, 4).fill(color)
      this.bubbleBg.roundRect(-w / 2, -h - 18, w, h, 4).stroke({ width: 2, color: COLORS.ink })
      this.bubbleBg.moveTo(-4, -19).lineTo(0, -11).lineTo(4, -19).fill(color)
      this.bubble.addChild(this.bubbleText)
      this.bubbleText.position.set(0, -23)
    } else {
      this.bubbleBg.roundRect(-16, -36, 32, 20, 4).fill(color)
      this.bubbleBg.roundRect(-16, -36, 32, 20, 4).stroke({ width: 2, color: COLORS.ink })
      this.bubbleBg.moveTo(-4, -17).lineTo(0, -10).lineTo(4, -17).fill(color)
    }
  }

  drawDesk() {
    const g = this.deskG
    const accent = this.meta.accent || COLORS.sky
    if (this.meta.agent_id === 'top_agent') {
      // BOSS CABIN — larger executive desk, gold trim, nameplate (maroon/gold)
      g.roundRect(-30, 2, 60, 26, 4).fill(COLORS.maroonDeep)
      g.roundRect(-30, 2, 60, 26, 4).stroke({ width: 3, color: COLORS.gold })
      g.roundRect(-24, 8, 48, 12, 2).fill(COLORS.woodLight)
      // dual monitors
      g.roundRect(-24, -14, 20, 15, 2).fill('#3A3348')
      g.roundRect(-21, -11, 14, 9, 1).fill(COLORS.gold)
      g.roundRect(4, -14, 20, 15, 2).fill('#3A3348')
      g.roundRect(7, -11, 14, 9, 1).fill(COLORS.mint)
      // nameplate: THE BOSS
      g.roundRect(-16, 32, 32, 10, 2).fill(COLORS.gold)
    } else {
      // monitor
      g.roundRect(-14, 6, 28, 18, 3).fill(COLORS.woodLight)
      g.roundRect(-14, 6, 28, 18, 3).stroke({ width: 2, color: COLORS.woodShadow })
      g.roundRect(-10, 9, 20, 11, 2).fill(accent)
      g.rect(-2, 24, 4, 4).fill(COLORS.woodShadow)
      // keyboard strip
      g.rect(-9, 30, 18, 3).fill(COLORS.woodDark)
      // temporary client desks get lighter wood top edge
      if (this.meta.temporary) g.rect(-14, 6, 28, 2).fill('#EED9B0')
    }
  }

  destroy() {
    this.world.removeChild(this.root)
    this.root.destroy({ children: true })
  }
}

function wrapText(text, maxChars, maxLines) {
  const words = String(text).split(/\s+/)
  const lines = []
  let cur = ''
  for (const w of words) {
    if ((cur + ' ' + w).trim().length > maxChars) {
      lines.push(cur.trim())
      cur = w
      if (lines.length === maxLines) break
    } else {
      cur = (cur + ' ' + w).trim()
    }
  }
  if (lines.length < maxLines && cur) lines.push(cur.trim())
  if (lines.length === maxLines) {
    const consumed = lines.join(' ').length
    if (consumed < String(text).trim().length) {
      lines[maxLines - 1] = lines[maxLines - 1].slice(0, Math.max(0, maxChars - 1)) + '…'
    }
  }
  return lines.filter(Boolean).join('\n')
}

function shortName(name) {
  if (!name) return '?'
  const clean = name.replace(' Agent', '')
  return clean.length > 18 ? clean.slice(0, 17) + '…' : clean
}
