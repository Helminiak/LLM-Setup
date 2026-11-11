#!/usr/bin/env python3
"""Bounded two-worker Hermes verification with per-process lifecycle records."""
import json, os, signal, subprocess, sys, time
from pathlib import Path
from urllib.request import urlopen
from hermes_telemetry import analyze_file, digest

ROOT=Path('/home/joe/dual-5090-optimization/results/hermes-turn12-20261106'); ROOT.mkdir(parents=True,exist_ok=True)
mode=sys.argv[1] if len(sys.argv)>1 else 'short'; assert mode in ('short','long')
deadline=420 if mode=='short' else 600
prompt=('Create a standard-library-only Rust 2021 Cargo project here. Implement a bounded FIFO ring buffer '
        'with explicit overflow, wraparound, and empty/full behavior. Add six unit tests. Run cargo fmt --check '
        'and cargo test. Report results. Keep source complete and compilable.')
def health(port):
    try:
        with urlopen(f'http://127.0.0.1:{port}/health',timeout=2) as r: return json.load(r).get('status')=='ok'
    except Exception: return False
def events(path):
    records=[]
    try:
        for line in path.read_text(errors='replace').splitlines():
            try:
                d=json.loads(line)
                if d.get('type')!='text': records.append({k:d.get(k) for k in ('type','timestamp','name','exit_code','tokens')})
            except json.JSONDecodeError: pass
    except FileNotFoundError: pass
    return records
children=[]; start=time.monotonic(); reason=None
try:
    for i,port in enumerate((8082,8083)):
        if not health(port): raise RuntimeError(f'endpoint {port} unhealthy')
        work=ROOT/f'{mode}-agent-{i+1}'; work.mkdir(parents=True,exist_ok=True)
        agent_prompt=prompt
        if mode=='long':
            prior=Path('/home/joe/dual-5090-optimization/results/full-context-production/preflight/run.jsonl').read_text(errors='replace')
            own=(ROOT/f'short-agent-{i+1}/hermes.jsonl').read_text(errors='replace')
            agent_prompt=('Prior coding conversation, tool results, and implementation decisions follow. '
                          'Use them as project history, then perform the current task.\n'+prior[:90000]
                          +'\nYour own preceding coding session:\n'+own[:60000]+'\nCurrent task:\n'+prompt)
        query=work/'prompt.txt'; query.write_text(agent_prompt)
        out=open(work/'hermes.jsonl','w'); err=open(work/'hermes.err','w')
        cmd=['hermes','chat','--safe-mode','--provider','custom','--base-url',f'http://127.0.0.1:{port}/v1',
             '--model',f'gyro-coder-l-gpu{i}','--reasoning','none','--in',str(work),'--query-file',str(query),
             '--oneshot','--max-turns','12','--format','stream-json']
        env=os.environ.copy(); env['HERMES_HOME']='/home/joe/.hermes/profiles/gyro-coder-supervisor'
        proc=subprocess.Popen(cmd,stdout=out,stderr=err,env=env,start_new_session=True)
        children.append({'proc':proc,'out':out,'err':err,'work':work,'port':port,'start':time.monotonic(),'exit_at':None})
    while True:
        now=time.monotonic()
        for child in children:
            if child['proc'].poll() is not None and child['exit_at'] is None: child['exit_at']=now
        if all(child['exit_at'] is not None for child in children): break
        if now-start>deadline: reason='execution_deadline'; break
        if not all(health(child['port']) for child in children): reason='endpoint_unhealthy'; break
        time.sleep(1)
finally:
    for child in children:
        proc=child['proc']
        if proc.poll() is None:
            os.killpg(proc.pid,signal.SIGTERM)
            try: proc.wait(timeout=5)
            except subprocess.TimeoutExpired: os.killpg(proc.pid,signal.SIGKILL); proc.wait()
        child['exit_at']=child['exit_at'] or time.monotonic()
        child['out'].close(); child['err'].close()
rows=[]
for child in children:
    work=child['work']; cargo=work/'Cargo.toml'; test=None
    if cargo.exists():
        run=subprocess.run(['cargo','test','--manifest-path',str(cargo)],capture_output=True,text=True,timeout=30)
        compiler_log=work/'cargo-test.log'; compiler_log.write_text(run.stdout+run.stderr)
        test={'exit':run.returncode,'log':str(compiler_log),'summary':(run.stdout+run.stderr)[-1000:]}
    telemetry=analyze_file(work/'hermes.jsonl', verifications=[{'command':'cargo test','output':compiler_log.read_text(),
        'exit_code':run.returncode}] if test else ())
    rows.append({'port':child['port'],'exit':child['proc'].returncode,'elapsed_s':round(child['exit_at']-child['start'],3),
                 'events':events(work/'hermes.jsonl'),'cargo':test,'telemetry':digest(telemetry)})
summary={'mode':mode,'deadline_s':deadline,'reason':reason,'wall_s':round(time.monotonic()-start,3),'agents':rows}
(ROOT/f'{mode}-summary.json').write_text(json.dumps(summary,indent=2))
print(json.dumps({'mode':mode,'reason':reason,'agents':[{'port':row['port'],'exit':row['exit'],'elapsed_s':row['elapsed_s'],
      'cargo_exit':row['cargo']['exit'] if row['cargo'] else None,'events':len(row['events'])} for row in rows]},indent=2))
