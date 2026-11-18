#!/usr/bin/env python3
"""llama-swap 'Reality' tab: front door on :18080 that proxies llama-swap (:8080) unchanged,
injects one extra sidebar tab, and serves /_reality/ (what is really running on GPUs/ports).
Read-only: never starts/stops anything."""
import json, os, re, subprocess, sys, time, http.client
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import threading, collections
from urllib.parse import urlparse, parse_qs

LISTEN = ("127.0.0.1", 18080)
UPSTREAM = ("127.0.0.1", 8080)
HOP = {"connection", "keep-alive", "proxy-authenticate", "proxy-authorization", "te", "trailers",
       "transfer-encoding", "upgrade", "content-length", "content-encoding"}

def run(cmd, t=6):
    try:
        return subprocess.run(cmd, capture_output=True, text=True, timeout=t).stdout
    except Exception:
        return ""

def health(port):
    try:
        c = http.client.HTTPConnection("127.0.0.1", port, timeout=2)
        c.request("GET", "/health"); r = c.getresponse(); r.read(); c.close()
        return r.status
    except Exception:
        return None

def proc_info(pid):
    try:
        args = open(f"/proc/{pid}/cmdline", "rb").read().split(b"\0")
        args = [a.decode(errors="replace") for a in args if a]
        cg = open(f"/proc/{pid}/cgroup").read().strip().split("/")[-1]
        ppid = int(re.search(r"PPid:\s+(\d+)", open(f"/proc/{pid}/status").read()).group(1))
        started = os.stat(f"/proc/{pid}").st_mtime
    except Exception:
        return None
    def opt(*names):
        for i, a in enumerate(args):
            if a in names and i + 1 < len(args):
                return args[i + 1]
        return None
    return {"pid": pid, "ppid": ppid, "unit": cg if cg.endswith(".service") else None,
            "model_file": opt("-m", "--model"), "alias": opt("--alias", "-a"),
            "port": int(opt("--port") or 0) or None, "cpu_only": opt("--device") == "none" or opt("-ngl", "--n-gpu-layers") == "0",
            "since": started}


def _comm(pid):
    try:
        return open(f"/proc/{pid}/comm").read().strip()
    except Exception:
        return None

def _cmdline(pid):
    try:
        return [a.decode(errors="replace") for a in open(f"/proc/{pid}/cmdline", "rb").read().split(b"\0") if a]
    except Exception:
        return []

def is_basalt_server(pid):
    # BASALT serve process: python3 running serve.server with the engine binary (bin/basalt).
    args = _cmdline(pid)
    return "serve.server" in args and any(a.endswith("/bin/basalt") for a in args)

def is_model_server(pid):
    return _comm(pid) == "llama-server" or is_basalt_server(pid)

def ancestors(pid, depth=12):
    out, cur = [], pid
    for _ in range(depth):
        try:
            cur = int(re.search(r"PPid:\s+(\d+)", open(f"/proc/{cur}/status").read()).group(1))
        except Exception:
            break
        if cur <= 1:
            break
        out.append(cur)
    return out

def attribute_gpu(server_pids, gpu_by_pid):
    # Each GPU compute process counts once, under the model server that is it or one of its ancestors.
    out = {}
    for gp, per_gpu in gpu_by_pid.items():
        owner = gp if gp in server_pids else next((a for a in ancestors(gp) if a in server_pids), None)
        if owner is None:
            continue
        slot = out.setdefault(owner, {})
        for idx, mib in per_gpu.items():
            slot[idx] = slot.get(idx, 0) + mib
    return out

def basalt_health(port):
    try:
        c = http.client.HTTPConnection("127.0.0.1", port, timeout=2)
        c.request("GET", "/health"); r = c.getresponse(); d = json.loads(r.read()); c.close()
        return d if isinstance(d, dict) else None
    except Exception:
        return None

