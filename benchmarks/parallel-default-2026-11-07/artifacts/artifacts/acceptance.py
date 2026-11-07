from artifacts import manifest
from pathlib import Path
import tempfile,hashlib
with tempfile.TemporaryDirectory() as t:
 p=Path(t);(p/'b').mkdir();(p/'b/x').write_bytes(b'abc');(p/'a').write_bytes(b'')
 r=manifest(p)
 assert [x['path'] for x in r]==['a','b/x'],r
 assert r[1]['sha256']==hashlib.sha256(b'abc').hexdigest()
 assert r[1]['bytes']==3
 (p/'link').symlink_to(p/'a')
 try: manifest(p)
 except ValueError: pass
 else: raise AssertionError('symlink')
