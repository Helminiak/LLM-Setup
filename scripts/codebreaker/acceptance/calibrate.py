import http.server, threading, json, subprocess, time
from pathlib import Path
from urllib.request import Request,urlopen
state=Path.home()/'.local/state/sol-parallel'
class Handler(http.server.BaseHTTPRequestHandler):
 def log_message(self,*args): pass
 def do_GET(self):
  try:
   b=urlopen('http://127.0.0.1:8082'+self.path,timeout=5).read();self.send_response(200);self.end_headers();self.wfile.write(b)
  except Exception:self.send_error(503)
 def do_POST(self):
  b=self.rfile.read(int(self.headers.get('content-length',0)))
  (state/'calibration-request.json').write_bytes(b)
  self.send_response(400);self.send_header('Content-Type','application/json');self.end_headers();self.wfile.write(b'{"error":{"message":"intentional admission calibration; no inference","type":"invalid_request_error"}}')
s=http.server.ThreadingHTTPServer(('127.0.0.1',18084),Handler);threading.Thread(target=s.serve_forever,daemon=True).start()
work=state/'calibration';work.mkdir(exist_ok=True)
cmd=['hermes','-p','gyro-coder-supervisor','chat','--cli','--provider','custom','--base-url','http://127.0.0.1:18084/v1','--model','gyro-coder-l-gpu0','--reasoning','none','--toolsets','terminal,file','--in',str(work),'--oneshot','--max-turns','1','--format','stream-json','-q','CALIBRATION_PLACEHOLDER']
with (state/'calibration.jsonl').open('w') as out,(state/'calibration.err').open('w') as err:
 try: subprocess.run(cmd,stdout=out,stderr=err,timeout=60)
 except subprocess.TimeoutExpired: pass
s.shutdown()
p=json.loads((state/'calibration-request.json').read_text());print('message count',len(p['messages']),'tools',len(p.get('tools',[])))
def post(path,data):return json.load(urlopen(Request('http://127.0.0.1:8082'+path,data=json.dumps(data).encode(),headers={'Content-Type':'application/json'}),timeout=30))
t=post('/apply-template',p)['prompt'];n=len(post('/tokenize',{'content':t})['tokens']);print('actual template overhead tokens',n);(state/'calibration-tokens.json').write_text(json.dumps({'tokens':n}))