def basalt_last(port):
    # Read-only: BASALT's /v1/status carries the last completed request's timings.
    try:
        c = http.client.HTTPConnection("127.0.0.1", port, timeout=2)
        c.request("GET", "/v1/status"); r = c.getresponse(); d = json.loads(r.read()); c.close()
        return d.get("last_timings") or None
    except Exception:
        return None

def swap_running_ports():
    # llama-swap's own view of running models, keyed by backend port (the proxy URL carries it).
    try:
        c = http.client.HTTPConnection(*UPSTREAM, timeout=3); c.request("GET", "/running")
        running = json.loads(c.getresponse().read()).get("running", [])
    except Exception:
        return None
    out = {}
    for r in running:
        try:
            out[urlparse(r.get("proxy", "")).port] = {"model": r.get("model"), "state": r.get("state")}
        except Exception:
            pass
    return out

def basalt_slot_step(prev, sl, now):
    # One BASALT /slots row -> (new tokens, active seconds, next state). Counts only while decoding.
    if sl.get("state") != "decoding":
        return 0, 0.0, None
    gen = int(sl.get("generated") or 0)
    if prev and prev[0] == "basalt" and now > prev[2]:
        dn = gen - prev[1] if gen >= prev[1] else gen   # counter reset: a new request started
        return max(dn, 0), now - prev[2], ("basalt", gen, now)
    return 0, 0.0, ("basalt", gen, now)

def status():
    gpus = []
    uuid2idx = {}
    for line in run(["nvidia-smi", "--query-gpu=index,uuid,name,memory.used,memory.total,utilization.gpu,power.draw,power.limit,temperature.gpu",
                     "--format=csv,noheader,nounits"]).strip().splitlines():
        p = [x.strip() for x in line.split(",")]
        if len(p) >= 9:
            uuid2idx[p[1]] = int(p[0])
            fl = lambda v: round(float(v), 1) if re.match(r"^[0-9.]+$", v) else None
            gpus.append({"index": int(p[0]), "name": p[2], "used_mib": int(p[3]), "total_mib": int(p[4]), "util": int(p[5]),
                         "power_w": fl(p[6]), "power_limit_w": fl(p[7]), "temp_c": fl(p[8])})
    gpu_mem = {}
    for line in run(["nvidia-smi", "--query-compute-apps=pid,gpu_uuid,used_memory", "--format=csv,noheader,nounits"]).strip().splitlines():
        p = [x.strip() for x in line.split(",")]
        if len(p) >= 3 and p[0].isdigit():
            gpu_mem.setdefault(int(p[0]), {})[uuid2idx.get(p[1], -1)] = int(p[2])
    swap_pid = None
    for pid in filter(str.isdigit, os.listdir("/proc")):
        try:
            if open(f"/proc/{pid}/comm").read().strip() == "llama-swap":
                swap_pid = int(pid); break
        except Exception:
            pass
    servers = []
    swap_map = swap_running_ports() or {}
    infos = {}
    for pid in filter(str.isdigit, os.listdir("/proc")):
        if not is_model_server(int(pid)):
            continue
        i = proc_info(int(pid))
        if i:
            infos[i["pid"]] = i
    attributed = attribute_gpu(set(infos), gpu_mem)
    for pid, i in infos.items():
        basalt = is_basalt_server(pid)
        managed = (i["ppid"] == swap_pid)
        i["backend"] = "basalt" if basalt else "llama.cpp"
        i["owner"] = "llama-swap" if managed else (i["unit"] or "unknown (not llama-swap)")
        i["managed_by_llama_swap"] = managed
        if swap_map.get(i["port"]) and swap_map[i["port"]].get("model"):
            i["alias"] = swap_map[i["port"]]["model"]
        if basalt and i["port"]:
            h = basalt_health(i["port"]) or {}
            rows = get_slots(i["port"]) or []
            decoding = sum(1 for r in rows if r.get("state") == "decoding")
            prefill = sum(1 for r in rows if r.get("state") == "prefill")
            if h.get("loading"):
                state = "loading"
            elif decoding:
                state = "generating"
            elif h.get("loaded"):
                state = "loaded"
            else:
                state = "unknown"
            i["health"] = 200 if h else None
            i["basalt"] = {"state": state, "loaded": h.get("loaded"), "loading": h.get("loading"),
                           "percent": h.get("percent"), "slots_decoding": decoding, "slots_prefill": prefill}
        else:
            i["health"] = health(i["port"]) if i["port"] else None
        i["gpu_mib"] = attributed.get(pid, {})
        i["uptime_s"] = int(time.time() - i["since"])
        servers.append(i)
    try:
        c = http.client.HTTPConnection(*UPSTREAM, timeout=3); c.request("GET", "/running")
        running = json.loads(c.getresponse().read()).get("running", [])
    except Exception:
        running = None
    gpu_users = sum(1 for s in servers if s["gpu_mib"])
    return {"time": time.time(), "gpus": gpus, "servers": servers, "llama_swap_running": running,
            "summary": f"{gpu_users} model server(s) on GPU; llama-swap reports {0 if running is None else len(running)} running"}

