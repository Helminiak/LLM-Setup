#!/usr/bin/env python3
"""Brief single-vs-dual local Gyro-L coding-request benchmark; no config changes."""
import argparse, concurrent.futures, json, re, statistics, subprocess, tempfile, threading, time, urllib.request
from pathlib import Path

API = "http://127.0.0.1:8081/v1/chat/completions"
HEALTH = "http://127.0.0.1:8081/health"
PROMPT = "Write only Python source, no Markdown or explanation. Implement def normalize_label(value: str) -> str: strip surrounding whitespace, lowercase, and collapse internal whitespace to one ASCII space. Do not change punctuation. Task ID: {task_id}."
TESTS = "from solution import normalize_label\nassert normalize_label('  Ship   NOW! ') == 'ship now!'\nassert normalize_label('A\\tB\\nC') == 'a b c'\nassert normalize_label('') == ''\nprint('VALIDATION_OK')\n"

def validate_artifact(code):
    try:
        with tempfile.TemporaryDirectory(prefix="gyro-worker-validator-") as d:
            p=Path(d); (p/"solution.py").write_text(code+"\n"); (p/"test_solution.py").write_text(TESTS)
            run=subprocess.run(["python3","test_solution.py"],cwd=p,text=True,capture_output=True,timeout=15)
            return run.returncode==0, (run.stdout+run.stderr)[-800:] if run.returncode else None
    except Exception as e: return False,repr(e)

def validator_self_test():
    good="def normalize_label(value: str) -> str:\n    return ' '.join(value.strip().lower().split())\n"
    bad="def normalize_label(value: str) -> str:\n    return value\n"
    assert validate_artifact(good)[0], "known-correct validator fixture failed"
    assert not validate_artifact(bad)[0], "known-incorrect validator fixture unexpectedly passed"

def slots():
    with urllib.request.urlopen("http://127.0.0.1:8081/slots", timeout=4) as r: return json.load(r)
def request(task_id):
    prompt=PROMPT.format(task_id=task_id)
    payload={"model":"gyro-l","messages":[{"role":"user","content":prompt}],"temperature":0,"top_p":1,"seed":42,"max_tokens":512,"stream":False}
    req=urllib.request.Request(API,data=json.dumps(payload).encode(),headers={"Content-Type":"application/json"})
    start=time.monotonic()
    with urllib.request.urlopen(req,timeout=180) as resp: raw=json.load(resp)
    elapsed=time.monotonic()-start
    text=raw.get("choices",[{}])[0].get("message",{}).get("content") or ""
    text=re.sub(r"<think>.*?</think>","",text,flags=re.S).strip()
    blocks=re.findall(r"```(?:python)?\s*(.*?)```",text,flags=re.S|re.I)
    code=(blocks[-1] if blocks else text).strip()
    valid,error=validate_artifact(code)
    finish=raw.get("choices",[{}])[0].get("finish_reason")
    classification="validated_correct" if valid else ("incomplete_response" if finish=="length" else ("genuine_incorrect_answer" if code else "empty_or_unparseable_artifact"))
    return {"task_id":task_id,"prompt":prompt,"wall_s":elapsed,"valid":valid,"failure_classification":classification,"finish_reason":finish,"validator_output":error,"response":raw,"artifact":code}

class Monitor:
    def __init__(self): self.rows=[]; self.stop=threading.Event(); self.thread=None
    def sample(self):
        cmd=["nvidia-smi","--query-gpu=index,memory.used,memory.free,utilization.gpu,power.draw","--format=csv,noheader,nounits"]
        p=subprocess.run(cmd,capture_output=True,text=True,timeout=4)
        now=time.time()
        for line in p.stdout.splitlines():
            vals=[x.strip() for x in line.split(',')]
            if len(vals)>=5:
                try: self.rows.append({"ts":now,"gpu":int(vals[0]),"used_mib":int(vals[1]),"free_mib":int(vals[2]),"util_pct":int(vals[3]),"power_w":float(vals[4])})
                except ValueError: pass
    def run(self):
        def loop():
            while not self.stop.is_set():
                try: self.sample()
                except Exception: pass
                self.stop.wait(.35)
        self.thread=threading.Thread(target=loop,daemon=True); self.thread.start()
    def done(self): self.stop.set(); self.thread.join(timeout=5); self.sample()

