#!/usr/bin/env python3
"""Fail-closed P7 persistent two-model residency runner. Run only on 5090FE."""
import fcntl, hashlib, importlib.util, select, signal, json, os, queue, re, subprocess, sys, tempfile, threading, time, urllib.request, urllib.error, uuid, yaml
from datetime import datetime, timezone
from pathlib import Path

ROOT=Path('/home/joe/.local/state/inference-research/p7-19-2026-11-11')
STATE=Path('/home/joe/.local/state/inference-research'); CLAIM=STATE/'gpu-lease.json'; LOCK=STATE/'gpu-lease.lock'
CONFIG=Path('/home/joe/.config/llama-swap/config.yaml'); GATEWAY='http://127.0.0.1:8080'
LLAMA='/home/joe/src/llama-gyro/build/bin/llama-server'
GPU_UUID={0:'GPU-4c61ea28-b74b-9144-cbab-76ed4b4721ae',1:'GPU-395e0f7a-0ab8-9b1c-46a6-17ad4e293bc1'}
MODELS={
 'qwen3.8-27b-q6':{'path':'/home/joe/models/bakeoff/q27b/Qwen3.8-27B-UD-Q6_K.gguf','sha':'c9c206812fbe4ac7b76a729e25928b63f2ae89d37f69da7a71c20aec763cd436','gpu':0,'port':8086,'ctx':131072,'estimate':28537},
 'qwen3.6-35b-q5':{'path':'/home/joe/models/bakeoff/q35a3b/Qwen3.6-35B-A3B-UD-Q5_K_M.gguf','sha':'c13ce26253ea334df472bd8fbd2d6da66d8a41195c17f6fcbf44c4d20ece0932','gpu':1,'port':8087,'ctx':131072,'estimate':30347},
}
SERVICES=('llama-swap.service','local-qwen.service','hindsight-extract-llm.service','dr100-model.service')
PROTECTED_PORTS=(8080,8082,8084,8091,1235); ALL_PORTS=(*PROTECTED_PORTS,8086,8087)
FLOOR=1024; RESERVE=1024; LEASE_S=1800; RENEW_S=600
CONFIG_SHA=None
ORIGINAL_SHA='92fc615beece108474e96f000f519baf99e9be5ea44b203247fe11507343b1e9'
P4B=Path('/home/joe/.local/state/inference-research/p4b-19-2026-11-11/p4b_runner.py')
CLAIM_MUTEX=threading.RLock()
BASELINE_PROMPT='Explain stable merge sort in Python in exactly four numbered steps. State why equal keys preserve relative order. End with time and auxiliary space complexity.'
class Blocked(RuntimeError): pass
def utc(): return datetime.now(timezone.utc).isoformat()
def run(a,timeout=15):
 p=subprocess.run(a,text=True,capture_output=True,timeout=timeout)
 if p.returncode: raise Blocked(f'{a[0]} failed rc={p.returncode}: {p.stderr[-500:]}')
 return p.stdout.strip()
def digest(path):
 h=hashlib.sha256()
 with open(path,'rb') as f:
  for b in iter(lambda:f.read(1024*1024),b''): h.update(b)
 return h.hexdigest()
def boot(): return Path('/proc/sys/kernel/random/boot_id').read_text().strip()
def ticks(pid): return int(Path(f'/proc/{pid}/stat').read_text().rsplit(')',1)[1].split()[19])
def gpu_rows():
 out=run(['nvidia-smi','--query-gpu=index,uuid,memory.total,memory.free,memory.used','--format=csv,noheader,nounits']); rows=[]
 for line in out.splitlines():
  i,u,total,free,used=[x.strip() for x in line.split(',')]; rows.append({'index':int(i),'uuid':u,'total_mib':int(total),'free_mib':int(free),'used_mib':int(used)})
 if {x['index']:x['uuid'] for x in rows}!=GPU_UUID: raise Blocked('GPU index/UUID mapping drift')
 return rows
