import importlib.util,json,tempfile,threading,time,unittest
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch
spec=importlib.util.spec_from_file_location('pe',Path(__file__).with_name('parallel_engineering.py'));pe=importlib.util.module_from_spec(spec);spec.loader.exec_module(pe)
class QueueTests(unittest.TestCase):
 def test_fifo_exclusive(self):
  gate=pe.FIFO();active=0;peak=0;order=[];mutex=threading.Lock()
  def job(i):
   nonlocal active,peak
   with gate.hold():
    with mutex:active+=1;peak=max(peak,active);order.append(i)
    time.sleep(.015)
    with mutex:active-=1
  with gate.hold():
   threads=[]
   for i in range(4):
    t=threading.Thread(target=job,args=(i,));t.start();threads.append(t)
    with gate.cv:gate.cv.wait_for(lambda:len(gate.waiters)==i+1,timeout=1)
  for t in threads:t.join(2)
  self.assertEqual(peak,1);self.assertEqual(order,[0,1,2,3])
 def test_cancelled_waiter_does_not_block_queue(self):
  gate=pe.FIFO()
  def wait():
   with self.assertRaises(TimeoutError):
    with gate.hold(timeout=.01):pass
  with gate.hold():
   t=threading.Thread(target=wait);t.start();t.join(1)
  with gate.hold(timeout=.1):pass
 def test_dag_rejects_cycle(self):
  with self.assertRaisesRegex(ValueError,'cycle'):
   pe.validate({'cpu_jobs':[{'id':'a','depends_on':['b']},{'id':'b','depends_on':['a']} ]},pe.config())
 def test_cpu_queues_overlap_and_limits(self):
  with tempfile.TemporaryDirectory() as temp,patch.object(pe,'STATE',Path(temp)):
   import sys
   jobs=[{'id':q,'queue':q,'cwd':temp,'command':[sys.executable,'-c','import os,time; print(os.environ["OMP_NUM_THREADS"]); time.sleep(.15)']} for q in ['build','test','analysis']]
   start=time.monotonic()
   with ThreadPoolExecutor(max_workers=3) as pool:results=list(pool.map(lambda j:pe.cpu_job(j,pe.config()),jobs))
   self.assertLess(time.monotonic()-start,.44)
   self.assertEqual([Path(r['stdout']).read_text().strip() for r in results],['8','6','6'])
 def test_proxy_serializes_entire_stream_and_refuses_overflow(self):
  import http.server
  from urllib.request import Request,urlopen
  from urllib.error import HTTPError
  counts={'active':0,'peak':0,'tokens':100};mutex=threading.Lock()
  class Upstream(http.server.BaseHTTPRequestHandler):
   def log_message(self,*a):pass
   def do_POST(self):
    self.rfile.read(int(self.headers.get('Content-Length',0)))
    self.send_response(200);self.end_headers()
    if self.path=='/apply-template':self.wfile.write(b'{"prompt":"source"}');return
    if self.path=='/tokenize':self.wfile.write(json.dumps({'tokens':[1]*counts['tokens']}).encode());return
    with mutex:counts['active']+=1;counts['peak']=max(counts['peak'],counts['active'])
    for _ in range(3):self.wfile.write(b'data: {}\n\n');self.wfile.flush();time.sleep(.01)
    with mutex:counts['active']-=1
  upstream=http.server.ThreadingHTTPServer(('127.0.0.1',0),Upstream)
  proxy=http.server.ThreadingHTTPServer(('127.0.0.1',0),pe.proxy_class(0,upstream.server_port,pe.FIFO()))
  for server in (upstream,proxy):threading.Thread(target=server.serve_forever,daemon=True).start()
  def request():
   return urlopen(Request(f'http://127.0.0.1:{proxy.server_port}/v1/chat/completions',data=b'{"messages":[],"stream":true}',headers={'Content-Type':'application/json'}),timeout=3).read()
  try:
   with tempfile.TemporaryDirectory() as temp,patch.object(pe,'STATE',Path(temp)):
    with ThreadPoolExecutor(max_workers=4) as pool:list(pool.map(lambda _:request(),range(4)))
    self.assertEqual(counts['peak'],1)
    counts['tokens']=70000
    with self.assertRaises(HTTPError) as error:request()
    self.assertEqual(error.exception.code,422)
    error.exception.close()
  finally:
   for server in (proxy,upstream):server.shutdown();server.server_close()

 def test_new_task_policy_is_persistent_and_routes_correct_gpu(self):
  with tempfile.TemporaryDirectory() as temp,patch.object(pe,'STATE',Path(temp)/'state'):
   root=Path(temp);work=root/'work';work.mkdir();prompt=root/'objective.txt';prompt.write_text('Implement a utility.')
   verify=root/'verify.py';verify.write_text('pass')
   task={'id':'newtask','worker':'w3','workspace':str(work),'prompt_file':str(prompt),'verify_file':str(verify)}
   captured=[]
   def fake(cmd,cwd,env,timeout,out,err):
    captured.append((cmd,env));pe.atomic(work/'continue-worker-checkpoint.json',{'technical_status':'VERIFIED','session_id':'stable-worker-session','slices_used':1});return 0
   with patch.object(pe,'bounded',side_effect=fake):
    self.assertEqual(pe.worker(task,pe.config())['status'],'pending_review')
    self.assertEqual(pe.worker(task,pe.config())['session_id'],'stable-worker-session')
   forwarded=Path(captured[0][0][3]);self.assertIn('shared CPU queues',forwarded.read_text())
   self.assertIn('Implement a utility.',forwarded.read_text())
   self.assertEqual(captured[0][0][3],captured[1][0][3])
   self.assertEqual(captured[0][1]['GYRO_INFERENCE_BASE_URL'],'http://127.0.0.1:18083/v1')

 def test_cpu_timeout_reaps_owned_process(self):
  import sys,os
  with tempfile.TemporaryDirectory() as temp:
   rc=pe.bounded([sys.executable,'-c','import time; time.sleep(5)'],temp,os.environ,.02,Path(temp)/'out',Path(temp)/'err')
   self.assertEqual(rc,124)

 def test_review_requires_feedback_and_stays_separate(self):
  with tempfile.TemporaryDirectory() as temp,patch.object(pe,'STATE',Path(temp)):
   p=Path(temp);workspace=p/'work';workspace.mkdir();cp=workspace/'continue-worker-checkpoint.json';pe.atomic(cp,{'technical_status':'VERIFIED'})
   pe.atomic(p/'controller.json',{'tasks':{'x':{'status':'pending_review','checkpoint':str(cp)}}})
   with self.assertRaises(ValueError):pe.review('x','DISAPPROVED — REWORK REQUIRED',None)
   f=p/'feedback';f.write_text('Handle malformed input explicitly.')
   pe.review('x','APPROVED WITH CHANGES',str(f))
   self.assertEqual(json.loads((p/'controller.json').read_text())['tasks']['x']['status'],'ready')
   self.assertEqual(json.loads(cp.read_text())['technical_status'],'PARTIAL')
if __name__=='__main__':unittest.main()
