"""Company Brain Dashboard — two interfaces, one brain.

/tab/chat    — chat with the Top Agent (real Team runs)
/tab/floor   — Munder-Difflin-style office floor: 11 agent desks,
               avatars light up on real work, envelopes fly on real
               delegations (fed by Team member_responses).

Mounted onto the same FastAPI app as the WhatsApp webhook, which is
mounted onto AgentOS — everything lives on one port (:8000).
"""
import logging
import time

from fastapi import APIRouter
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel

logger = logging.getLogger("company-brain.dashboard")

router = APIRouter(prefix="/dashboard", include_in_schema=False)

# ---- activity ledger (real runs only) -------------------------------------
ACTIVITY: list[dict] = []          # newest last
MAX_ACTIVITY = 200


def record_activity(agent: str, action: str, detail: str = "") -> dict:
    entry = {
        "agent": agent,
        "action": action,
        "detail": detail[:220],
        "ts": time.time(),
    }
    ACTIVITY.append(entry)
    if len(ACTIVITY) > MAX_ACTIVITY:
        del ACTIVITY[: len(ACTIVITY) - MAX_ACTIVITY]
    return entry


def get_team():
    from app.main import team  # late import: avoid circulars at module load

    return team


class ChatRequest(BaseModel):
    message: str


@router.get("/api/activity")
async def activity():
    cutoff = time.time() - 600
    recent = [a for a in ACTIVITY if a["ts"] >= cutoff]
    busy = {}
    for a in recent:
        busy[a["agent"]] = max(busy.get(a["agent"], 0), a["ts"])
    return {"activity": recent[-60:], "busy_until": busy}


@router.post("/api/chat")
async def chat(req: ChatRequest):
    try:
        team = get_team()
        record_activity("Top Agent", "received", req.message)
        response = await team.arun(
            input=req.message,
            session_id="dashboard-floor",
        )
        content = getattr(response, "content", None) or ""
        members = []
        for m in getattr(response, "member_responses", None) or []:
            name = getattr(m, "agent_name", None) or getattr(m, "name", "") or "Specialist"
            members.append(name)
            record_activity(name, "delegated work", str(getattr(m, "content", ""))[:180])
        record_activity("Top Agent", "replied", str(content)[:180])
        return {
            "reply": str(content),
            "members": members,
        }
    except Exception as exc:
        logger.exception("dashboard chat error")
        msg = str(exc)
        if "429" in msg:
            friendly = (
                "[quota] Gemini's free-tier limit is reached right now. "
                "It resets within minutes/hours — or add a GROQ_API_KEY "
                "(free at console.groq.com) to spread the load."
            )
        else:
            friendly = f"[error] {exc}"
        return JSONResponse(status_code=200, content={"reply": friendly, "members": []})


@router.get("")
@router.get("/", response_class=HTMLResponse)
async def dashboard():
    return PAGE