def service_snapshot():
 out={}
 for unit in SERVICES:
  props='ActiveState,MainPID,NRestarts'+(',UnitFileState,Result' if unit=='dr100-model.service' else '')
  out[unit]=dict(x.split('=',1) for x in run(['systemctl','--user','show',unit,'--property='+props]).splitlines() if '=' in x)
 return out
def port_snapshot(ports=ALL_PORTS):
 lines=run(['ss','-Hltpn']).splitlines(); out={}
 for port in ports: out[str(port)]=sorted(set(re.findall(r'pid=(\d+)', '\n'.join(x for x in lines if re.search(rf':{port}\s',x)))))
 return out
def proc_rows():
 out=[]
 for d in Path('/proc').iterdir():
  if not d.name.isdigit(): continue
  try:
   argv=[x.decode(errors='replace') for x in (d/'cmdline').read_bytes().split(b'\0') if x]
   if '--alias' not in argv: continue
   alias=argv[argv.index('--alias')+1]; flag='-m' if '-m' in argv else '--model'; path=argv[argv.index(flag)+1]
   env=(d/'environ').read_bytes().split(b'\0'); cvd=next((x.decode().split('=',1)[1] for x in env if x.startswith(b'CUDA_VISIBLE_DEVICES=')),None)
   out.append({'pid':int(d.name),'alias':alias,'path':path,'exe':os.path.realpath(f'/proc/{d.name}/exe'),'cmd':' '.join(argv),'cuda_visible_devices':cvd})
  except (OSError,ValueError,IndexError): pass
 return out
def backend(alias):
 spec=MODELS[alias]; rows=[p for p in proc_rows() if p['alias']==alias]
 if not rows: return None
 if len(rows)!=1: raise Blocked(f'ambiguous process identity for {alias}')
 p=rows[0]
 if p['path']!=spec['path'] or p['exe']!=os.path.realpath(LLAMA): raise Blocked(f'process model/executable mismatch for {alias}')
 socks=[]
 for line in run(['ss','-Hltpn']).splitlines():
  if re.search(rf'pid={p["pid"]}(?:,|\))',line):
   f=line.split()
   if len(f)>=5:
    try: addr,port=f[3].rsplit(':',1); socks.append((addr.strip('[]'),int(port)))
    except ValueError: pass
 if len(set(socks))!=1: return None if not socks else (_ for _ in ()).throw(Blocked(f'ambiguous listener for {alias}: {socks}'))
 addr,port=socks[0]
 if port!=spec['port'] or not(addr.startswith('127.') or addr=='::1'): raise Blocked(f'unsafe/mismatched endpoint {addr}:{port} for {alias}')
 st=Path(f'/proc/{p["pid"]}/stat').read_text().rsplit(')',1)[1].split(); bt=int(next(x.split()[1] for x in Path('/proc/stat').read_text().splitlines() if x.startswith('btime ')))
 return {'pid':p['pid'],'alias':alias,'model_path':p['path'],'executable':p['exe'],'cmd':p['cmd'],'cuda_visible_devices':p['cuda_visible_devices'],'process_start_utc':datetime.fromtimestamp(bt+int(st[19])/os.sysconf('SC_CLK_TCK'),timezone.utc).isoformat(),'endpoint':f'http://{addr}:{port}','port':port}
def getj(url,timeout=4):
 with urllib.request.urlopen(url,timeout=timeout) as r: return r.status,json.loads(r.read())
def wait_model_ids(required,absent=(),timeout=20):
 required=set(required); absent=set(absent); end=time.time()+timeout
 while time.time()<end:
  if service_snapshot()['llama-swap.service'].get('MainPID')!='2456835': raise Blocked('llama-swap PID changed while awaiting config reload')
  try:
   _,obj=getj(GATEWAY+'/models')
   ids={x.get('id') for x in obj.get('data',[])}
   if required<=ids and not (absent&ids): return sorted(x for x in ids if x)
  except Exception: pass
  time.sleep(.25)
 raise Blocked(f'gateway model-list reload timeout; required={sorted(required)}, absent={sorted(absent)}')
