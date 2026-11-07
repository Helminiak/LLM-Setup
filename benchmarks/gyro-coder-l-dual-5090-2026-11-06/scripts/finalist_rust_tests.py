import concurrent.futures,json,pathlib,subprocess,time,urllib.request
R=pathlib.Path('/home/joe/dual-5090-optimization'); O=R/'results/finalist-rust-20261106'; O.mkdir(parents=True,exist_ok=True)
TASKS=[('ring','Implement a fixed-capacity Rust FIFO ring buffer with safe push/pop, wraparound, full/empty flags, overflow error, and six unit tests.'),('parser','Implement a Rust incremental newline-delimited id|value parser preserving partial chunks, rejecting malformed records, recovering after errors, with six unit tests.'),('repair','Implement a Rust bounded counter and repair underflow, overflow, invalid indexing, and reset defects. Include six unit tests.')]
CS={'C':{'CACHE_TYPE_K':'q8_0','CACHE_TYPE_V':'q8_0','BATCH_SIZE':4096,'UBATCH_SIZE':512},'F':{'CACHE_TYPE_K':'q8_0','CACHE_TYPE_V':'q8_0','BATCH_SIZE':2048,'UBATCH_SIZE':1024}}
def restart(c):
 (R/'config/active-overrides.env').write_text('\n'.join(f'{k}={v}' for k,v in c.items())+'\n'); subprocess.run(['systemctl','--user','restart','gyro-coder-l-gpu0.service','gyro-coder-l-gpu1.service'],check=True,stdout=subprocess.DEVNULL)
 for _ in range(120):
  try:
   if all(urllib.request.urlopen(f'http://127.0.0.1:{p}/health',timeout=1).status==200 for p in (8082,8083)): return
  except Exception: pass
  time.sleep(1)
def run(f,t,prompt,port):
 b=json.dumps({'model':'gyro-coder-l','messages':[{'role':'system','content':'Output only complete Rust code after thinking. No markdown.'},{'role':'user','content':prompt}], 'temperature':0,'top_p':.95,'top_k':20,'min_p':.05,'max_tokens':4096,'reasoning_format':'none','timings_per_token':True}).encode(); q=urllib.request.Request(f'http://127.0.0.1:{port}/v1/chat/completions',data=b,headers={'Content-Type':'application/json'}); st=time.monotonic()
 with urllib.request.urlopen(q,timeout=240) as x:d=json.load(x)
 c=d['choices'][0]['message'].get('content') or d['choices'][0]['message'].get('reasoning_content') or ''
 if '</think>' in c:c=c.split('</think>',1)[1]
 c=c.replace('```rust','').replace('```','').strip()+'\n'; w=O/f/t/f'gpu{port-8082}'; w.mkdir(parents=True,exist_ok=True); (w/'response.json').write_text(json.dumps(d,indent=2)); (w/'main.rs').write_text(c); cp=subprocess.run(['rustc','--test','main.rs','-o','testbin'],cwd=w,capture_output=True,text=True); tp=subprocess.run(['./testbin'],cwd=w,capture_output=True,text=True) if cp.returncode==0 else None; ti=d.get('timings') or {}; return {'finalist':f,'task':t,'gpu':port-8082,'wall_s':time.monotonic()-st,'prompt_tokens':d.get('usage',{}).get('prompt_tokens'),'generated_tokens':d.get('usage',{}).get('completion_tokens'),'generation_tps':ti.get('predicted_per_second'),'finish_reason':d['choices'][0].get('finish_reason'),'compile':cp.returncode==0,'tests':bool(tp and tp.returncode==0)}
ALL=[]
for f,cfg in CS.items():
 restart(cfg)
 for t,d in TASKS:
  p='Return only one complete Rust 2021 source file. '+d+' Standard library only. Include exactly six unit tests. No markdown.'
  with concurrent.futures.ThreadPoolExecutor(2) as ex: rr=list(ex.map(lambda port:run(f,t,p,port),(8082,8083)))
  ALL.extend(rr); print(json.dumps(rr),flush=True)
(O/'results.json').write_text(json.dumps(ALL,indent=2))
