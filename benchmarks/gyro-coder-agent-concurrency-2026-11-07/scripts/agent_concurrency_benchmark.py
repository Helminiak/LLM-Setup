import concurrent.futures,json,os,pathlib,subprocess,time,urllib.request
ROOT=pathlib.Path('/home/joe/dual-5090-optimization'); OUT=ROOT/'results/agent-concurrency-20261107'; OUT.mkdir(parents=True,exist_ok=True)
TASK='Return only complete Rust code after thinking, with no markdown. Implement fn clamp(x:i32, lo:i32, hi:i32)->i32, and exactly six unit tests covering normal values, both boundaries, reversed bounds, and negatives. Standard library only.'
LEVELS=[2,4,6,8]
TIMEOUT=90; RAM_MIN_KIB=8*1024*1024; SWAP_DELTA_KIB=1024*1024; QUEUE_LIMIT=4; COMPILERS=2
def mem():
 d={}
 for line in pathlib.Path('/proc/meminfo').read_text().splitlines():
  k,v=line.split(':',1); d[k]=int(v.strip().split()[0])
 return d
def gpu():
 try:return subprocess.check_output(['nvidia-smi','--query-gpu=index,utilization.gpu,memory.used,memory.free,temperature.gpu,power.draw','--format=csv,noheader'],text=True).strip()
 except Exception as e:return 'ERROR '+repr(e)
def health():
 try:return all(urllib.request.urlopen(f'http://127.0.0.1:{p}/health',timeout=2).status==200 for p in (8082,8083))
 except Exception:return False
def agent(stage,i):
 port=8082 if i%2==0 else 8083; wd=OUT/f'stage-{stage}'/f'agent-{i}'; wd.mkdir(parents=True,exist_ok=True); body=json.dumps({'model':'gyro-coder-l','messages':[{'role':'system','content':'Output only complete Rust code after thinking. No markdown.'},{'role':'user','content':TASK}],'temperature':0,'top_p':.95,'top_k':20,'min_p':.05,'max_tokens':2048,'reasoning_format':'none','timings_per_token':True}).encode(); req=urllib.request.Request(f'http://127.0.0.1:{port}/v1/chat/completions',data=body,headers={'Content-Type':'application/json'}); t=time.monotonic()
 try:
  with urllib.request.urlopen(req,timeout=TIMEOUT) as r:d=json.load(r)
  c=d['choices'][0]['message'].get('content') or d['choices'][0]['message'].get('reasoning_content') or ''
  if '</think>' in c:c=c.split('</think>',1)[1]
  c=c.replace('```rust','').replace('```','').strip()+'\n'; (wd/'response.json').write_text(json.dumps(d,indent=2)); (wd/'main.rs').write_text(c)
  cp=subprocess.run(['rustc','--test','main.rs','-o','testbin'],cwd=wd,capture_output=True,text=True); tp=subprocess.run(['./testbin'],cwd=wd,capture_output=True,text=True) if cp.returncode==0 else None; ti=d.get('timings') or {}
  return {'agent':i,'gpu':port-8082,'wall_s':time.monotonic()-t,'prompt_tokens':d.get('usage',{}).get('prompt_tokens'),'generated_tokens':d.get('usage',{}).get('completion_tokens'),'generation_tps':ti.get('predicted_per_second'),'finish_reason':d['choices'][0].get('finish_reason'),'compile':cp.returncode==0,'tests':bool(tp and tp.returncode==0),'error':None}
 except Exception as e:return {'agent':i,'gpu':port-8082,'wall_s':time.monotonic()-t,'compile':False,'tests':False,'error':repr(e)}
def run_stage(n):
 b=mem(); sw0=b.get('SwapFree',0); start=time.monotonic(); pre=gpu(); hs0=health(); results=[]
 with concurrent.futures.ThreadPoolExecutor(max_workers=n) as ex: results=list(ex.map(lambda i:agent(n,i),range(n)))
 elapsed=time.monotonic()-start; a=mem(); post=gpu(); hs1=health(); total=sum(r.get('generated_tokens',0) or 0 for r in results); correct=sum(1 for r in results if r.get('compile') and r.get('tests')); failures=sum(1 for r in results if r.get('error')); waits=max(0,n//2-1)
 return {'agents':n,'elapsed_s':elapsed,'completed':len(results),'correct':correct,'correct_per_min':60*correct/elapsed,'aggregate_tok_s':total/elapsed if elapsed else 0,'p50_latency_s':sorted(r['wall_s'] for r in results)[len(results)//2-1] if results else None,'p95_latency_s':sorted(r['wall_s'] for r in results)[max(0,int(len(results)*.95)-1)] if results else None,'queue_limit':QUEUE_LIMIT,'estimated_max_waiting_per_gpu':waits,'health_before':hs0,'health_after':hs1,'mem_before_kib':b.get('MemAvailable'),'mem_after_kib':a.get('MemAvailable'),'swap_delta_kib':sw0-a.get('SwapFree',0),'gpu_before':pre,'gpu_after':post,'agent_errors':failures,'workers':results,'status':'PASS' if hs0 and hs1 and a.get('MemAvailable',0)>=RAM_MIN_KIB and sw0-a.get('SwapFree',0)<=SWAP_DELTA_KIB and failures==0 and waits<=QUEUE_LIMIT else 'FAIL'}
baseline={'captured_at':time.time(),'memory':mem(),'gpu':gpu(),'health':health(),'thresholds':{'request_timeout_s':TIMEOUT,'ram_min_kib':RAM_MIN_KIB,'swap_delta_max_kib':SWAP_DELTA_KIB,'queue_limit_per_gpu':QUEUE_LIMIT,'compiler_workers':COMPILERS}}
(OUT/'baseline.json').write_text(json.dumps(baseline,indent=2)); allr=[]; last_good=None
for n in LEVELS:
 r=run_stage(n); allr.append(r); (OUT/f'stage-{n}.json').write_text(json.dumps(r,indent=2)); print(json.dumps({'agents':n,'status':r['status'],'correct':r['correct'],'correct_per_min':r['correct_per_min'],'p95':r['p95_latency_s'],'mem_after_kib':r['mem_after_kib'],'swap_delta_kib':r['swap_delta_kib']}),flush=True)
 if r['status']!='PASS':
  break
 last_good=r
 if len(allr)>=2 and r['correct_per_min'] <= allr[-2]['correct_per_min']*1.05:
  r['plateau']=True; break
summary={'stages':allr,'last_known_good':last_good['agents'] if last_good else None,'first_failure':next((r['agents'] for r in allr if r['status']=='FAIL'),None)}
(OUT/'summary.json').write_text(json.dumps(summary,indent=2)); print(json.dumps(summary,indent=2))