def verify(b,alias):
 _,props=getj(b['endpoint']+'/props'); _,models=getj(b['endpoint']+'/v1/models'); _,health=getj(b['endpoint']+'/health')
 ids=[x.get('id') for x in models.get('data',[])]
 if props.get('model_path')!=MODELS[alias]['path'] or alias not in ids: raise Blocked(f'dynamic endpoint identity mismatch: {alias}, props={props}, ids={ids}')
 return {'props_model_path':props.get('model_path'),'v1_models':ids,'health':health}
def gpu_pid_map():
 out=run(['nvidia-smi','--query-compute-apps=gpu_uuid,pid,used_memory','--format=csv,noheader,nounits']); rows=[]
 for x in out.splitlines():
  try: u,p,m=[v.strip() for v in x.split(',')]; rows.append({'gpu_uuid':u,'pid':int(p),'used_mib':int(m)})
  except ValueError: pass
 return rows
def assert_protected(base_services,base_ports,baseline_gpu,check_reserve=True):
 if CONFIG_SHA is not None and digest(CONFIG)!=CONFIG_SHA: raise Blocked('active config drift')
 if service_snapshot()!=base_services: raise Blocked('protected service state/PID/restart drift')
 if port_snapshot(PROTECTED_PORTS)!={str(p):base_ports[str(p)] for p in PROTECTED_PORTS}: raise Blocked('protected service listener drift')
 rows=gpu_rows()
 for r in rows:
  b=next(x for x in baseline_gpu if x['uuid']==r['uuid'])
  if r['free_mib']<FLOOR or (check_reserve and r['free_mib']<b['free_mib']-RESERVE): raise Blocked(f'GPU floor/reserve violated: {r}')
def _write_claim(claim,create=False):
 data=(json.dumps(claim,sort_keys=True,indent=2)+'\n').encode()
 if create: fd=os.open(CLAIM,os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o600)
 else:
  old=json.loads(CLAIM.read_text())
  if old.get('lease_id')!=claim['lease_id']: raise Blocked('lease claim changed')
  fd,tmp=tempfile.mkstemp(prefix='.gpu-lease-',dir=STATE); os.close(fd); os.unlink(tmp); fd=os.open(tmp,os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o600)
  with os.fdopen(fd,'wb') as f: f.write(data); f.flush(); os.fsync(f.fileno())
  os.replace(tmp,CLAIM); fsync_dir(STATE); return
 with os.fdopen(fd,'wb') as f: f.write(data); f.flush(); os.fsync(f.fileno())
 fsync_dir(STATE)
def write_claim(claim,create=False):
 with CLAIM_MUTEX: _write_claim(claim,create)
def fsync_dir(path):
 fd=os.open(path,os.O_RDONLY|os.O_DIRECTORY)
 try: os.fsync(fd)
 finally: os.close(fd)
def durable_new(path,data):
 fd=os.open(path,os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o600)
 with os.fdopen(fd,'wb') as f: f.write(data); f.flush(); os.fsync(f.fileno())
 fsync_dir(path.parent)
def install_bytes(data,expected):
 # Same-directory temporary file guarantees atomic replacement on this filesystem.
 fd,tmp=tempfile.mkstemp(prefix='.p7-config-',dir=CONFIG.parent)
 try:
  with os.fdopen(fd,'wb') as f: f.write(data); f.flush(); os.fsync(f.fileno())
  os.chmod(tmp,0o600)
  if digest(CONFIG)!=expected: raise Blocked('active config changed before atomic replacement')
  os.replace(tmp,CONFIG); fsync_dir(CONFIG.parent)
 finally:
  if os.path.exists(tmp): os.unlink(tmp)
