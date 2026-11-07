#!/usr/bin/env python3
"""Dedicated, persistent engineering controller. No production queue/model lifecycle changes."""
import argparse, concurrent.futures as cf, contextlib, fcntl, hashlib, http.client
import http.server, json, os, signal, subprocess, sys, tempfile, threading, time
from collections import deque
from pathlib import Path
from urllib.request import Request, urlopen
REPO=Path(__file__).resolve().parents[2]
CONFIG=REPO/'configs/parallel-engineering.json'
STATE=Path(os.environ.get('SOL_PARALLEL_STATE','~/.local/state/sol-parallel')).expanduser()
LOG_LOCK=threading.Lock()
INFERENCE_ACTIVE=threading.Event()
def config(): return json.loads(CONFIG.read_text())
def atomic(path,data):
 path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
 fd,name=tempfile.mkstemp(dir=path.parent)
 with os.fdopen(fd,'w') as f:json.dump(data,f,indent=2);f.flush();os.fsync(f.fileno())
 os.replace(name,path)
def event(kind,**kw):
 STATE.mkdir(parents=True,exist_ok=True)
 with LOG_LOCK,(STATE/'events.jsonl').open('a') as f:f.write(json.dumps({'time':time.time(),'event':kind,**kw})+'\n')
@contextlib.contextmanager
def lock(name,blocking=True):
 STATE.mkdir(parents=True,exist_ok=True)
 with (STATE/(name+'.lock')).open('a') as f:
  fcntl.flock(f,fcntl.LOCK_EX|(0 if blocking else fcntl.LOCK_NB))
  try:yield
  finally:fcntl.flock(f,fcntl.LOCK_UN)
def get(port,path):return json.load(urlopen(f'http://127.0.0.1:{port}{path}',timeout=5))
def preflight(cfg):
 errors=[]
 for gpu,g in cfg['gpus'].items():
  try:
   assert get(g['port'],'/health')['status']=='ok'
   props=get(g['port'],'/props')
   assert props['total_slots']==1 and props['default_generation_settings']['n_ctx']==65536
   assert props['model_alias']==f'gyro-coder-l-gpu{gpu}'
  except Exception as e:errors.append(f'GPU {gpu} unavailable or slots mismatch: {type(e).__name__}')
 try:
  free=[int(x) for x in subprocess.check_output(['nvidia-smi','--query-gpu=memory.free','--format=csv,noheader,nounits'],text=True,timeout=5).split()]
  if len(free)!=2 or min(free)<cfg['min_vram_free_mib']:errors.append('VRAM reserve below limit')
  mem=dict(line.split(':',1) for line in Path('/proc/meminfo').read_text().splitlines())
  if int(mem['MemAvailable'].split()[0])<cfg['min_ram_available_mib']*1024:errors.append('RAM reserve below limit')
 except Exception as e:errors.append('resource telemetry unavailable: '+str(e))
 return {'state':'degraded' if errors else 'ready','errors':errors}
class FIFO:
 def __init__(self,limit=32):self.cv=threading.Condition();self.waiters=deque();self.active=False;self.limit=limit
 @contextlib.contextmanager
 def hold(self,timeout=600):
  ticket=object();start=time.monotonic()
  with self.cv:
   if len(self.waiters)>=self.limit:raise RuntimeError('GPU queue full')
   self.waiters.append(ticket)
   while self.active or self.waiters[0] is not ticket:
    remaining=timeout-(time.monotonic()-start)
    if remaining<=0:self.waiters.remove(ticket);self.cv.notify_all();raise TimeoutError('GPU queue timeout')
    self.cv.wait(remaining)
   self.waiters.popleft();self.active=True
  try:yield time.monotonic()-start
  finally:
   with self.cv:self.active=False;self.cv.notify_all()
