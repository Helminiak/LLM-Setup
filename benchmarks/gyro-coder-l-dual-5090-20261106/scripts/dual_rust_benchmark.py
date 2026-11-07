import json, pathlib, subprocess, threading, time, urllib.request

OUT = pathlib.Path('/home/joe/dual-5090-optimization/results/dual-rust-benchmark-20261106')
OUT.mkdir(parents=True, exist_ok=True)
PROMPT = '''BEGIN WITH `struct Task` ON THE FIRST CHARACTER. Output only one complete Rust 2021 source file, no reasoning, no markdown, no `<think>` tags. Implement a line-oriented task tracker with struct Task { id: u32, title: String, done: bool }, parse_tasks(input: &str) -> Vec<Task> for lines id|done|title, complete_task(tasks: &mut [Task], id: u32) -> bool, render_tasks(tasks: &[Task]) -> String, and six unit tests. Standard library only; keep code concise and compilable.'''
results, lock = {}, threading.Lock()
def gpu_snapshot():
    s = subprocess.check_output(['nvidia-smi','--query-gpu=index,utilization.gpu,memory.used,memory.free','--format=csv,noheader'], text=True)
    return s.strip()
def run(name, port):
    body = json.dumps({'model':'gyro-coder-l','messages':[{'role':'system','content':'Answer directly with code. Do not reason.'},{'role':'user','content':PROMPT}], 'temperature':0, 'top_p':0.95, 'top_k':20, 'min_p':0.05, 'max_tokens':1400, 'reasoning_format':'none', 'timings_per_token':True}).encode()
    req = urllib.request.Request(f'http://127.0.0.1:{port}/v1/chat/completions', data=body, headers={'Content-Type':'application/json'})
    t0 = time.monotonic();
    with urllib.request.urlopen(req, timeout=180) as r: data = json.load(r)
    wall = time.monotonic() - t0
    msg = data['choices'][0]['message']; code = msg.get('content') or msg.get('reasoning_content') or ''
    if '</think>' in code: code = code.split('</think>',1)[1]
    code = code.replace('```rust','').replace('```','').strip() + '\n'
    wd = OUT / name; wd.mkdir(exist_ok=True); (wd/'main.rs').write_text(code); (wd/'response.json').write_text(json.dumps(data,indent=2))
    compile_t0=time.monotonic(); cp=subprocess.run(['rustc','--test','main.rs','-o','testbin'],cwd=wd,text=True,capture_output=True); compile_s=time.monotonic()-compile_t0
    tp=subprocess.run(['./testbin'],cwd=wd,text=True,capture_output=True) if cp.returncode==0 else None
    timing=data.get('timings') or {}
    rec={'worker':name,'port':port,'wall_seconds':wall,'prompt_tokens':data.get('usage',{}).get('prompt_tokens'),'generated_tokens':data.get('usage',{}).get('completion_tokens'),'prompt_processing_ms':timing.get('prompt_ms'),'generation_ms':timing.get('predicted_ms'),'prompt_tokens_per_sec':timing.get('prompt_per_second'),'generation_tokens_per_sec':timing.get('predicted_per_second'),'rust_compile':'PASS' if cp.returncode==0 else 'FAIL','rust_tests':'PASS' if tp and tp.returncode==0 else 'FAIL','compile_seconds':compile_s,'test_output':tp.stdout[-1000:] if tp else cp.stderr[-1000:]}
    with lock: results[name]=rec
threads=[threading.Thread(target=run,args=('gpu0',8082)),threading.Thread(target=run,args=('gpu1',8083))]
before=gpu_snapshot(); start=time.monotonic()
for t in threads:t.start()
for t in threads:t.join()
concurrent_wall=time.monotonic()-start; after=gpu_snapshot()
total=sum((r.get('generated_tokens') or 0) for r in results.values())
out={'prompt':PROMPT,'same_parameters':{'temperature':0,'top_p':0.95,'top_k':20,'min_p':0.05,'max_tokens':1100},'concurrent_wall_seconds':concurrent_wall,'aggregate_generated_tokens_per_sec':total/concurrent_wall if concurrent_wall else None,'sum_individual_generation_rates':sum((r.get('generation_tokens_per_sec') or 0) for r in results.values()),'gpu_before':before,'gpu_after':after,'workers':results}
(OUT/'result.json').write_text(json.dumps(out,indent=2)); print(json.dumps(out,indent=2))