def prepare_config(backup,staged,original_sha):
 original=CONFIG.read_bytes()
 if hashlib.sha256(original).hexdigest()!=original_sha: raise Blocked('config drift before backup')
 durable_new(backup,original)
 if digest(P4B)!='e9f587cf2f952d2fd4045f3d382b9196514d2eb3012a3014faec8edb6926604a': raise Blocked('P4b staging helper hash drift')
 spec=importlib.util.spec_from_file_location('p7_p4b_config',P4B)
 helper=importlib.util.module_from_spec(spec); spec.loader.exec_module(helper)
 helper.STAGED=staged
 staged_sha=helper.staged_config(backup)
 fd=os.open(staged,os.O_WRONLY)
 try: os.fsync(fd)
 finally: os.close(fd)
 fsync_dir(staged.parent)
 if digest(backup)!=original_sha or digest(CONFIG)!=original_sha: raise Blocked('backup/active original hash mismatch')
 return staged_sha
def cleanup(claim,services,ports,baseline_gpu,backup,staged_sha,original_sha,installed):
 global CONFIG_SHA
 errors=[]
 if installed:
  for a,spec in MODELS.items():
   try:
    ps=[p for p in proc_rows() if p['alias']==a]
    if ps:
     if len(ps)!=1 or ps[0]['path']!=spec['path'] or ps[0]['exe']!=os.path.realpath(LLAMA): raise Blocked(f'refusing unload; exact identity mismatch for {a}')
     if digest(CONFIG)!=staged_sha: raise Blocked('config drift; refusing alias unload through changed routing')
     req=urllib.request.Request(GATEWAY+f'/api/models/unload/{a}',data=b'',method='POST')
     with urllib.request.urlopen(req,timeout=90) as r: r.read()
   except Exception as e: errors.append(str(e))
  end=time.time()+90
  while time.time()<end and any(p['alias'] in MODELS for p in proc_rows()): time.sleep(.5)
  remaining=[p for p in proc_rows() if p['alias'] in MODELS]
  if remaining:
   errors.append(f'exact alias process remains after cleanup: {remaining}')
  else:
   try:
    if digest(backup)!=original_sha: raise Blocked('backup hash mismatch; refusing restore')
    if digest(CONFIG)!=staged_sha: raise Blocked('active hash differs from staged; refusing restore')
    install_bytes(backup.read_bytes(),staged_sha)
    CONFIG_SHA=original_sha
    wait_model_ids({'qwen3.8-27b-q6'},{'qwen3.6-35b-q5'},timeout=20)
   except Exception as e: errors.append(str(e))
 CONFIG_SHA=original_sha
 try:
  if digest(CONFIG)!=original_sha: raise Blocked('original config hash not restored')
  end=time.time()+12
  while time.time()<end:
   if service_snapshot()==services and port_snapshot()==ports: break
   time.sleep(.25)
  if service_snapshot()!=services or port_snapshot()!=ports: raise Blocked('protected service/PID or port baseline drift after cleanup')
  rows=gpu_rows()
  for r in rows:
   base=next(x for x in baseline_gpu if x['uuid']==r['uuid'])
   if r['free_mib']<FLOOR or r['free_mib']<base['free_mib']-RESERVE: raise Blocked(f'GPU memory did not recover to baseline: {r} baseline={base}')
 except Exception as e: errors.append(str(e))
 claim.update(status='CLEANUP_FAILED' if errors else 'RELEASED',cleanup_verified=not errors,cleanup_errors=errors,released_utc=None if errors else utc())
 write_claim(claim)
 if errors: raise Blocked('cleanup failed: '+'; '.join(errors))
 print('CLEANUP_VERIFIED lease='+claim['lease_id'],flush=True)
