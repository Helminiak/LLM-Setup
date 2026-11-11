#!/usr/bin/env python3
"""Four isolated real Hermes processes, two queued per single-slot GPU."""
import concurrent.futures, json, os, subprocess, time
from pathlib import Path
from urllib.request import urlopen
ROOT=Path.home()/'.local/state/sol-restoration/four-workers'
ROOT.mkdir(parents=True,exist_ok=True)
def health():
    for port in (8082,8083):
        assert json.load(urlopen(f'http://127.0.0.1:{port}/health',timeout=5))['status']=='ok'
def memory():
    return [int(x) for x in subprocess.check_output(['nvidia-smi','--query-gpu=memory.free','--format=csv,noheader,nounits'],text=True).split()]
def run(i):
    work=ROOT/f'worker-{i}'; work.mkdir(exist_ok=True)
    port=8082+i%2
    prompt='Create clamp.py defining clamp(value, low, high): reject low > high with ValueError, otherwise bound value inclusively. Use terminal or file tools to write the actual file in the current directory. Run a Python smoke test. Do not inspect other directories.'
    cmd=['hermes','-p','gyro-coder-supervisor','chat','--cli','--provider','custom','--base-url',f'http://127.0.0.1:{port}/v1','--model',f'gyro-coder-l-gpu{i%2}','--reasoning','none','--in',str(work),'--oneshot','--max-turns','12','--format','stream-json','-q',prompt]
    start=time.monotonic()
    with (work/'run.jsonl').open('w') as out,(work/'run.err').open('w') as err:
        try: rc=subprocess.run(cmd,stdout=out,stderr=err,timeout=300).returncode
        except subprocess.TimeoutExpired: rc=124
    test='from clamp import clamp\nassert clamp(-1,0,9)==0\nassert clamp(12,0,9)==9\nassert clamp(4,0,9)==4\nassert clamp(2,2,2)==2\ntry: clamp(0,2,1)\nexcept ValueError: pass\nelse: raise AssertionError("invalid bounds")'
    result=subprocess.run(['python3','-c',test],cwd=work,capture_output=True,text=True)
    return {'worker':i,'port':port,'exit':rc,'test_exit':result.returncode,'elapsed_s':round(time.monotonic()-start,2)}
health(); before=memory(); assert min(before)>1024
start=time.monotonic(); samples=[before]
with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
    futures=[pool.submit(run,i) for i in range(4)]
    while not all(f.done() for f in futures):
        health(); samples.append(memory()); time.sleep(3)
    rows=[f.result() for f in futures]
report={'workers':rows,'wall_s':round(time.monotonic()-start,2),'min_free_mib':[min(x[i] for x in samples) for i in range(2)],'pass':all(r['exit']==r['test_exit']==0 for r in rows),'scope':'four processes; queued inference, one slot per GPU; production Kanban unchanged'}
(ROOT/'summary.json').write_text(json.dumps(report,indent=2)); print(json.dumps(report,indent=2))
