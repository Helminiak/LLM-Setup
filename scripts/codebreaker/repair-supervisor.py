#!/usr/bin/env python3
"""Back up and repair only stale inference routes in the existing Supervisor."""
from pathlib import Path
import datetime, hashlib, json, shutil, os, tempfile
import yaml
home = Path.home()
p = home/'.hermes/profiles/hermes-supervisor/config.yaml'
raw = p.read_text()
cfg = yaml.safe_load(raw)
backup = home/'.local/state/sol-restoration'/datetime.datetime.now(datetime.timezone.utc).strftime('backup-%Y%m%dT%H%M%S%fZ')
backup.mkdir(parents=True, mode=0o700)
shutil.copy2(p, backup/p.name)
# Preserve comments, skills, persona, review, approvals, and production Kanban.
text = raw.replace('http://127.0.0.1:8081/v1', 'http://127.0.0.1:8082/v1').replace('http://127.0.0.1:1235/v1', 'http://127.0.0.1:8082/v1')
text = text.replace('Gyro-L Abliterated', 'gyro-coder-l-gpu0').replace('dr100-gsq-coder-mtp-250k', 'gyro-coder-l-gpu0').replace('context_length: 128000', 'context_length: 65536')
new = yaml.safe_load(text)
for key in ('kanban','approvals','skills','moa','memory','mcp_servers'):
    assert new[key] == cfg[key], key
with tempfile.NamedTemporaryFile(mode='w', dir=p.parent, delete=False) as f:
    f.write(text)
    temp = Path(f.name)
shutil.copymode(p, temp)
os.replace(temp, p)
print(json.dumps({'backup':str(backup),'before_sha256':hashlib.sha256(raw.encode()).hexdigest(),'after_sha256':hashlib.sha256(text.encode()).hexdigest(),'kanban_unchanged':True}))