PAGE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Company Brain — Floor</title>
<style>
  :root{
    --bg:#101418; --floor:#1a2027; --panel:#161b22; --border:#30363d;
    --text:#e6edf3; --muted:#8b949e; --accent:#d9a441; --accent2:#7c95ff; --user:#1f6feb;
  }
  *{box-sizing:border-box;margin:0}
  body{background:var(--bg);color:var(--text);height:100vh;display:flex;flex-direction:column;
       font-family:ui-sans-serif,system-ui,'Segoe UI',sans-serif}
  header{padding:12px 20px;border-bottom:1px solid var(--border);background:var(--panel);
         display:flex;align-items:center;gap:12px}
  .logo{width:34px;height:34px;border-radius:9px;display:grid;place-items:center;font-size:18px;
        background:linear-gradient(135deg,var(--accent),#8a5a19)}
  h1{font-size:16px} small{color:var(--muted);display:block;margin-top:2px}
  nav{margin-left:auto;display:flex;gap:8px}
  nav button{background:transparent;border:1px solid var(--border);color:var(--text);
             padding:8px 18px;border-radius:9px;font-size:13px;font-weight:600;cursor:pointer}
  nav button.active{background:var(--accent);border-color:var(--accent);color:#141414}
  main{flex:1;display:flex;flex-direction:column;overflow:hidden}

  /* ---------- FLOOR ---------- */
  #floorWrap{flex:1;display:none;flex-direction:column;overflow:hidden}
  #floorWrap.on{display:flex}
  canvas#floor{flex:1;width:100%;background:var(--floor)}
  #ledger{height:150px;border-top:1px solid var(--border);background:var(--panel);
          overflow-y:auto;padding:8px 14px;font-size:12.5px;line-height:1.7}
  #ledger b{color:var(--accent)} #ledger .t{color:var(--muted)}

  /* ---------- CHAT ---------- */
  #chatWrap{flex:1;display:none;flex-direction:column;overflow:hidden}
  #chatWrap.on{display:flex}
  #chat{flex:1;overflow-y:auto;padding:22px;display:flex;flex-direction:column;gap:12px}
  .msg{max-width:76%;padding:11px 15px;border-radius:13px;line-height:1.55;white-space:pre-wrap;word-wrap:break-word}
  .msg.user{align-self:flex-end;background:var(--user);border-bottom-right-radius:4px}
  .msg.brain{align-self:flex-start;background:var(--panel);border:1px solid var(--border);border-bottom-left-radius:4px}
  .typing{align-self:flex-start;color:var(--muted);font-size:13px;padding:10px 15px}
  form{display:flex;gap:10px;padding:14px 18px;border-top:1px solid var(--border);background:var(--panel)}
  input{flex:1;background:var(--bg);border:1px solid var(--border);color:var(--text);
        padding:12px 15px;border-radius:10px;font-size:14px;outline:none}
  input:focus{border-color:var(--accent2)}
  button.send{background:var(--user);color:#fff;border:none;padding:0 22px;border-radius:10px;
              font-size:14px;font-weight:600;cursor:pointer}
  button.send:disabled{opacity:.5}
</style>
</head>
<body>
<header>
  <div class="logo">🧠</div>
  <div><h1>Company Brain</h1><small>the office floor · 11 agents · one Chief of Staff</small></div>
  <nav>
    <button id="navFloor" class="active">🏢 Floor</button>
    <button id="navChat">💬 Talk to Top Agent</button>
  </nav>
</header>

<main>
  <section id="floorWrap" class="on">
    <canvas id="floor"></canvas>
    <div id="ledger"><span class="t">Activity log — waiting for the first task…</span></div>
  </section>

  <section id="chatWrap">
    <div id="chat"><div class="msg brain">Chief of Staff online. Ask me anything — I'll route it to the right specialist. Try: "brief me", "new lead: …", "I have an idea".</div></div>
    <form id="f">
      <input id="i" placeholder="Message your Chief of Staff…" autocomplete="off" autofocus>
      <button class="send" id="b">Send</button>
    </form>
  </section>
</main>

<script>
/* ---------------- tabs ---------------- */
const floorWrap=document.getElementById('floorWrap'), chatWrap=document.getElementById('chatWrap');
const navFloor=document.getElementById('navFloor'), navChat=document.getElementById('navChat');
function show(which){
  const floor = which==='floor';
  floorWrap.classList.toggle('on',floor); chatWrap.classList.toggle('on',!floor);
  navFloor.classList.toggle('active',floor); navChat.classList.toggle('active',!floor);
  if(floor) resize();
}
navFloor.onclick=()=>show('floor'); navChat.onclick=()=>show('chat');

/* ---------------- floor ---------------- */
const AGENTS=[
  {id:'top',   name:'Top Agent',      emoji:'🧑‍✈️'},
  {id:'sales', name:'Sales',          emoji:'📈'},
  {id:'onb',   name:'Onboarding',     emoji:'📋'},
  {id:'neg',   name:'Negotiation',    emoji:'🤝'},
  {id:'fin',   name:'Finance',        emoji:'💰'},
  {id:'legal', name:'Legal',          emoji:'⚖️'},
  {id:'idea',  name:'Idea',           emoji:'💡'},
  {id:'ref',   name:'Refinement',     emoji:'✨'},
  {id:'mkt',   name:'Market Research',emoji:'🔍'},
  {id:'strat', name:'Strategy',       emoji:'🎯'},
  {id:'brief', name:'Briefing',       emoji:'☀️'},
];
const canvas=document.getElementById('floor'), ctx=canvas.getContext('2d');
let desks=[], envelopes=[], busyUntil={}, lastLedgerCount=-1;

function layout(){
  const W=canvas.width, H=canvas.height;
  // Top Agent big desk center-top
  desks=[{a:AGENTS[0],x:W*0.5,y:H*0.24,big:true}];
  // 10 specialists in two rows of 5 below
  const rest=AGENTS.slice(1);
  rest.forEach((a,i)=>{
    const row=Math.floor(i/5), col=i%5;
    desks.push({a,x:W*(0.14+col*0.18),y:H*(0.55+row*0.26)});
  });
}
function resize(){
  const r=canvas.getBoundingClientRect();
  canvas.width=r.devicePixelRatio? r.clientWidth*devicePixelRatio : r.clientWidth;
  canvas.height=window.innerHeight-260;
  canvas.width=r.clientWidth;
  layout();
}
window.addEventListener('resize',resize);

function draw(ts){
  const W=canvas.width,H=canvas.height;
  ctx.fillStyle='#1a2027';ctx.fillRect(0,0,W,H);
  // carpet
  ctx.fillStyle='rgba(217,164,65,0.05)';
  ctx.beginPath();ctx.ellipse(W/2,H*0.28,W*0.2,H*0.14,0,0,7);ctx.fill();
  const now=Date.now()/1000;
  for(const d of desks){
    const busy=(busyUntil[d.a.name]||0)>now-20 || (busyUntil['Top Agent']||0)>now-20 && d.big;
    // desk
    ctx.fillStyle=d.big?'#3b3323':'#232b33';
    const dw=d.big?150:110, dh=d.big?70:52;
    roundRect(d.x-dw/2,d.y-dh/2,dw,dh,10);ctx.fill();
    ctx.strokeStyle=busy?'#d9a441':'#30363d';ctx.lineWidth=busy?3:1.5;ctx.stroke();
    if(busy){ // glow pulse
      const p=(Math.sin(now*4)+1)/2;
      ctx.strokeStyle=`rgba(217,164,65,${0.25+p*0.35})`;ctx.lineWidth=6;ctx.stroke();
    }
    // avatar
    ctx.font=`${d.big?46:32}px serif`;ctx.textAlign='center';ctx.textBaseline='middle';
    ctx.fillText(d.a.emoji,d.x,d.y-dh/2-(d.big?30:22));
    // name
    ctx.font=`${d.big?14:11}px system-ui`;ctx.fillStyle='#8b949e';
    ctx.fillText(d.a.name,d.x,d.y+dh/2+14);
  }
  // envelopes
  envelopes=envelopes.filter(e=>now-e.t0<1.4);
  for(const e of envelopes){
    const p=(now-e.t0)/1.4, x=e.x1+(e.x2-e.x1)*p, y=e.y1+(e.y2-e.y1)*p-Math.sin(p*Math.PI)*40;
    ctx.font='22px serif';ctx.fillText('✉️',x,y);
  }
  requestAnimationFrame(draw);
}
function roundRect(x,y,w,h,r){ctx.beginPath();ctx.moveTo(x+r,y);ctx.arcTo(x+w,y,x+w,y+h,r);
  ctx.arcTo(x+w,y+h,x,y+h,r);ctx.arcTo(x,y+h,x,y,r);ctx.arcTo(x,y,x+w,y,r);ctx.closePath();}
function fly(fromName,toName){
  const f=desks.find(d=>d.a.name===fromName)||desks[0], t=desks.find(d=>d.a.name===toName)||desks[0];
  envelopes.push({x1:f.x,y1:f.y,x2:t.x,y2:t.y,t0:Date.now()/1000});
}
requestAnimationFrame(draw); resize();

/* ---------------- activity polling ---------------- */
const ledger=document.getElementById('ledger');
async function poll(){
  try{
    const r=await fetch('/dashboard/api/activity'); const d=await r.json();
    busyUntil=d.busy_until||{};
    if((d.activity||[]).length!==lastLedgerCount){
      lastLedgerCount=(d.activity||[]).length;
      ledger.innerHTML=d.activity.slice().reverse().map(a=>{
        const t=new Date(a.ts*1000).toLocaleTimeString();
        return `<span class="t">${t}</span> — <b>${esc(a.agent)}</b> ${esc(a.action)}${a.detail?': '+esc(a.detail):''}`;
      }).join('<br>')||'<span class="t">Activity log — waiting…</span>';
    }
  }catch(e){}
  setTimeout(poll,3000);
}
function esc(s){const d=document.createElement('div');d.textContent=String(s);return d.innerHTML;}
poll();

/* ---------------- chat ---------------- */
const chatEl=document.getElementById('chat'), form=document.getElementById('f'),
      input=document.getElementById('i'), btn=document.getElementById('b');
form.addEventListener('submit', async e=>{
  e.preventDefault();
  const text=input.value.trim(); if(!text||btn.disabled)return;
  add(text,'user'); input.value='';
  const t=document.createElement('div');t.className='typing';t.textContent='Chief of Staff is routing ';
  chatEl.appendChild(t);chatEl.scrollTop=chatEl.scrollHeight;btn.disabled=true;
  try{
    const r=await fetch('/dashboard/api/chat',{method:'POST',
      headers:{'Content-Type':'application/json'},body:JSON.stringify({message:text})});
    const d=await r.json(); t.remove(); add(d.reply||'[no response]','brain');
    // animate the delegation on the floor
    busyUntil['Top Agent']=Date.now()/1000;
    (d.members||[]).forEach(m=>{fly('Top Agent',m);busyUntil[m]=Date.now()/1000;
      setTimeout(()=>fly(m,'Top Agent'),700);});
    show('floor');                       // flip to the floor to watch the work
    setTimeout(()=>{},0);
  }catch(err){t.remove();add('[connection error]','brain');}
  btn.disabled=false;input.focus();
});
function add(text,who){
  const el=document.createElement('div');el.className='msg '+who;el.textContent=text;
  chatEl.appendChild(el);chatEl.scrollTop=chatEl.scrollHeight;
}
</script>
</body>
</html>"""
