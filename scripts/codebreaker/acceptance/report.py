"""Aggregate sanitized telemetry; unavailable metrics remain explicit."""
import json,time,re
from pathlib import Path
ROOT=Path.home()/'.local/state/sol-parallel'
def rows(path):return [json.loads(s) for s in path.read_text().splitlines() if s.strip()]
def generate():
 events=rows(ROOT/'events.jsonl');start=next(e['time'] for e in events if e['event']=='run_start')
 finish=next((e['time'] for e in events if e['event']=='acceptance_complete'),float('inf'))
 events=[e for e in events if start<=e['time']<=finish];state=json.loads((ROOT/'controller.json').read_text())
 ends=[e for e in events if e['event']=='run_end'];execution_wall=ends[0]['wall_s'] if ends else None
 intervals={0:[],1:[]};pending={};requests=[]
 for e in events:
  if e['event']=='inference_start':pending[e['gpu']]=e
  if e['event']=='inference_end' and e['gpu'] in pending:
   a=pending.pop(e['gpu']);intervals[e['gpu']].append((a['time'],e['time']));requests.append({**a,**e,'start_time':a['time']})
 cpus={};cpu_intervals=[]
 for e in events:
  if e['event']=='cpu_start':cpus[e['id']]=e
  if e['event']=='cpu_end' and e['id'] in cpus:
   a=cpus.pop(e['id']);cpu_intervals.append({'id':e['id'],'queue':a['queue'],'start':a['time'],'end':e['time'],'exit':e['exit'],'threads':a['threads']})
 samples=[r for r in rows(ROOT/'telemetry.jsonl') if start<=r['time']<=finish]
 mem=[];available=[];cpu=[];gpu=[[],[]];powers=[[],[]];temp=[[],[]];throttle=[];swap=[];cores={};iowait=[]
 prev=None
 for r in samples:
  m={x.split(':')[0]:int(x.split(':')[1].strip().split()[0]) for x in r['memory'].splitlines()};mem.append((m['MemTotal']-m['MemAvailable'])/1024);available.append(m['MemAvailable']/1024)
  vm=dict(x.split() for x in r['swap'].splitlines());swap.append([int(vm.get(k,0)) for k in ['pswpin','pswpout']])
  current={x.split()[0]:[int(v) for v in x.split()[1:9]] for x in r['cpu'].splitlines() if x.startswith('cpu')}
  if prev:
   for name,vals in current.items():
    delta=[a-b for a,b in zip(vals,prev[name])];total=sum(delta)
    if total:
     u=100*(total-delta[3]-delta[4])/total
     if name=='cpu':cpu.append(u);iowait.append(100*delta[4]/total)
     else:cores.setdefault(name,[]).append(u)
  prev=current
  for line in (r.get('gpu') or '').splitlines():
   v=[s.strip() for s in line.split(',')];idx=int(v[0]);gpu[idx].append({'util':float(v[1]),'used':float(v[2]),'free':float(v[3])});temp[idx].append(float(v[4]));powers[idx].append(float(v[5]));throttle.append(v[6])
 accepted=sum(r['status']=='approved' for r in state['tasks'].values());last=max([e['time'] for e in events]+[start]);wall=last-start
 usages=[r.get('usage',{}) for r in requests];timings=[r.get('timings',{}) for r in requests]
 generated=sum(u.get('completion_tokens',0) for u in usages);prompt=sum(t.get('prompt_n',0) for t in timings);prompt_s=sum(t.get('prompt_ms',0) for t in timings)/1000;decode_s=sum(t.get('predicted_ms',0) for t in timings)/1000
 worker_starts={};worker_elapsed=[]
 for e in events:
  if e['event']=='worker_start':worker_starts[e['id']]=e['time']
  if e['event']=='worker_end' and e['id'] in worker_starts:worker_elapsed.append(e['time']-worker_starts.pop(e['id']))
 result={'status_by_task':{k:v['status'] for k,v in state['tasks'].items()},'accepted_deliverables':accepted,'execution_wall_s':execution_wall,'acceptance_wall_s':wall,'accepted_per_minute':accepted/(wall/60) if wall else None,'generated_tokens':generated,'generated_tokens_per_wall_second':generated/wall if wall else None,'decode_tokens_per_service_second':generated/decode_s if decode_s else None,'uncached_prompt_tokens':prompt,'prompt_tokens_per_processing_second':prompt/prompt_s if prompt_s else None,'prompt_processing_service_s':prompt_s,'decode_service_s':decode_s,'cache_tokens_observed':sum(u.get('prompt_tokens_details',{}).get('cached_tokens',0) for u in usages),'maximum_requested_prompt_tokens':max((r.get('prompt_tokens') or 0 for r in requests),default=0),'maximum_prompt_tokens':max((r.get('prompt_tokens') or 0 for r in requests if r.get('status')==200),default=0),'rejected_context_requests':[{'gpu':r['gpu'],'tokens':r.get('prompt_tokens'),'status':r['status']} for r in requests if r.get('status',200)>=400],'initial_prompt_tokens_by_gpu':{str(g):[r['prompt_tokens'] for r in requests if r['gpu']==g][:2] for g in (0,1)},'context_high_water_prompt_plus_output':max((u.get('total_tokens',0) for u in usages),default=0),'gpu_queue_wait_total_s':sum(r.get('queue_wait_s',0) for r in requests),'gpu_queue_wait_max_s':max((r.get('queue_wait_s',0) for r in requests),default=0),'average_worker_execution_s':sum(worker_elapsed)/len(worker_elapsed) if worker_elapsed else None,'peak_ram_used_mib':max(mem,default=None),'minimum_memavailable_mib':min(available,default=None),'cpu_mean_percent':sum(cpu)/len(cpu) if cpu else None,'cpu_peak_percent':max(cpu,default=None),'iowait_mean_percent':sum(iowait)/len(iowait) if iowait else None,'per_core_mean_percent':{k:sum(v)/len(v) for k,v in cores.items()},'swap_pages_delta':[swap[-1][i]-swap[0][i] for i in (0,1)] if swap else None,'gpu':{},'cpu_tasks':cpu_intervals,'unavailable':['paid SOL token consumption','exact tool subprocess timings outside shared CPU queues','independent physical throttling confirmation','per-probe health latency'],'observed_throttling_masks':sorted(set(throttle)),'http_errors':[e for e in events if e['event']=='proxy_error' or e.get('status',200)>=400]}
 for g in (0,1):
  occupied=sum(b-a for a,b in intervals[g]);samples_g=gpu[g]
  result['gpu'][str(g)]={'inference_occupied_s':occupied,'inference_idle_s':max(0,wall-occupied),'mean_sampled_util_percent':sum(v['util'] for v in samples_g)/len(samples_g) if samples_g else None,'peak_vram_mib':max((v['used'] for v in samples_g),default=None),'minimum_free_vram_mib':min((v['free'] for v in samples_g),default=None),'peak_temperature_c':max(temp[g],default=None),'peak_power_w':max(powers[g],default=None)}
 active=0;peak=0;gpu_active={0:0,1:0};gpu_peak={0:0,1:0}
 for e in events:
  if e['event']=='worker_start':active+=1;peak=max(peak,active)
  if e['event']=='worker_end':active-=1
  if e['event']=='inference_start':gpu_active[e['gpu']]+=1;gpu_peak[e['gpu']]=max(gpu_peak[e['gpu']],gpu_active[e['gpu']])
  if e['event']=='inference_end':gpu_active[e['gpu']]-=1
 tool_ms={};tool_count={}
 for path in (ROOT/'acceptance').glob('*/slice-*-stdout.jsonl'):
  for item in rows(path):
   if item.get('type')=='tool_result' and isinstance(item.get('duration_ms'),(int,float)):
    name=path.parent.name;tool_ms[name]=tool_ms.get(name,0)+item['duration_ms'];tool_count[name]=tool_count.get(name,0)+1
 result['reported_tool_seconds_by_task']={k:v/1000 for k,v in tool_ms.items()};result['timed_tool_results_by_task']=tool_count
 result['disk_sector_deltas']={}
 if samples:
  def disks(sample):
   return {v[2]:v for line in sample['disk'].splitlines() if (v:=line.split()) and re.fullmatch(r'nvme[0-9]+n[0-9]+',v[2])}
  first,last=disks(samples[0]),disks(samples[-1])
  result['disk_sector_deltas']={k:{'read':int(last[k][5])-int(v[5]),'written':int(last[k][9])-int(v[9])} for k,v in first.items() if k in last}
 result['peak_worker_lifecycles']=peak;result['peak_inference_requests_per_gpu']=gpu_peak
 result['cpu_inference_overlap']={c['id']:any(max(c['start'],a)<min(c['end'],b) for iv in intervals.values() for a,b in iv) for c in cpu_intervals}
 result['three_cpu_queues_simultaneous']=any(max(a['start'],b['start'],c['start'])<min(a['end'],b['end'],c['end']) for a in cpu_intervals for b in cpu_intervals for c in cpu_intervals if len({a['queue'],b['queue'],c['queue']})==3)
 return result
if __name__=='__main__':print(json.dumps(generate(),indent=2))