def refuse_claim():
 if not CLAIM.exists(): return
 try:
  old=json.loads(CLAIM.read_text()); ex=old['executor']; pid=int(ex['pid'])
  if ex.get('boot_id')!=boot(): alive=False
  else:
   try: alive=ticks(pid)==int(ex['start_ticks'])
   except FileNotFoundError: alive=False
 except Exception as e: raise Blocked(f'existing lease unreadable/malformed; preserving it: {e}')
 if alive or old.get('status')!='RELEASED' or old.get('cleanup_verified') is not True: raise Blocked(f'existing lease {old.get("lease_id")} is active or not cleanly released')
 archive=STATE/f'gpu-lease.archive.{old["lease_id"]}.json'
 if archive.exists(): raise Blocked(f'lease archive already exists: {archive}')
 os.replace(CLAIM,archive); fsync_dir(STATE)
def check_identity_pair():
 residents={}
 for a in MODELS:
  b=backend(a)
  if not b: raise Blocked(f'{a} has no dynamically verifiable backend process/listener')
  identity=verify(b,a); residents[a]={**b,'identity':identity}
 gm=gpu_pid_map()
 for a,s in MODELS.items():
  hits=[x for x in gm if x['pid']==residents[a]['pid']]
  if not hits or {x['gpu_uuid'] for x in hits}!={GPU_UUID[s['gpu']]}: raise Blocked(f'{a} is not resident exclusively on expected GPU: {hits}')
 return residents,gm
def request(alias,prompt):
 body=json.dumps({'model':alias,'messages':[{'role':'user','content':prompt}],'stream':False,'temperature':0,'top_p':1,'seed':42,'max_tokens':256,'chat_template_kwargs':{'enable_thinking':False}}).encode()
 req=urllib.request.Request(GATEWAY+'/v1/chat/completions',data=body,method='POST',headers={'Content-Type':'application/json'})
 t=time.monotonic()
 with urllib.request.urlopen(req,timeout=600) as r: obj=json.loads(r.read())
 return {'alias':alias,'wall_ms':round((time.monotonic()-t)*1000,1),'usage':obj.get('usage'),'finish_reason':(obj.get('choices') or [{}])[0].get('finish_reason'),'output':((obj.get('choices') or [{}])[0].get('message') or {}).get('content','')}
def lease_loop(claim,fd,parent,services,ports,gpus,monitor_stop):
 deadline=time.time()+LEASE_S; next_renew=time.time()+RENEW_S
 while not monitor_stop.is_set():
  if os.getppid()!=parent[0] or ticks(parent[0])!=parent[1]: raise Blocked('runner parent exited or PID reused')
  if time.time()>=deadline: raise Blocked('lease expired; refusing service')
  assert_protected(services,ports,gpus,check_reserve=False)
  if claim['status']=='RESIDENT': check_identity_pair()
  if time.time()>=next_renew:
   deadline=time.time()+LEASE_S; claim['expires_utc']=datetime.fromtimestamp(deadline,timezone.utc).isoformat(); claim['renewed_utc']=utc(); claim['renewal_count']+=1; write_claim(claim)
   next_renew=time.time()+RENEW_S; print('LEASE_RENEWED '+claim['expires_utc'],flush=True)
  time.sleep(2)
def wait_line(q,stop):
 try: return q.get(timeout=.5)
 except queue.Empty: return None