def proxy_class(gpu,upstream,gate):
 class Handler(http.server.BaseHTTPRequestHandler):
  protocol_version='HTTP/1.0'
  def log_message(self,*a):pass
  def do_GET(self):self.forward()
  def do_POST(self):self.forward()
  def forward(self):
   if self.path not in ('/v1/chat/completions','/v1/completions','/v1/models','/health','/props','/tokenize','/apply-template'):
    self.send_error(404);return
   body=self.rfile.read(int(self.headers.get('Content-Length',0)))
   inference=self.path.endswith(('/chat/completions','/completions'))
   cm=gate.hold() if inference else contextlib.nullcontext(0)
   conn=None;started=False;size=0;tail=b'';payload=None
   try:
    with cm as waited:
     if inference:
      try:
       payload=json.loads(body)
       if payload.get('stream'):
        payload['stream_options']={'include_usage':True}
       payload['cache_prompt']=True
       body=json.dumps(payload).encode()
       # Exact tokenizer accounting on the full rendered chat, not text estimates.
       rendered=json.load(urlopen(Request(f'http://127.0.0.1:{upstream}/apply-template',data=body,headers={'Content-Type':'application/json'}),timeout=30))['prompt']
       n=len(json.load(urlopen(Request(f'http://127.0.0.1:{upstream}/tokenize',data=json.dumps({'content':rendered}).encode(),headers={'Content-Type':'application/json'}),timeout=30))['tokens'])
      except Exception:n=None
      if n is None:
       self.send_error(503,'Cannot verify context capacity');return
      reserve=config()['context_policy']['minimum_generation_and_tool_reserve'] if len(payload.get('messages',[]))<=2 else 4096
      if n>65536-reserve:
       event('context_admission_rejected',gpu=gpu,prompt_tokens=n,remaining_tokens=65536-n)
       self.send_error(422,'Checkpoint and compact required; original source must be preserved');return
      payload['max_tokens']=min(payload.get('max_tokens',8192),65536-n-256)
      body=json.dumps(payload).encode()
      event('inference_start',gpu=gpu,queue_wait_s=waited,prompt_tokens=n)
     INFERENCE_ACTIVE.set() if inference else None
     start=time.monotonic();conn=http.client.HTTPConnection('127.0.0.1',upstream,timeout=600)
     conn.request(self.command,self.path,body,{'Content-Type':'application/json'})
     r=conn.getresponse();self.send_response(r.status);self.send_header('Content-Type',r.getheader('Content-Type','application/json'));self.end_headers();started=True
     while True:
      chunk=r.read1(65536)
      if not chunk:break
      self.wfile.write(chunk);self.wfile.flush();size+=len(chunk);tail=(tail+chunk)[-65536:]
     if inference:
      usage={};timings={}
      for line in tail.decode(errors='replace').splitlines():
       try:
        d=json.loads(line.removeprefix('data: '));usage=d.get('usage') or usage;timings=d.get('timings') or timings
       except (ValueError,AttributeError):pass
      event('inference_end',gpu=gpu,duration_s=time.monotonic()-start,status=r.status,bytes=size,usage=usage,timings=timings)
   except Exception as e:
    event('proxy_error',gpu=gpu,error=type(e).__name__)
    if not started:
     try:self.send_error(503,'Endpoint unavailable or queue exhausted')
     except OSError:pass
   finally:
    if conn:conn.close()
 return Handler
@contextlib.contextmanager
def proxies(cfg):
 servers=[]
 try:
  for gpu,g in cfg['gpus'].items():
   server=http.server.ThreadingHTTPServer(('127.0.0.1',g['proxy_port']),proxy_class(int(gpu),g['port'],FIFO(cfg['queue_limit'])))
   server.daemon_threads=True;threading.Thread(target=server.serve_forever,daemon=True).start();servers.append(server)
  yield
 finally:
  for server in servers:server.shutdown();server.server_close()
