"""Office Floor UI — Munder-Difflin-style visualization of the Company Brain.

Adapted to our architecture: agents are the 11 specialists + Top Agent,
activity comes from real AgentOS team-run responses (member_responses),
and chat goes ONLY through the Top Agent (AGENTS.md rule #2).

Served at /floor by the same server as AgentOS.
"""

FLOOR_PAGE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Company Brain — Office Floor</title>
<style>
  :root {
    --bg:#14100e; --floor1:#2b2320; --floor2:#332a26; --wall:#4a3830;
    --panel:#1d1714; --border:#4a3a32; --text:#f0e6d8; --muted:#a08d7c;
    --accent:#d9a441; --hot:#e2574c; --ok:#7fb069; --desk:#5a4638;
  }
  *{box-sizing:border-box;margin:0;padding:0}
  body{background:var(--bg);color:var(--text);font-family:'Segoe UI',system-ui,sans-serif;height:100vh;display:flex;flex-direction:column;overflow:hidden}
  header{display:flex;align-items:center;gap:12px;padding:10px 18px;background:var(--panel);border-bottom:2px solid var(--border)}
  header .logo{width:34px;height:34px;border-radius:8px;display:grid;place-items:center;background:linear-gradient(135deg,#d9a441,#8a5a24);font-size:18px}
  header h1{font-size:15px} header span{font-size:11px;color:var(--muted);display:block}
  header .links{margin-left:auto;font-size:12px}
  header .links a{color:var(--accent);text-decoration:none;margin-left:14px;border:1px solid var(--border);padding:6px 12px;border-radius:8px}
  header .links a:hover{background:var(--desk)}
  #main{flex:1;display:flex;min-height:0}
  /* ---- floor ---- */
  #floorWrap{flex:1;position:relative;overflow:auto}
  canvas{display:block;image-rendering:pixelated}
  /* ---- sidebar ---- */
  #side{width:360px;display:flex;flex-direction:column;border-left:2px solid var(--border);background:var(--panel)}
  #tabs{display:flex;border-bottom:2px solid var(--border)}
  #tabs button{flex:1;padding:10px;background:none;border:none;color:var(--muted);font-weight:600;cursor:pointer;font-size:13px}
  #tabs button.on{color:var(--text);box-shadow:inset 0 -3px var(--accent)}
  #log{flex:1;overflow-y:auto;padding:10px;font-size:12px;line-height:1.5}
  .entry{padding:6px 8px;border-left:3px solid var(--desk);margin-bottom:6px;background:rgba(255,255,255,.03);border-radius:0 6px 6px 0}
  .entry b{color:var(--accent)} .entry .t{color:var(--muted);font-size:10px}
  #chatPane{height:45%;display:flex;flex-direction:column;border-top:2px solid var(--border)}
  #msgs{flex:1;overflow-y:auto;padding:10px;display:flex;flex-direction:column;gap:8px;font-size:13px}
  .m{max-width:92%;padding:8px 12px;border-radius:10px;line-height:1.45;white-space:pre-wrap;word-break:break-word}
  .m.you{align-self:flex-end;background:#35502c}
  .m.cos{align-self:flex-start;background:var(--desk);border:1px solid var(--border);max-width:95%;max-height:220px;overflow-y:auto}
  .m.sys{align-self:center;color:var(--muted);font-size:11px}
  form{display:flex;gap:8px;padding:10px;border-top:1px solid var(--border)}
  input{flex:1;background:var(--bg);border:1px solid var(--border);color:var(--text);padding:10px 12px;border-radius:8px;outline:none;font-size:13px}
  input:focus{border-color:var(--accent)}
  button.send{background:var(--accent);border:none;color:#241a08;font-weight:700;padding:0 18px;border-radius:8px;cursor:pointer}
  button.send:disabled{opacity:.5}
  /* tooltip */
  #tip{position:fixed;pointer-events:none;background:#000d;border:1px solid var(--border);padding:8px 12px;border-radius:8px;font-size:12px;display:none;z-index:9;max-width:260px;line-height:1.5}
  #tip b{color:var(--accent)}
</style>
</head>
<body>
<header>
  <div class="logo">🧠</div>
  <div><h1>Company Brain — Office Floor</h1><span>your AI chief-of-staff &amp; her crew, live</span></div>
  <nav class="links"><a href="/" target="_blank">AgentOS API</a><a href="/docs" target="_blank">API Docs</a></nav>
</header>
<div id="main">
  <div id="floorWrap"><canvas id="cv"></canvas></div>
  <div id="side">
    <div id="tabs">
      <button id="tabLog" class="on">Activity</button>
      <button id="tabChat">Talk to Chief</button>
    </div>
    <div id="log"></div>
    <div id="chatPane" style="display:none">
      <div id="msgs"><div class="m sys">You talk ONLY to the Top Agent (Chief of Staff). She delegates.</div></div>
      <form id="cf"><input id="ci" placeholder="e.g. new lead: … / brief me / I have an idea" autocomplete="off"><button class="send" id="cb">Send</button></form>
    </div>
  </div>
</div>
<div id="tip"></div>
<script>
/* ---------------- roster (matches AGENTS.md) ---------------- */
const ROSTER = [
  {id:'top',        name:'Top Agent',        role:'Chief of Staff — routes everything', emoji:'👩‍💼', cabin:true},
  {id:'sales',      name:'Sales Agent',      role:'Lead qualification & scoring',       emoji:'📈'},
  {id:'onboarding', name:'Onboarding Agent', role:'New client setup',                   emoji:'🧾'},
  {id:'negotiation',name:'Negotiation Agent',role:'Pricing & deals (owner approval!)',  emoji:'🤝'},
  {id:'finance',    name:'Finance Agent',    role:'Invoices, payments, cashflow',       emoji:'💰'},
  {id:'legal',      name:'Legal Agent',      role:'Contract review & risk flags',       emoji:'⚖️'},
  {id:'idea',       name:'Idea Agent',       role:'Captures raw ideas',                 emoji:'💡'},
  {id:'refinement', name:'Refinement Agent', role:'Ideas → pitches & briefs',           emoji:'✍️'},
  {id:'research',   name:'Market Research',  role:'Competitors & trends',               emoji:'🔭'},
  {id:'strategy',   name:'Strategy Agent',   role:'Campaigns & growth roadmaps',        emoji:'🗺️'},
  {id:'briefing',   name:'Briefing Agent',   role:'Daily/weekly summaries',             emoji:'📋'},
];
const TS=110, GAP=26, MX=60, MY=90;            // tile size, gaps, margins
const W = MX*2 + TS*4 + GAP*3;
let H = MY + TS*3 + 140;
const cv=document.getElementById('cv'), ctx=cv.getContext('2d');
cv.width=W; cv.height=H;

/* desks: top-agent cabin center-top, others grid below */
const desks={};
ROSTER.forEach((a,i)=>{
  if(a.cabin){ desks[a.id]={x:W/2-TS/2, y:MY-40}; }
  else{
    const k=i-1, row=Math.floor(k/5), col=k%5;
    const rowN = row===0?5:5;
    const totalW = TS*5+GAP*4;
    desks[a.id]={x:(W-totalW)/2 + col*(TS+GAP), y:MY+70+row*(TS+GAP)};
  }
});
H = MY+70+2*(TS+GAP)+TS+80; cv.height=H;

let busy={}, glow={}, envs=[];
function draw(t){
  // floor
  for(let y=0;y<H;y+=24)for(let x=0;x<W;x+=24){
    ctx.fillStyle=((x+y)/24)%2?'var(--floor1)':'#2b2320';
    ctx.fillStyle=((x+y)/24)%2?'#2b2320':'#332a26'; ctx.fillRect(x,y,24,24);
  }
  // wall
  ctx.fillStyle='#4a3830'; ctx.fillRect(0,0,W,44);
  ctx.fillStyle='#241a12'; ctx.fillRect(0,42,W,4);
  ctx.font='16px monospace'; ctx.fillStyle='#d9a441'; ctx.textAlign='center';
  ctx.fillText('🏢  COMPANY BRAIN INC.', W/2, 28);
  // desks
  for(const a of ROSTER){
    const d=desks[a.id], hot=glow[a.id]>performance.now(), bs=busy[a.id];
    ctx.save();
    if(a.cabin){ ctx.strokeStyle='#d9a441'; ctx.lineWidth=3; ctx.strokeRect(d.x-10,d.y-26,TS+20,TS+36);
      ctx.font='11px sans-serif'; ctx.fillStyle='#d9a441'; ctx.fillText('CHIEF', d.x+TS/2, d.y-32);}
    // desk
    ctx.fillStyle='#5a4638'; rr(d.x,d.y+34,TS,26,4);
    ctx.strokeStyle='#33261c'; ctx.lineWidth=2; ctx.strokeRect(d.x,d.y+34,TS,26);
    // avatar
    if(hot||bs){ ctx.shadowColor='#ffd76a'; ctx.shadowBlur=22; }
    ctx.font='40px serif'; ctx.fillText(a.emoji, d.x+TS/2, d.y+30);
    ctx.shadowBlur=0;
    // name plate
    ctx.font='10px sans-serif'; ctx.fillStyle='#f0e6d8';
    ctx.fillText(a.name.replace(' Agent',''), d.x+TS/2, d.y+74);
    ctx.fillStyle=bs?'#e2574c':'#7fb069';
    ctx.beginPath(); ctx.arc(d.x+TS-8, d.y+40, 4+(bs?(t/150%1<.5?2:0):0), 0, 7); ctx.fill();
    ctx.restore();
  }
  // envelopes
  envs=envs.filter(e=>{
    e.p+=0.025; if(e.p>=1){ if(e.to)glow[e.to]=performance.now()+2500; return false;}
    const A=desks[e.from],B=desks[e.to];
    const x=A.x+TS/2+(B.x-A.x)*e.p, y=A.y+20+(B.y-A.y)*e.p - Math.sin(e.p*Math.PI)*70;
    ctx.font='22px serif'; ctx.fillText('✉️',x,y); return true;
  });
  requestAnimationFrame(draw);
}
function rr(x,y,w,h,r){ctx.beginPath();ctx.roundRect(x,y,w,h,r);ctx.fill();}
requestAnimationFrame(draw);

/* tooltip */
const tip=document.getElementById('tip');
cv.addEventListener('mousemove',ev=>{
  const r=cv.getBoundingClientRect(), x=(ev.clientX-r.left), y=(ev.clientY-r.top);
  for(const a of ROSTER){const d=desks[a.id];
    if(x>d.x&&x<d.x+TS&&y>d.y-30&&y<d.y+80){
      tip.style.display='block'; tip.style.left=ev.clientX+14+'px'; tip.style.top=ev.clientY+10+'px';
      tip.innerHTML=`<b>${a.name}</b><br>${a.role}<br>Status: ${busy[a.id]?'working…':'idle'}`;
      return; }}
  tip.style.display='none';
});

/* ---------------- activity log ---------------- */
const logEl=document.getElementById('log');
function log(html){const e=document.createElement('div');e.className='entry';
  e.innerHTML=`<span class="t">${new Date().toLocaleTimeString()}</span><br>${html}`;
  logEl.prepend(e);}

/* ---------------- tabs & chat ---------------- */
const tabL=document.getElementById('tabLog'), tabC=document.getElementById('tabChat'),
      logPane=document.getElementById('log'), chatPane=document.getElementById('chatPane');
tabL.onclick=()=>{tabL.classList.add('on');tabC.classList.remove('on');logPane.style.display='block';chatPane.style.display='none';};
tabC.onclick=()=>{tabC.classList.add('on');tabL.classList.remove('on');chatPane.style.display='flex';logPane.style.display='none';};

const msgs=document.getElementById('msgs'), cf=document.getElementById('cf'),
      ci=document.getElementById('ci'), cb=document.getElementById('cb');
cf.onsubmit=async e=>{
  e.preventDefault(); const text=ci.value.trim(); if(!text||cb.disabled)return;
  add(text,'you'); ci.value='';
  busy['top']=true; cb.disabled=true;
  const sys=add('Chief is thinking…','sys');
  try{
    const fd=new FormData(); fd.append('message',text); fd.append('stream','false');
    const r=await fetch('/teams/company-brain/runs',{method:'POST',body:fd});
    const d=await r.json();
    sys.remove();
    // REAL delegation data → animate
    const members=(d.member_responses||[]).map(m=>m.agent_name||'');
    let first=true;
    for(const m of members){
      const a=ROSTER.find(a=>m.toLowerCase().includes(a.name.toLowerCase().replace(' Agent','')) || m===a.name);
      if(a){ if(first){envs.push({from:'top',to:a.id,p:0}); first=false;} else {
          const prev=ROSTER.find(x=>busy[x.id]); envs.push({from:prev?prev.id:'top',to:a.id,p:0);}
        }
        busy[a.id]=true; log(`<b>${a.name}</b> worked on your request`);
        setTimeout(()=>{busy[a.id]=false;},6000);
      }
    }
    if(!members.length) log('<b>Top Agent</b> answered directly');
    await new Promise(res=>setTimeout(res, members.length?1800:400));
    busy['top']=false;
    envs.push({from:members.length?rosterByResponse(members[members.length-1]):'sales',to:'top',p:0});
    setTimeout(()=>add(d.content||'[empty]','cos'), 500);
  }catch(err){ sys.remove(); busy['top']=false; add('[error] '+err.message,'sys'); }
  cb.disabled=false;
};
function rosterByResponse(name){
  const a=ROSTER.find(a=>name.toLowerCase().includes(a.name.toLowerCase().replace(' Agent','')));
  return a?a.id:'top';
}
function add(text,who){const el=document.createElement('div');el.className='m '+who;el.textContent=text;
  msgs.appendChild(el);msgs.scrollTop=msgs.scrollHeight;return el;}

log('<b>Floor opened.</b> 11 specialists at their desks. Chat routes through the Chief.');
['sales','finance','briefing'].forEach((id,i)=>setTimeout(()=>{
  envs.push({from:'top',to:id,p:0}); log('<b>Morning round:</b> Chief checked in with '+ROSTER.find(a=>a.id===id).name);
},800*i+600));
</script>
</body>
</html>"""
