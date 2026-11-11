import os, subprocess, tempfile, unittest
from pathlib import Path
import yaml

class RepairTest(unittest.TestCase):
    def test_backup_and_preserved_controls(self):
        script=Path(__file__).with_name('repair-supervisor.py')
        with tempfile.TemporaryDirectory() as temp:
            p=Path(temp)/'.hermes/profiles/hermes-supervisor/config.yaml'; p.parent.mkdir(parents=True)
            cfg={'model':{'base_url':'http://127.0.0.1:8081/v1'},'auxiliary':{'review':{'base_url':'http://127.0.0.1:1235/v1'}},'kanban':{'max_in_progress':1},'approvals':{'mode':'smart'},'skills':{},'moa':{},'memory':{'provider':'hindsight'},'mcp_servers':{}}
            original=yaml.safe_dump(cfg); p.write_text(original); p.chmod(0o600)
            subprocess.run(['python3',str(script)],env={**os.environ,'HOME':temp},check=True,capture_output=True)
            changed=yaml.safe_load(p.read_text())
            self.assertEqual(changed['kanban'],cfg['kanban'])
            self.assertEqual(changed['model']['base_url'],'http://127.0.0.1:8082/v1')
            self.assertEqual(next(Path(temp).glob('.local/state/sol-restoration/backup-*/config.yaml')).read_text(),original)
            self.assertEqual(p.stat().st_mode & 0o777,0o600)
if __name__=='__main__': unittest.main()
