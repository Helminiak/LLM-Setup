import concurrent.futures,json,pathlib,subprocess,time,urllib.request
O=pathlib.Path('/home/joe/dual-5090-20261107-confirm'); O.mkdir(parents=True,exist_ok=True)
P='Return only complete Rust code after thinking, no markdown. Implement fn clamp(x:i32,lo:i32,hi:i32)->i32 and exactly six unit tests for normal values, both boundaries, reversed bounds, and negatives.'
def run(i):
 p=8082 if i%2==0 else 8083
 b=json.dumps({'model':'gyro-coder-l','messages':[{'role':'user','content':P}],'temperature':0,'max_tokens':2048,'timings_per_token':True}).encode()
 q=urllib.request.Request(f'http://127.0.0.1:{p}/v1/chat/completions',data=b,headers={'Content-Type':'application/json'}); t=time.monotonic()
 with urllib.request.urlopen(q,timeout=90) as r:d=json.load(r)
 c=d['choices'][0]['message'].get('content') or d['choices'][0]['message'].get('reasoning_content') or ''
 if '</think>' in c:c=c.split('</think>',1)[1]
 w=O/f'agent-{i}'; w.mkdir(exist_ok=True); (w/'main.rs').write_text(c.replace('```rust','').replace('```','').strip()+'\n'); cp=subprocess.run(['rustc','--test','main.rs','-o','testbin'],cwd=w,capture_output=True); tp=subprocess.run(['./testbin'],cwd=w,capture_output=True) if cp.returncode==0 else None
 return {'agent':i,'gpu':p-8082,'wall_s':time.monotonic()-t,'generated':d.get('usage',{}).get('completion_tokens'),'generation_tps':(d.get('timings') or {}).get('predicted_per_second'),'compile':cp.returncode==0,'tests':bool(tp and tp.returncode==0),'finish':d['choices'][0].get('finish_reason')}
t=time.monotonic()
with concurrent.futures.ThreadPoolExecutor(6) as e:r=list(e.map(run,range(6)))
out={'agents':6,'wall_s':time.monotonic()-t,'correct':sum(x['compile'] and x['tests'] for x in r),'workers':r,'health0':urllib.request.urlopen('http://127.0.0.1:8082/health').status==200,'health1':urllib.request.urlopen('http://127.0.0.1:8083/health').status==200}
(O/'confirmation.json').write_text(json.dumps(out,indent=2)); print(json.dumps(out,indent=2))