def bounded(command,cwd,env,timeout,out,err):
 with open(out,'w') as o,open(err,'w') as e:
  proc=subprocess.Popen(command,cwd=cwd,env=env,stdout=o,stderr=e,start_new_session=True)
  try:return proc.wait(timeout=timeout)
  except (subprocess.TimeoutExpired,KeyboardInterrupt):
   os.killpg(proc.pid,signal.SIGTERM)
   try:proc.wait(timeout=5)
   except subprocess.TimeoutExpired:os.killpg(proc.pid,signal.SIGKILL);proc.wait()
   return 124
class Telemetry:
 def __init__(self):self.stop=threading.Event();self.thread=threading.Thread(target=self.run,daemon=True)
 def __enter__(self):self.thread.start();return self
 def __exit__(self,*a):self.stop.set();self.thread.join(timeout=10)
 def run(self):
  while not self.stop.is_set():
   row={'time':time.time()}
   for name,path in [('cpu','/proc/stat'),('memory','/proc/meminfo'),('swap','/proc/vmstat'),('disk','/proc/diskstats')]:
    try:row[name]=Path(path).read_text()
    except OSError:row[name]=None
   try:row['gpu']=subprocess.check_output(['nvidia-smi','--query-gpu=index,utilization.gpu,memory.used,memory.free,temperature.gpu,power.draw,clocks_event_reasons.active','--format=csv,noheader,nounits'],text=True,timeout=3)
   except Exception:row['gpu']=None
   row['slots']={}
   for gpu,g in config()['gpus'].items():
    try:row['slots'][gpu]=get(g['port'],'/slots')
    except Exception:row['slots'][gpu]=None
   with (STATE/'telemetry.jsonl').open('a') as f:f.write(json.dumps(row)+'\n')
   self.stop.wait(1)
def cpu_job(job,cfg):
 queue=job['queue'];threads=cfg['cpu_queues'][queue]['threads'];cwd=str(Path(job['cwd']).resolve());start=time.monotonic()
 identity=hashlib.sha256(cwd.encode()).hexdigest()[:16]
 if job.get('after_inference_start') and not INFERENCE_ACTIVE.wait(cfg['slice_timeout']):
  return {'status':'failed','error':'inference never started'}
 workspace_lock=lock('workspace-'+identity) if queue=='build' else contextlib.nullcontext()
 with lock('cpu-'+queue),workspace_lock:
  event('cpu_start',id=job['id'],queue=queue,threads=threads,wait_s=time.monotonic()-start)
  env={**os.environ,**{k:str(threads) for k in ('OMP_NUM_THREADS','MAX_JOBS','CMAKE_BUILD_PARALLEL_LEVEL','RAYON_NUM_THREADS','CARGO_BUILD_JOBS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS')}}
  logs=STATE/'cpu';logs.mkdir(exist_ok=True);stem=job['id']+'-'+str(time.time_ns())
  rc=bounded(job['command'],cwd,env,cfg['cpu_timeout'],logs/(stem+'.out'),logs/(stem+'.err'))
  event('cpu_end',id=job['id'],queue=queue,exit=rc)
  return {'status':'complete' if rc==0 else 'failed','exit':rc,'stdout':str(logs/(stem+'.out')),'stderr':str(logs/(stem+'.err'))}
def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def validate(manifest,cfg):
 alljobs=manifest.get('tasks',[])+manifest.get('cpu_jobs',[])
 if len(alljobs)>cfg['queue_limit']:raise ValueError('bounded queue limit exceeded')
 ids=[j['id'] for j in alljobs]
 if len(ids)!=len(set(ids)) or any(not x.replace('-','').replace('_','').isalnum() for x in ids):raise ValueError('invalid or duplicate task ids')
 tasks=manifest.get('tasks',[])
 if len({t['worker'] for t in tasks})!=len(tasks):raise ValueError('one lifecycle per worker')
 if len({str(Path(t['workspace']).resolve()) for t in tasks})!=len(tasks):raise ValueError('workspaces must be isolated')
 for t in tasks:
  if t['worker'] not in cfg['workers']:raise ValueError('unknown worker')
  for k in ('prompt_file','verify_file'):
   if not Path(t[k]).is_file():raise ValueError('missing '+k)
 for j in alljobs:
  if any(d not in ids for d in j.get('depends_on',[])):raise ValueError('unknown dependency')
 seen=set()
 while len(seen)<len(ids):
  ready=[j['id'] for j in alljobs if j['id'] not in seen and set(j.get('depends_on',[]))<=seen]
  if not ready:raise ValueError('dependency cycle')
  seen.update(ready)