def percentile(values,p):
    v=sorted(values)
    if not v: return None
    pos=(len(v)-1)*p; lo=int(pos); hi=min(len(v)-1,lo+1)
    return round(v[lo]+(v[hi]-v[lo])*(pos-lo),3)
def summarize(name,results,wall,monitor):
    samples=monitor.rows
    gpus=[]
    for i in (0,1):
        ss=[x for x in samples if x['gpu']==i]
        gpus.append({"gpu":i,"min_free_mib":min((x['free_mib'] for x in ss),default=None),"max_used_mib":max((x['used_mib'] for x in ss),default=None),"mean_util_pct":round(statistics.mean(x['util_pct'] for x in ss),2) if ss else None,"max_util_pct":max((x['util_pct'] for x in ss),default=None)})
    tokens=sum((r.get('response',{}).get('usage') or {}).get('completion_tokens',0) for r in results)
    lats=[r['wall_s'] for r in results]
    return {"workers":name,"tasks":len(results),"validated":sum(r['valid'] for r in results),"elapsed_s":round(wall,3),"aggregate_completion_tps":round(tokens/wall,3) if wall else None,"latency_p50_s":percentile(lats,.5),"latency_p95_s":percentile(lats,.95),"gpus":gpus}

def main():
    ap=argparse.ArgumentParser(); ap.add_argument('--output',required=True); ap.add_argument('--tasks',type=int,default=4); args=ap.parse_args()
    if args.tasks<2 or args.tasks%2: raise SystemExit('--tasks must be an even number >= 2')
    validator_self_test()
    with urllib.request.urlopen(HEALTH,timeout=3) as r: health=json.load(r)
    ss=slots()
    if health.get('status')!='ok' or len(ss)!=2 or any(x.get('n_ctx')!=64000 for x in ss): raise SystemExit('Refusing benchmark: service/slot acceptance not met')
    if any(x.get('is_processing') for x in ss): raise SystemExit('Refusing benchmark: an inference slot is busy')
    raw=[]; report={"model":"gyro-l","endpoint":"127.0.0.1:8081/v1","sampling":{"temperature":0,"top_p":1,"seed":42,"max_tokens":512},"task":"normalize_label code generation with deterministic Python assertions","validator_self_test":"known-correct passed; known-incorrect rejected","tasks_per_configuration":args.tasks}
    for name,concurrency,offset in [('single_worker',1,100),('dual_worker',2,200)]:
        mon=Monitor(); mon.sample(); mon.run(); start=time.monotonic(); results=[]
        if concurrency==1:
            for i in range(args.tasks): results.append(request(offset+i))
        else:
            for base in range(0,args.tasks,2):
                with concurrent.futures.ThreadPoolExecutor(2) as pool: results.extend(pool.map(request,[offset+base,offset+base+1]))
        elapsed=time.monotonic()-start; mon.done()
        report.setdefault('configurations',[]).append(summarize(name,results,elapsed,mon))
        for r in results: raw.append({"configuration":name,"result":r})
        report[name+"_gpu_samples"]=mon.rows
    output=Path(args.output); output.parent.mkdir(parents=True,exist_ok=True)
    output.write_text(json.dumps({"summary":report,"raw":raw},indent=2)+"\n")
    print(json.dumps({k:v for k,v in report.items() if not k.endswith('_gpu_samples')},indent=2))
    if any(c['validated']!=args.tasks for c in report['configurations']): raise SystemExit('At least one deterministic code task failed validation')
if __name__=='__main__': main()
