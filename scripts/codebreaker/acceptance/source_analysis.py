"""Real deterministic AST/source audit used by CPU-C alongside inference."""
import ast,hashlib,json
from pathlib import Path
root=Path(__file__).resolve().parents[3]
rows=[]
for p in sorted((root/'scripts').rglob('*.py')):
 tree=ast.parse(p.read_text());rows.append({'path':str(p.relative_to(root)),'sha256':hashlib.sha256(p.read_bytes()).hexdigest(),'functions':sum(isinstance(n,(ast.FunctionDef,ast.AsyncFunctionDef)) for n in ast.walk(tree))})
print(json.dumps({'files':len(rows),'functions':sum(r['functions'] for r in rows),'manifest_sha256':hashlib.sha256(json.dumps(rows,sort_keys=True).encode()).hexdigest()}))