def worker(task,cfg):
 w=cfg['workers'][task['worker']];work=Path(task['workspace']).resolve();work.mkdir(parents=True,exist_ok=True)
 logs=STATE/'tasks'/task['id'];logs.mkdir(parents=True,exist_ok=True)
 env={**os.environ,'GYRO_INFERENCE_BASE_URL':f"http://127.0.0.1:{w['proxy_port']}/v1",'GYRO_SLICE_TIMEOUT':str(cfg['slice_timeout']),'GYRO_WORKER_TOOLSETS':cfg['worker_toolsets']}
 feedback=logs/'feedback.txt'
 if feedback.exists():env['GYRO_REVIEW_FEEDBACK']=str(feedback)
 ckpt=work/'continue-worker-checkpoint.json'
 used=json.loads(ckpt.read_text()).get('slices_used',0) if ckpt.exists() else 0
 prompt_path=task['prompt_file']
 dispatch_prompt=logs/'dispatch-prompt.txt'
 if not ckpt.exists():
  policy=(f"Engineering execution policy: you are logical worker {task['worker']} on GPU {w['gpu']}. "
          "Keep changes in your isolated workspace. Route compilation/builds, tests/static checks and deterministic analysis through the shared CPU queues: "
          f"{REPO}/scripts/codebreaker/sol-engineering cpu build|test|analysis --cwd {work} -- COMMAND. "
          "CPU limits are 8/6/6; do not run competing builds in the same directory. Submit source diff, tests, limitations and checkpoint for SOL review; never self-approve. "
          "Use only necessary context; the 50K bundle is stress-test-only.\n")
  dispatch_prompt.write_text(policy+Path(task['prompt_file']).read_text());prompt_path=str(dispatch_prompt)
 elif dispatch_prompt.exists():prompt_path=str(dispatch_prompt)
 cmd=[sys.executable,str(REPO/'scripts/codebreaker/continue-worker.py'),str(work),prompt_path,'--verify-file',task['verify_file'],'--port',str(w['port']),'--profile',cfg['worker_profile'],'--slices',str(used+cfg['slices']),'--turns',str(cfg['turns'])]
 event('worker_start',id=task['id'],worker=task['worker'],gpu=w['gpu'])
 rc=bounded(cmd,REPO,env,cfg['task_timeout'],logs/'controller.out',logs/'controller.err')
 checkpoint=json.loads(ckpt.read_text()) if ckpt.exists() else {}
 diff=subprocess.run(['git','diff','--no-ext-diff','--','*.py'],cwd=work,capture_output=True,text=True,timeout=10)
 patch=diff.stdout
 for p in sorted(work.glob('*.py')):
  untracked=subprocess.run(['git','ls-files','--error-unmatch',p.name],cwd=work,capture_output=True)
  if untracked.returncode:
   patch+=subprocess.run(['git','diff','--no-index','--','/dev/null',str(p)],capture_output=True,text=True).stdout
 (logs/'diff.txt').write_text(patch)
 artifacts={str(p.relative_to(work)):sha(p) for p in work.rglob('*.py') if '.git' not in p.parts}
 atomic(logs/'artifacts.json',artifacts)
 event('worker_end',id=task['id'],worker=task['worker'],exit=rc,session_id=checkpoint.get('session_id'))
 return {'status':'pending_review' if checkpoint.get('technical_status')=='VERIFIED' else 'failed','exit':rc,'checkpoint':str(ckpt),'session_id':checkpoint.get('session_id'),'artifacts':artifacts,'limitations':['Review required; technical tests alone do not accept deliverable']}