SAMPLES = {}      # alias -> deque[(unix_time, tokens_per_second)]
SLOT_STATE = {}   # (port, slot) -> (task_id, n_decoded, time)
SRV_CACHE = {"t": 0, "list": []}
LOCK = threading.Lock()
MAXPTS = 1800     # 30 min at 1 sample/s

def light_servers():
    now = time.time()
    if now - SRV_CACHE["t"] < 5:
        return SRV_CACHE["list"]
    out = []
    names = swap_running_ports() or {}
    for pid in filter(str.isdigit, os.listdir("/proc")):
        if not is_model_server(int(pid)):
            continue
        i = proc_info(int(pid))
        if i and i["port"]:
            alias = (names.get(i["port"]) or {}).get("model") or i["alias"] or f"port {i['port']}"
            out.append({"alias": alias, "port": i["port"], "basalt": is_basalt_server(int(pid))})
    SRV_CACHE["t"] = now; SRV_CACHE["list"] = out
    return out

def get_slots(port):
    try:
        c = http.client.HTTPConnection("127.0.0.1", port, timeout=1.5)
        c.request("GET", "/slots"); r = c.getresponse(); d = json.loads(r.read()); c.close()
        return d if isinstance(d, list) else []
    except Exception:
        return None

ACC = {}  # alias -> [bucket_start, tokens, active_seconds]
LAST = {}   # alias -> last completed request's timings (BASALT)
LAST_T = {} # port -> last /v1/status poll time

def sampler():
    while True:
        t0 = time.time()
        try:
            for s in light_servers():
                if s["basalt"] and time.time() - LAST_T.get(s["port"], 0) >= 5:
                    LAST_T[s["port"]] = time.time()
                    t = basalt_last(s["port"])
                    if t:
                        LAST[s["alias"]] = {k: t.get(k) for k in ("predicted_per_second", "prompt_per_second", "predicted_n", "prompt_n", "at")}
                d = get_slots(s["port"])
                if d is None:
                    continue
                tok = 0.0; act = 0.0
                for sl in d:
                    key = (s["port"], sl.get("id"))
                    now = time.time()
                    if "generated" in sl and "state" in sl:          # BASALT slot row
                        dn, dt, nxt = basalt_slot_step(SLOT_STATE.get(key), sl, now)
                        SLOT_STATE[key] = nxt
                        if dn > 0:
                            tok += dn; act = max(act, dt)
                        continue
                    nd = None
                    if sl.get("is_processing"):
                        nt = sl.get("next_token") or []
                        if isinstance(nt, list) and nt and isinstance(nt[0], dict):
                            nd = nt[0].get("n_decoded")
                    prev = SLOT_STATE.get(key); tid = sl.get("id_task")
                    if nd is not None and prev and prev[0] == tid and nd >= prev[1] and now > prev[2]:
                        dn = nd - prev[1]
                        if dn > 0:
                            tok += dn; act = max(act, now - prev[2])
                    SLOT_STATE[key] = (tid, nd, now) if nd is not None else None
                a = ACC.setdefault(s["alias"], [time.time(), 0.0, 0.0]); a[1] += tok; a[2] += act
            now = time.time()
            for alias, a in list(ACC.items()):
                if now - a[0] >= 1.0:
                    with LOCK:
                        SAMPLES.setdefault(alias, collections.deque(maxlen=MAXPTS)).append((now, a[1] / (now - a[0]), a[1], a[2]))
                    ACC[alias] = [now, 0.0, 0.0]
        except Exception:
            pass
        time.sleep(max(0.02, 0.25 - (time.time() - t0)))