def main():
 STATE.mkdir(parents=True,exist_ok=True); ROOT.mkdir(parents=True,exist_ok=True)
 if not CONFIG.is_file(): raise Blocked('active llama-swap config absent')
 global CONFIG_SHA
 config_sha=digest(CONFIG); CONFIG_SHA=config_sha;
 if config_sha!=ORIGINAL_SHA: raise Blocked('original active config SHA mismatch')
 before_services=service_snapshot(); before_ports=port_snapshot(); before_gpu=gpu_rows()
 if before_services['dr100-model.service']!={'ActiveState':'inactive','MainPID':'0','NRestarts':'0','UnitFileState':'static','Result':'success'}: raise Blocked('DR100 protected baseline mismatch')
 if before_services['llama-swap.service'].get('MainPID')!='2456835' or before_services['hindsight-extract-llm.service'].get('MainPID')!='1653347' or before_services['hindsight-extract-llm.service'].get('ActiveState')!='active' or before_services['local-qwen.service'].get('ActiveState')!='inactive': raise Blocked('protected service identity/state mismatch')
 if before_ports.get('8080')!=['2456835'] or before_ports.get('8091')!=['1653347'] or before_ports.get('8082') or before_ports.get('1235') or before_ports.get('8084'): raise Blocked('protected listener baseline mismatch')
 for a,s in MODELS.items():
  p=Path(s['path'])
  if not p.is_file() or digest(p)!=s['sha']: raise Blocked(f'incumbent model artifact identity mismatch: {a}')
  row=next(x for x in before_gpu if x['index']==s['gpu'])
  if row['free_mib']<s['estimate']+RESERVE: raise Blocked(f'GPU fit/reserve gate failed for {a}: {row}')
 if any(x['alias'] in (*MODELS,'qwen3.6-35b-q4') for x in proc_rows()): raise Blocked('incumbent alias process already exists before lease')
 for a,s in MODELS.items():
  if before_ports.get(str(s['port'])): raise Blocked(f'incumbent port occupied before lease: {s["port"]}')
 lockfd=os.open(LOCK,os.O_CREAT|os.O_RDWR,0o600)
 try: fcntl.flock(lockfd,fcntl.LOCK_EX|fcntl.LOCK_NB)
 except BlockingIOError: os.close(lockfd); raise Blocked('shared exclusive dual-GPU lease is active')
 refuse_claim(); parent=(os.getppid(),ticks(os.getppid())); pid=os.getpid(); lid=str(uuid.uuid4()); deadline=time.time()+LEASE_S
 claim={'lease_id':lid,'status':'WAITING_GO','owner':{'supervisor':'winter','executor':'P7 #19'},'executor':{'pid':pid,'start_ticks':ticks(pid),'boot_id':boot()},'parent':{'pid':parent[0],'start_ticks':parent[1],'boot_id':boot()},'gpus':[GPU_UUID[0],GPU_UUID[1]],'resources':'exclusive dual-GPU incumbent residency lease','models':{a:{**s,'expected_gpu_uuid':GPU_UUID[s['gpu']]} for a,s in MODELS.items()},'active_config_sha256':config_sha,'started_utc':utc(),'expires_utc':datetime.fromtimestamp(deadline,timezone.utc).isoformat(),'lease_seconds':LEASE_S,'renewal_count':0,'cleanup':'Exact CLEANUP P7 lease=<lease_id> or failure cleanup; unload only exact identity-checked aliases; restore only staged active hash; verify original config and services/ports.'}
 backup=ROOT/f'config.yaml.pre-p7.{lid}'; staged=ROOT/f'config.p7.{lid}.yaml'
 staged_sha=prepare_config(backup,staged,config_sha)
 claim.update(original_config_sha256=config_sha,staged_config_sha256=staged_sha,config_backup=str(backup),staged_config_path=str(staged))
 installed=False; monitor_stop=threading.Event(); runner=None
 write_claim(claim,create=True)
 try:
  token=f'GO P7 lease={lid}'; print(f'WAITING_GO {token}',flush=True)
  go_deadline=time.time()+LEASE_S; next_renew=time.time()+RENEW_S
  while True:
   if time.time()>=go_deadline: raise Blocked('lease expired while waiting for GO')
   ready,_,_=select.select([sys.stdin],[],[],2)
   if ready:
    line=sys.stdin.readline()
    if line.strip()==token: break
    if not line: raise Blocked('stdin closed before GO')
    print('GO token mismatch; still waiting for exact token',flush=True)
   if time.time()>=next_renew:
    go_deadline=time.time()+LEASE_S; claim['expires_utc']=datetime.fromtimestamp(go_deadline,timezone.utc).isoformat(); claim['renewed_utc']=utc(); claim['renewal_count']+=1; write_claim(claim); next_renew=time.time()+RENEW_S; print('LEASE_RENEWED '+claim['expires_utc'],flush=True)
   assert_protected(before_services,before_ports,before_gpu)
   if digest(CONFIG)!=config_sha: raise Blocked('active config drift while waiting for GO')
  claim.update(status='GO_RECEIVED',go_received_utc=utc()); write_claim(claim)
  if digest(CONFIG)!=config_sha: raise Blocked('active config drift before GO')
  assert_protected(before_services,before_ports,before_gpu)
  # Installation is authorized only by the exact GO token above.
  if digest(staged)!=staged_sha: raise Blocked('staged config drift')
  installed=True  # Include replacement/fsync failures in guarded cleanup.
  install_bytes(staged.read_bytes(),config_sha)
  CONFIG_SHA=staged_sha
  claim.update(status='CONFIG_INSTALLED',active_config_sha256=staged_sha,config_installed_utc=utc()); write_claim(claim)
  assert_protected(before_services,before_ports,before_gpu)
  failures=[]
  def guarded_lease_loop():
   try: lease_loop(claim,lockfd,parent,before_services,before_ports,before_gpu,monitor_stop)
   except BaseException as exc: failures.append(exc); print(f'LEASE_MONITOR_FAILED: {type(exc).__name__}: {exc}',file=sys.stderr,flush=True)
  runner=threading.Thread(target=guarded_lease_loop,daemon=True); runner.start()
  # Wait until llama-swap exposes both aliases from the exact staged config before any chat request.
  visible_ids=wait_model_ids(MODELS,timeout=20)
  print('STAGED_ALIASES_VISIBLE '+','.join(a for a in MODELS if a in visible_ids),flush=True)
  # Cold-load sequentially, matching proven P4b order and avoiding config-reload races.
  warm_results={}
  for a in MODELS:
   assert_protected(before_services,before_ports,before_gpu,check_reserve=False)
   warm_results[a]=request(a,BASELINE_PROMPT)
   if failures: raise Blocked(f'lease monitor failed during warmup: {failures[0]}')
  residents,gm=check_identity_pair()
  claim.update(status='RESIDENT',resident_utc=utc()); write_claim(claim)
  print(json.dumps({'status':'BOTH_RESIDENT','lease_id':lid,'models':residents,'gpu_pid_map':gm,'warm_requests':warm_results},indent=2),flush=True)
  q=queue.Queue(); stop=threading.Event()
  def reader():
   for ln in sys.stdin:
    q.put(ln.rstrip('\n'))
   stop.set()
  threading.Thread(target=reader,daemon=True).start()
  while True:
   if failures: raise Blocked(f'lease monitor failed: {failures[0]}')
   cmd=wait_line(q,stop)
   if not cmd:
    if stop.is_set(): raise Blocked('stdin closed while resident lease is active')
    time.sleep(.5); continue
   if cmd==f'CLEANUP P7 lease={lid}':
    print('CLEANUP_ACCEPTED',flush=True)
    return 0
   else: print('IGNORED_COMMAND exact CLEANUP token required',flush=True)
   assert_protected(before_services,before_ports,before_gpu,check_reserve=False); check_identity_pair()
 finally:
  monitor_stop.set()
  if runner is not None: runner.join(timeout=30)
  if runner is not None and runner.is_alive():
   claim.update(status='CLEANUP_FAILED',cleanup_verified=False,cleanup_errors=['monitor did not stop; manual cleanup required']); write_claim(claim)
   raise Blocked('monitor did not stop; refusing concurrent cleanup')
  try: cleanup(claim,before_services,before_ports,before_gpu,backup,staged_sha,config_sha,installed)
  finally: fcntl.flock(lockfd,fcntl.LOCK_UN); os.close(lockfd)
if __name__=='__main__':
 def interrupted(signum,frame): raise Blocked(f'interrupted by signal {signum}')
 signal.signal(signal.SIGTERM,interrupted); signal.signal(signal.SIGINT,interrupted)
 try: raise SystemExit(main())
 except Exception as e:
  print(f'P7 BLOCKED: {type(e).__name__}: {e}',file=sys.stderr,flush=True); raise SystemExit(2)