def run(manifest_path):
 cfg=config();manifest=json.loads(Path(manifest_path).read_text());validate(manifest,cfg)
 with lock('controller',False):
  pre=preflight(cfg)
  if pre['state']!='ready':print(json.dumps(pre));return 2
  path=STATE/'controller.json';old=json.loads(path.read_text()) if path.exists() else {'tasks':{}}
  jobs=manifest.get('tasks',[])+manifest.get('cpu_jobs',[]);gpuids={t['id'] for t in manifest.get('tasks',[])}
  for t in jobs:
   identity=hashlib.sha256(json.dumps(t,sort_keys=True).encode()).hexdigest()
   if t['id'] in old['tasks'] and old['tasks'][t['id']]['identity']!=identity:raise ValueError('task identity changed: '+t['id'])
   record=old['tasks'].setdefault(t['id'],{'identity':identity,'status':'ready','definition':t})
   if t['id'] in gpuids:
    hashes={'objective_hash':sha(t['prompt_file']),'acceptance_hash':sha(t['verify_file'])}
    for key,value in hashes.items():
     if key in record and record[key]!=value:raise ValueError('checkpoint content changed: '+t['id'])
     record[key]=value
    if record['status'] in ('pending_review','approved'):
     result=cpu_job({'id':'revalidate-'+t['id'],'queue':'test','cwd':t['workspace'],'command':[sys.executable,'-c',"import os,runpy,sys;sys.path.insert(0,os.getcwd());runpy.run_path(sys.argv[1],run_name='__main__')",t['verify_file']]},cfg)
     if result['exit']!=0:record.update(status='failed',error='previous acceptance no longer passes')
   if record['status']=='running':record['status']='recovery_required'
  atomic(path,old);start=time.time();event('run_start',tasks=len(gpuids))
  futures={};pending={t['id']:t for t in jobs if old['tasks'][t['id']]['status']=='ready'}
  with proxies(cfg),Telemetry(),cf.ThreadPoolExecutor(max_workers=7) as pool:
   while pending or futures:
    for id,t in list(pending.items()):
     deps=[old['tasks'][d]['status'] for d in t.get('depends_on',[])]
     if any(d in ('failed','blocked','recovery_required') for d in deps):old['tasks'][id]['status']='blocked';del pending[id];continue
     if not all(d in ('complete','approved') for d in deps):continue
     old['tasks'][id]['status']='running';atomic(path,old)
     futures[pool.submit(worker if id in gpuids else cpu_job,t,cfg)]=id;del pending[id]
    if not futures:break
    done,_=cf.wait(futures,return_when=cf.FIRST_COMPLETED)
    for f in done:
     id=futures.pop(f)
     try:old['tasks'][id].update(f.result())
     except Exception as e:old['tasks'][id].update(status='failed',error=str(e))
     atomic(path,old)
  event('run_end',wall_s=time.time()-start)
  print(json.dumps(old,indent=2));return 0 if all(old['tasks'][t['id']]['status'] in ('complete','pending_review','approved') for t in jobs) else 1
def review(id,disposition,feedback):
 with lock('controller',False):
  path=STATE/'controller.json';state=json.loads(path.read_text());r=state['tasks'][id]
  if r['status']!='pending_review':raise ValueError('deliverable not pending review')
  record={'time':time.time(),'reviewer':'sol','disposition':disposition,'feedback':Path(feedback).read_text() if feedback else ''}
  if disposition!='APPROVED' and not record['feedback'].strip():raise ValueError('correction feedback required')
  r.setdefault('reviews',[]).append(record)
  if disposition=='APPROVED':r['status']='approved'
  else:
   log=STATE/'tasks'/id;log.mkdir(parents=True,exist_ok=True);(log/'feedback.txt').write_text(record['feedback'])
   ckpt=Path(r['checkpoint']);d=json.loads(ckpt.read_text());d['technical_status']='PARTIAL';d['failures']=[record['feedback']];atomic(ckpt,d);r['status']='ready'
  atomic(path,state);event('review',id=id,disposition=disposition)