def summ(p):
    if not p:
        return {"now": None, "avg": None, "peak": None, "tokens": 0}
    tok = sum(x[2] for x in p); act = sum(x[3] for x in p)
    return {"now": round(p[-1][1], 1), "avg": round(tok / act, 1) if act > 0 else None,
            "peak": round(max(x[1] for x in p), 1), "tokens": round(tok)}

def down(p, maxn=600):
    if len(p) <= maxn:
        return [[round(x[0], 2), round(x[1], 1)] for x in p]
    k = -(-len(p) // maxn); out = []
    for i in range(0, len(p), k):
        ch = p[i:i + k]
        out.append([round(ch[-1][0], 2), round(max(x[1] for x in ch), 1)])
    return out

def tps_payload(window):
    window = max(10, min(1800, window)); now = time.time(); lo = now - window
    with LOCK:
        snap = {k: list(v) for k, v in SAMPLES.items()}
    series, stats, buckets = {}, {}, {}
    for alias, pts in snap.items():
        p = [x for x in pts if x[0] >= lo]
        if not p:
            continue
        series[alias] = down(p); stats[alias] = summ(p)
        if alias in LAST:
            stats[alias]["last"] = LAST[alias]
        for t, r, tk, ac in p:
            b = buckets.setdefault(int(t), [0.0, 0.0, 0.0])
            b[0] += r; b[1] += tk; b[2] = max(b[2], ac)
    total = [(float(t), v[0], v[1], v[2]) for t, v in sorted(buckets.items())]
    stats["__total__"] = summ(total)
    return {"now": now, "window": window, "series": series, "total": down(total), "stats": stats}

PAGE = r"""<!doctype html><html><head><meta charset="utf-8"><title>What's really running</title>
<style>
:root{color-scheme:dark light}
body{margin:0;padding:20px;font:14px system-ui,sans-serif;background:#0f1115;color:#e6e6e6}
@media (prefers-color-scheme:light){body{background:#fafafa;color:#1a1a1a}.card{background:#fff!important;border-color:#ddd!important}}
h2{margin:0 0 4px}.sub{opacity:.65;margin-bottom:16px}
.card{border:1px solid #2a2f3a;background:#171a21;border-radius:10px;padding:14px 16px;margin-bottom:12px}
.row{display:flex;gap:10px;align-items:center;flex-wrap:wrap}.name{font-weight:600;font-size:15px}
.pill{padding:2px 9px;border-radius:99px;font-size:12px;font-weight:600}
.ok{background:#14532d;color:#bbf7d0}.bad{background:#7f1d1d;color:#fecaca}.warn{background:#713f12;color:#fde68a}.mut{background:#2a2f3a;color:#cbd5e1}
.k{opacity:.6;min-width:92px;display:inline-block}.mono{font-family:ui-monospace,monospace;font-size:12.5px;word-break:break-all}
.bar{height:8px;background:#2a2f3a;border-radius:6px;overflow:hidden;margin:6px 0}.bar>div{height:100%;background:#4f8cff}
.rb{border:1px solid #2a2f3a;background:transparent;color:inherit;border-radius:6px;padding:3px 9px;margin-left:6px;cursor:pointer;font-size:12px}
.rb.on{background:#4f8cff;color:#fff;border-color:#4f8cff}
.tt{width:100%;border-collapse:collapse;margin-top:8px;font-size:13px}.tt th{text-align:left;opacity:.6;font-weight:500}.tt td,.tt th{padding:3px 10px 3px 0}
.sw{display:inline-block;width:10px;height:10px;border-radius:2px;margin-right:6px}
</style></head><body><h2>What's really running</h2><div class="sub" id="sum">loading…</div><div class="card"><div class="row"><span class="name">Tokens per second</span><span id="range" style="margin-left:auto"></span></div>
<canvas id="tpsChart" style="width:100%;height:180px;display:block;margin-top:8px"></canvas><div id="tpsStats"></div></div>
<div id="gpus"></div><div id="srv"></div>
<script>
const gb=m=>(m/1024).toFixed(1)+' GB';
const up=s=>s<3600?Math.round(s/60)+' min':(s/3600).toFixed(1)+' h';
async function tick(){try{
const r=await (await fetch('/_reality/status')).json();
document.getElementById('sum').textContent=r.summary+' · updated '+new Date(r.time*1000).toLocaleTimeString();
document.getElementById('gpus').innerHTML=r.gpus.map(g=>`<div class="card"><div class="row"><span class="name">GPU ${g.index}</span><span>${g.name}</span><span class="pill mut">${g.util}% load</span><span class="pill mut">${g.power_w==null?'?':Math.round(g.power_w)} W${g.power_limit_w?' / '+Math.round(g.power_limit_w)+' W':''}</span><span class="pill mut">${g.temp_c==null?'?':Math.round(g.temp_c)}&deg;C</span></div>
<div class="bar"><div style="width:${100*g.used_mib/g.total_mib}%"></div></div>${gb(g.used_mib)} / ${gb(g.total_mib)} memory
<div class="bar"><div style="width:${g.power_limit_w?Math.min(100,100*g.power_w/g.power_limit_w):0}%;background:#f59e0b"></div></div>power draw</div>`).join('');
document.getElementById('srv').innerHTML=r.servers.map(s=>{
const gm=Object.entries(s.gpu_mib).map(([i,m])=>`GPU${i} ${gb(m)}`).join(', ')||(s.cpu_only?'CPU only':'none');
const h=s.health===200?'<span class="pill ok">HEALTHY</span>':'<span class="pill bad">NO HEALTH</span>';
const o=s.managed_by_llama_swap?'<span class="pill ok">managed by llama-swap</span>':'<span class="pill warn">external: '+s.owner+'</span>';
return `<div class="card"><div class="row"><span class="name">${s.alias||'(no alias)'}</span>${h}${o}</div>
<div><span class="k">Port</span>${s.port||'?'} &nbsp; <span class="k">PID</span>${s.pid} &nbsp; <span class="k">Up</span>${up(s.uptime_s)}</div>
<div><span class="k">Memory</span>${gm}</div><div><span class="k">Model file</span><span class="mono">${s.model_file||'?'}</span></div></div>`}).join('')||'<div class="card">No llama-server processes found.</div>';
}catch(e){document.getElementById('sum').textContent='status error: '+e}}
const WINS=[[30,'Live 30s'],[60,'1 min'],[120,'2 min'],[300,'5 min'],[600,'10 min'],[1800,'30 min']];
let W=120;try{W=+localStorage.getItem('tpsW')||120}catch(e){}
const COLORS=['#4f8cff','#f59e0b','#22c55e','#ef4444','#a78bfa','#14b8a6'];
const f1=v=>v==null?'–':v.toFixed(1);
function renderRange(){document.getElementById('range').innerHTML=WINS.map(([s,l])=>`<button class="rb${s===W?' on':''}" onclick="setW(${s})">${l}</button>`).join('')}
function setW(s){W=s;try{localStorage.setItem('tpsW',s)}catch(e){}renderRange();tpsTick()}
function draw(d){
 const cv=document.getElementById('tpsChart'),dpr=window.devicePixelRatio||1,w=cv.clientWidth,h=180;
 cv.width=Math.round(w*dpr);cv.height=Math.round(h*dpr);const c=cv.getContext('2d');c.scale(dpr,dpr);
 const names=Object.keys(d.series).sort();let peak=10;
 names.concat(['__t']).forEach(n=>(n==='__t'?d.total:d.series[n]).forEach(p=>{if(p[1]>peak)peak=p[1]}));
 const ymax=[10,25,50,100,150,200,250,300,400,500,750,1000,1500].find(x=>x>=peak*1.05)||Math.ceil(peak*1.05);
 const L=42,R=8,T=8,B=20,pw=w-L-R,ph=h-T-B,t1=d.now,t0=t1-d.window,fg=getComputedStyle(document.body).color;
 const X=t=>L+pw*(t-t0)/d.window,Y=v=>T+ph*(1-v/ymax);
 c.font='11px system-ui';c.fillStyle=fg;c.strokeStyle='rgba(128,128,128,.25)';c.lineWidth=1;
 for(let i=0;i<=4;i++){const v=ymax*i/4,y=Y(v);c.beginPath();c.moveTo(L,y);c.lineTo(w-R,y);c.stroke();c.fillText(String(Math.round(v)),4,y+4)}
 c.fillText('-'+(d.window>=60?(d.window/60)+' min':d.window+' s'),L,h-5);c.fillText('now',w-R-22,h-5);
 const line=(pts,col,lw)=>{if(!pts.length)return;c.strokeStyle=col;c.lineWidth=lw;c.beginPath();pts.forEach((p,i)=>{const x=X(p[0]),y=Y(p[1]);i?c.lineTo(x,y):c.moveTo(x,y)});c.stroke()};
 names.forEach((n,i)=>line(d.series[n],COLORS[i%COLORS.length],1.6));
 if(names.length>1)line(d.total,fg,2.2);
}
function statsHtml(d){
 const names=Object.keys(d.series).sort();
 const row=(label,st,col)=>`<tr><td><span class="sw" style="background:${col}"></span>${label}</td><td>${f1(st.now)}</td><td>${f1(st.avg)}</td><td>${f1(st.peak)}</td><td>${st.tokens==null?'–':st.tokens}</td></tr>`;
 let h='<table class="tt"><tr><th>Model</th><th>Now t/s</th><th>Avg t/s (while generating)</th><th>Peak t/s</th><th>Tokens in window</th></tr>';
 h+=names.map((n,i)=>row(n,d.stats[n]||{},COLORS[i%COLORS.length])).join('');
 if(names.length>1)h+=row('All models',d.stats.__total__||{},'currentColor');
 return h+'</table>'+(names.length?'':'<div class="sub">No data yet.</div>');
}
async function tpsTick(){try{const d=await (await fetch('/_reality/tps?window='+W)).json();draw(d);document.getElementById('tpsStats').innerHTML=statsHtml(d)}catch(e){}}
renderRange();tpsTick();setInterval(tpsTick,1000);
tick();setInterval(tick,3000);
</script></body></html>"""

INJECT_JS = r"""(function(){
const LABEL="What's really running";
let panel=null, open=/[?&]reality\b/.test(location.search);
function links(){return [...document.querySelectorAll('a')].filter(a=>/^(Activity|Playground|Models|Logs|Performance|Hardware)/.test(a.textContent.trim()));}
function ensureTab(){
  if(document.getElementById('reality-tab'))return;
  const hw=links().find(a=>a.textContent.trim().startsWith('Hardware'));if(!hw)return;
  const t=hw.cloneNode(true);t.id='reality-tab';t.setAttribute('href','#/');
  const sp=[...t.querySelectorAll('span')].find(s=>s.textContent.trim()==='Hardware');if(sp)sp.textContent=LABEL;
  t.addEventListener('click',e=>{e.preventDefault();e.stopPropagation();open=true;sync();},true);
  hw.parentNode.insertBefore(t,hw.nextSibling);
}
function area(){
  const a=links()[0];if(!a)return 256;let el=a;
  while(el&&el.parentElement){const r=el.getBoundingClientRect();if(r.height>innerHeight*0.8&&r.width<420)break;el=el.parentElement;}
  return Math.round((el||a).getBoundingClientRect().right);
}
function sync(){
  ensureTab();
  if(open&&!panel){
    panel=document.createElement('div');panel.id='reality-panel';
    panel.style.cssText='position:fixed;top:0;right:0;bottom:0;left:'+area()+'px;z-index:50;background:Canvas';
    panel.innerHTML='<iframe src="/_reality/" style="border:0;width:100%;height:100%"></iframe>';
    document.body.appendChild(panel);
  }else if(!open&&panel){panel.remove();panel=null;}
  const t=document.getElementById('reality-tab');if(t)t.style.fontWeight=open?'600':'';
}
document.addEventListener('click',e=>{
  const a=e.target.closest&&e.target.closest('a');
  if(open&&a&&a.id!=='reality-tab'&&a.closest('nav,aside,[data-sidebar],ul,div')){open=false;setTimeout(sync,0);}
},true);
new MutationObserver(()=>{if(!document.getElementById('reality-tab'))sync();}).observe(document.documentElement,{childList:true,subtree:true});
sync();
})();"""

class H(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.0"
    def log_message(self, *a): pass
    def _send(self, code, body, ctype):
        self.send_response(code); self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body))); self.send_header("Cache-Control", "no-store")
        self.end_headers(); self.wfile.write(body)
    def do_GET(self): self.handle_any()
    do_POST = do_PUT = do_DELETE = do_PATCH = do_OPTIONS = do_HEAD = do_GET
    def handle_any(self):
        p = self.path.split("?")[0]
        if p == "/_reality/tps":
            q = parse_qs(urlparse(self.path).query)
            try: w = int((q.get("window") or ["120"])[0])
            except ValueError: w = 120
            return self._send(200, json.dumps(tps_payload(w)).encode(), "application/json")
        if p == "/_reality/status":
            return self._send(200, json.dumps(status()).encode(), "application/json")
        if p in ("/_reality", "/_reality/"):
            return self._send(200, PAGE.encode(), "text/html; charset=utf-8")
        if p == "/_reality/inject.js":
            return self._send(200, INJECT_JS.encode(), "application/javascript")
        self.proxy()
    def proxy(self):
        n = int(self.headers.get("Content-Length") or 0)
        body = self.rfile.read(n) if n else None
        hdr = {k: v for k, v in self.headers.items() if k.lower() not in HOP and k.lower() not in ("host", "accept-encoding")}
        hdr["Host"] = "%s:%d" % UPSTREAM
        try:
            c = http.client.HTTPConnection(*UPSTREAM, timeout=3600)
            c.request(self.command, self.path, body=body, headers=hdr)
            r = c.getresponse()
        except Exception as e:
            return self._send(502, ("llama-swap unreachable: %s" % e).encode(), "text/plain")
        ctype = r.getheader("Content-Type", "")
        is_ui = ctype.startswith("text/html") and self.path.split("?")[0] in ("/ui", "/ui/", "/ui/index.html")
        self.send_response(r.status)
        for k, v in r.getheaders():
            if k.lower() not in HOP:
                self.send_header(k, v)
        if is_ui:
            data = r.read().decode("utf-8", "replace")
            tag = '<script src="/_reality/inject.js"></script>'
            data = data.replace("</body>", tag + "</body>", 1) if "</body>" in data else data + tag
            out = data.encode()
            self.send_header("Content-Length", str(len(out))); self.end_headers()
            if self.command != "HEAD": self.wfile.write(out)
            return
        self.end_headers()
        if self.command == "HEAD": return
        try:
            while True:
                chunk = r.read1(8192) if hasattr(r, "read1") else r.read(8192)
                if not chunk: break
                self.wfile.write(chunk); self.wfile.flush()
        except Exception:
            pass
        finally:
            c.close()

if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--status":
        print(json.dumps(status(), indent=2)); sys.exit(0)
    threading.Thread(target=sampler, daemon=True).start()
    ThreadingHTTPServer(LISTEN, H).serve_forever()
