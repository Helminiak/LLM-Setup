import concurrent.futures,json,pathlib,subprocess,time,urllib.request
R=pathlib.Path('/home/joe/dual-5090-optimization'); O=R/'results/adaptive-screen-20261106'; O.mkdir(parents=True,exist_ok=True)
TASK='Return only complete Rust source. Implement a fixed-capacity FIFO ring buffer of i32 with push, pop, empty/full, overflow error, wraparound, and six unit tests. No markdown or reasoning.'
CS=[('A-baseline',{'CACHE_TYPE_K':'q8_0','CACHE_TYPE_V':'q8_0','BATCH_SIZE':2048,'UBATCH_SIZE':512}),('B-small-batch',{'CACHE_TYPE_K':'q8_0','CACHE_TYPE_V':'q8_0','BATCH_SIZE':1024,'UBATCH_SIZE':256}),('C-large-batch',{'CACHE_TYPE_K':'q8_0','CACHE_TYPE_V':'q8_0','BATCH_SIZE':4096,'UBATCH_SIZE':512}),('D-q4-kv',{'CACHE_TYPE_K':'q4_0','CACHE_TYPE_V':'q4_0','BATCH_SIZE':2048,'UBATCH_SIZE':512}),('E-q4-small-batch',{'CACHE_TYPE_K':'q4_0','CACHE_TYPE_V':'q4_0','BATCH_SIZE':1024,'UBATCH_SIZE':256}),('F-large-ubatch',{'CACHE_TYPE_K':'q8_0','CACHE_TYPE_V':'q8_0','BATCH_SIZE':2048,'UBATCH_SIZE':1024})]
def restart(c):
 (R/'config/active-overrides.env').write_text('\n'.join(f'{k}={v}' for k,v in c.items())+'\n'); subprocess.run(['systemctl','--user','restart','gyro-coder-l-gpu0.service','gyro-coder-l-gpu1.service'],check=True,stdout=subprocess.DEVNULL)
 for _ in range(120):
  try:
   if all(urllib.request.urlopen(f'http://127.0.0.1:{p}/health',timeout=1).status==200 for p in (8082,8083)): return True
  except Exception: pass
  time.sleep(1)
 return False
def one(n,p,label):
 b=json.dumps({'model':'gyro-coder-l','messages':[{'role':'user','content':TASK}],'temperature':0,'top_p':.95,'top_k':20,'min_p':.05,'max_tokens':4096,'reasoning_format':'none','timings_per_token':True}).encode(); q=urllib.request.Request(f'http://127.0.0.1:{p}/v1/chat/completions',data=b,headers={'Content-Type':'application/json'}); t=time.monotonic()
 try:
  with urllib.request.urlopen(q,timeout=180) as x:d=json.load(x)
  m=d['choices'][0]['message']; c=(m.get('content') or m.get('reasoning_content') or '').replace('```rust','').replace('```','').strip()+'\n'; w=O/label/n; w.mkdir(parents=True,exist_ok=True); (w/'response.json').write_text(json.dumps(d,indent=2)); (w/'main.rs').write_text(c); cp=subprocess.run(['rustc','--test','main.rs','-o','testbin'],cwd=w,capture_output=True,text=True); tp=subprocess.run(['./testbin'],cwd=w,capture_output=True,text=True) if cp.returncode==0 else None; ti=d.get('timings') or {}; return {'worker':n,'wall_s':time.monotonic()-t,'prompt_tokens':d.get('usage',{}).get('prompt_tokens'),'generated_tokens':d.get('usage',{}).get('completion_tokens'),'prompt_tps':ti.get('prompt_per_second'),'generation_tps':ti.get('predicted_per_second'),'finish_reason':d['choices'][0].get('finish_reason'),'compile':cp.returncode==0,'tests':bool(tp and tp.returncode==0)}
 except Exception as e:return {'worker':n,'error':repr(e)}
OUT=[]
for i in range(0,6,2):
 for label,cfg in CS[i:i+2]:
  print('starting',label,flush=True); ok=restart(cfg); t=time.monotonic()
  with concurrent.futures.ThreadPoolExecutor(2) as ex: rr=list(ex.map(lambda z:one(z[0],z[1],label),[('gpu0',8082),('gpu1',8083)]))
  OUT.append({'round':i//2+1,'config':label,'settings':cfg,'ready':ok,'wall_s':time.monotonic()-t,'workers':rr}); print(json.dumps(OUT[-1]),flush=True)
(O/'screening.json').write_text(json.dumps(OUT,indent=2))
