"""Replay published source acceptance offline; no model or service changes."""
from pathlib import Path
import subprocess,sys
root=Path(__file__).resolve().parent
commands=[('worker-1',['cargo','fmt','--check']),('worker-1',['cargo','test','--offline']),('worker-2',['python3','-m','unittest','-v'])]
for workspace,command in commands:
 result=subprocess.run(command,cwd=root/workspace,timeout=60)
 print(workspace,command,'exit',result.returncode,flush=True)
 if result.returncode:sys.exit(result.returncode)