def recover(id):
 with lock('controller',False):
  path=STATE/'controller.json';state=json.loads(path.read_text());record=state['tasks'][id]
  if record['status']!='failed':raise ValueError('recover requires a settled failed task; inspect in-flight sessions separately')
  task=record['definition'];checkpoint=Path(record['checkpoint']);data=json.loads(checkpoint.read_text())
  result=cpu_job({'id':'recover-'+id,'queue':'test','cwd':task['workspace'],'command':[sys.executable,'-c',"import os,runpy,sys;sys.path.insert(0,os.getcwd());runpy.run_path(sys.argv[1],run_name='__main__')",task['verify_file']]},config())
  if result['exit']!=0:raise ValueError('acceptance still fails; preserve state and diagnose')
  atomic(checkpoint.with_name('recovery-evidence-'+str(time.time_ns())+'.json'),data)
  data.setdefault('recovery_history',[]).append({'time':time.time(),'previous_status':data['technical_status'],'previous_error':data.get('error'),'acceptance':result})
  data['technical_status']='VERIFIED';data['error']=None;data['continue_reason']=None;data['review_state']='pending'
  atomic(checkpoint,data);record.update(status='pending_review',recovery=result);atomic(path,state)
  event('recovery',id=id,technical_status='VERIFIED',review='pending',session_id=data.get('session_id'))


def main():
 p=argparse.ArgumentParser();sub=p.add_subparsers(dest='action',required=True)
 q=sub.add_parser('run');q.add_argument('manifest')
 sub.add_parser('status');sub.add_parser('serve')
 q=sub.add_parser('recover');q.add_argument('id')
 q=sub.add_parser('cpu');q.add_argument('queue',choices=['build','test','analysis']);q.add_argument('--cwd',required=True);q.set_defaults(command=[])
 q=sub.add_parser('review');q.add_argument('id');q.add_argument('disposition',choices=['APPROVED','APPROVED WITH CHANGES','DISAPPROVED — REWORK REQUIRED']);q.add_argument('--feedback-file')
 argv=sys.argv[1:];command=[]
 if argv[:1]==['cpu'] and '--' in argv:
  index=argv.index('--');command=argv[index+1:];argv=argv[:index]
 a=p.parse_args(argv);a.command=command if a.action=='cpu' else None
 os.umask(0o077);STATE.mkdir(parents=True,exist_ok=True)
 if a.action=='run':return run(a.manifest)
 if a.action=='status':print(json.dumps({'resources':preflight(config()),'controller':json.loads((STATE/'controller.json').read_text()) if (STATE/'controller.json').exists() else None},indent=2))
 if a.action=='cpu':
  command=a.command[1:] if a.command[:1]==['--'] else a.command
  if not command:p.error('CPU command required')
  r=cpu_job({'id':'manual-'+str(time.time_ns()),'queue':a.queue,'cwd':a.cwd,'command':command},config());print(json.dumps(r));return r['exit']
 if a.action=='review':review(a.id,a.disposition,a.feedback_file)
 if a.action=='recover':recover(a.id)
 if a.action=='serve':
  with lock('controller',False),proxies(config()),Telemetry():
   print('Dedicated engineering queues ready',flush=True)
   threading.Event().wait()
 return 0
if __name__=='__main__':
 try:sys.exit(main())
 except (ValueError,BlockingIOError) as e:print(str(e),file=sys.stderr);sys.exit(2)
