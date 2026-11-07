#!/usr/bin/env python3
import json, os, subprocess, sys, time
from pathlib import Path

stage = int(sys.argv[1]); root = Path('/home/joe/dual-5090-optimization/results/full-context-production') / f'stage-{stage}'
root.mkdir(parents=True, exist_ok=True)
base = Path('/home/joe/dual-5090-optimization/results/full-context-production/preflight/run.jsonl').read_text(errors='ignore')
history = ('You are continuing an independent Rust engineering task. Preserve these prior decisions and constraints.\n'
           'The implementation must be standard-library-only, Rust 2021, ownership-safe, deterministic, and tested.\n'
           'Prior review: use explicit boundary checks, document panic behavior, avoid unsafe code, and keep tests independent.\n')
history += ('\nPrior Hermes telemetry and tool transcript (context retained for this agent):\n' + base[:120000])
history += ('\nAdditional project notes:\n' + ('Rust API compatibility, error handling, and regression-test requirements. ' * 1800))
prompt = history + '\n\nNow create src/main.rs with a complete bounded ring-buffer implementation (capacity, FIFO push/pop, full/empty, overflow Result), exactly six unit tests, and a minimal Cargo.toml if needed. Run rustfmt --check and cargo test. Do not stop until source is complete and tests pass. Report measured commands and results.'
procs=[]; meta=[]
for i in range(stage):
    ws=root/f'agent-{i+1}'; ws.mkdir(parents=True, exist_ok=True)
    q=ws/'prompt.txt'; q.write_text(prompt)
    gpu=i%2; port=8082+gpu
    out=ws/'hermes.jsonl'; err=ws/'hermes.err'; t=time.time()
    f=open(out,'w'); e=open(err,'w')
    env=os.environ.copy(); env['HERMES_HOME']='/home/joe/.hermes/profiles/gyro-coder-supervisor'
    cmd=['hermes','chat','--safe-mode','--provider','custom','--base-url',f'http://127.0.0.1:{port}/v1','--model',f'gyro-coder-l-gpu{gpu}','--reasoning','none','--in',str(ws),'--query-file',str(q),'--oneshot','--max-turns','8','--format','stream-json']
    procs.append((subprocess.Popen(cmd,stdout=f,stderr=e,env=env),f,e,t,i,gpu,ws))
for p,f,e,t,i,gpu,ws in procs: p.wait(); f.close(); e.close()
def extract(p):
    text=''; result={}
    for line in p.read_text(errors='ignore').splitlines():
        try:
            d=json.loads(line)
            if d.get('type')=='text': text += d.get('text','')
            if d.get('type')=='result': result=d
        except: pass
    return text,result
rows=[]
for proc,f,e,t,i,gpu,ws in procs:
    text,res=extract(ws/'hermes.jsonl'); (ws/'response.txt').write_text(text)
    cargo=subprocess.run(['cargo','test','--manifest-path',str(ws/'Cargo.toml')],capture_output=True,text=True) if (ws/'Cargo.toml').exists() else None
    rows.append({'agent':i+1,'gpu':gpu,'exit_code':proc.returncode,'duration_s':time.time()-t,'result':res,'response_chars':len(text),'cargo_pass':bool(cargo and cargo.returncode==0),'cargo_output':(cargo.stdout+"\n"+cargo.stderr)[-4000:] if cargo else ''})
(root/'stage.json').write_text(json.dumps({'stage':stage,'agents':rows},indent=2))
print(json.dumps({'stage':stage,'agents':rows},indent=2))
