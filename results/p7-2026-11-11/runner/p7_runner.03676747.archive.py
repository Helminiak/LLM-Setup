#!/usr/bin/env python3
"""P7 paired-residency benchmark runner. Do not execute without Winter GO."""
from __future__ import annotations

import ast
import argparse
import concurrent.futures
import fcntl
import hashlib
import importlib.util
import json
import os
import queue
import random
import re
import shutil
import signal
import subprocess
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.request
import uuid
from datetime import datetime, timezone
from pathlib import Path

import yaml

P7ROOT = Path('/home/joe/.local/state/inference-research/p7-19-2026-11-11')
SUITE = P7ROOT / 'p7_suite'
SUITE_V1 = P7ROOT / 'p7_suite_v1'
P4 = Path('/home/joe/.local/state/inference-research/p4-24-2026-11-11')
P4B = Path('/home/joe/.local/state/inference-research/p4b-19-2026-11-11')
STATE = Path('/home/joe/.local/state/inference-research')
CONFIG = Path('/home/joe/.config/llama-swap/config.yaml')
P4B_BACKUP = P4B / 'config.yaml.pre-p4b'
CLAIM = STATE / 'gpu-lease.json'
LOCK = STATE / 'gpu-lease.lock'
RESULT = P7ROOT / 'result.json'
GATEWAY = 'http://127.0.0.1:8080'
LLAMA = '/home/joe/src/llama-gyro/build/bin/llama-server'
SWAP = '/home/joe/.local/opt/llama-swap/v272/llama-swap'
LEASE_SECONDS = 1800
RENEW_BEFORE_SECONDS = 300
FREE_FLOOR_MIB = 1024
CTX = 131072
MAX_TOKENS = 2048
SUPERVISOR = 'winter'
P7_ATTACH_JOB_PROTOCOL = 'suite-v1-job-v1'
ATTACH_JOB_FIELDS = {'schema_version', 'job_id', 'suite_id', 'manifest_sha256', 'task_ids',
                     'seeds', 'streams', 'lease_id', 'created_utc'}
ATTACH_JOB_ID_RE = re.compile(r'^[A-Za-z0-9][A-Za-z0-9_.-]{0,79}$')
ATTACH_TASK_ORDER = ('01_toposort', '02_json_pointer_get', '03_safe_join', '04_retry_delays',
                     '05_pack_batches', '06_lru_trace', '07_redact_secrets',
                     '08_select_nonoverlapping', '09_aggregate_logs', '10_dependency_closure',
                     'merge_intervals', 'parse_records')

TASKS_SHA = ''  # Loaded from the selected pinned suite manifest.
REFERENCE_SHA = ''  # Loaded from the selected pinned suite manifest.
MANIFEST_V2_SHA = 'f705357888003fe37a1d6794857ccae9c55ad57efaab48b6344c9a018104c5f6'
MANIFEST_V1_SHA = 'af1e1c2dbd8376a7b9fbb8cb12494d70e4317a287c92079fd47132834dce48bc'
MANIFEST_SHA = MANIFEST_V2_SHA
VALIDATOR_SHA = ''  # Loaded from the selected pinned suite manifest.
SUITE_README_SHA = ''  # Loaded from the selected pinned suite manifest.
P4_RUNNER_SHA = '7120da691a71dbd1b90709f51a2416a54e2773d192b489fd1f72992e6ef738a1'
P4B_RUNNER_SHA = '8284b9c1df0ae9638f8a446b91b3062586440945f56d54324cc8d537fc2d48a0'
MERGE_ORACLE_SHA = 'e05f5fe05b01c309fba5b7aacb2654e5694ba508baab622f5b50574e1d8f8886'
PARSE_SPEC_SHA = 'c8e6b751b4268c9b8dad6fca683045796d71ba3e6cb75fcba26a43f29cc41730'
PARSE_ORACLE_SHA = '72071bd8461f0093cbb5e19e02b1976a4822661fdc9e4642607e39785a3e1911'
P4_PROMPTS = {
    'merge_intervals': '4a17910b4513d9b7ee63b8104f09fa39838eb3875866d23d594bc7528a5b2bf1',
    'parse_records': 'd4df4dd6b843af9bd232a757adf35924772519da9c4d88ef34f8bb7ef0cb0606',
    'prefill': 'a1e01c6d58a6a6f83a20b208ea5f2059652b1b2ac37fabb4bfc25269841c337d',
}

MODELS = {
    'qwen3.8-27b-q6': {
        'candidate_id': 'qwen3.8-27b-q6', 'path': '/home/joe/models/bakeoff/q27b/Qwen3.8-27B-UD-Q6_K.gguf',
        'sha': 'c9c206812fbe4ac7b76a729e25928b63f2ae89d37f69da7a71c20aec763cd436',
        'gpu_index': 0, 'gpu_uuid': 'GPU-4c61ea28-b74b-9144-cbab-76ed4b4721ae',
        'port': 8086, 'weight_mib': 20966, 'kv_mib': 3475, 'buffer_mib': 4096,
        'legacy_alias': 'qwen3.8-27b-q6',
    },
    'qwen3.6-35b-q5': {
        'candidate_id': 'qwen3.6-35b-q5', 'path': '/home/joe/models/bakeoff/q35a3b/Qwen3.6-35B-A3B-UD-Q5_K_M.gguf',
        'sha': 'c13ce26253ea334df472bd8fbd2d6da66d8a41195c17f6fcbf44c4d20ece0932',
        'gpu_index': 1, 'gpu_uuid': 'GPU-395e0f7a-0ab8-9b1c-46a6-17ad4e293bc1',
        'port': 8087, 'weight_mib': 25231, 'kv_mib': 1020, 'buffer_mib': 4096,
        'legacy_alias': 'qwen3.6-35b-q4',
    },
}
ALIASES = tuple(MODELS)
EXPECTED_GPU_MAP = {0: MODELS[ALIASES[0]]['gpu_uuid'], 1: MODELS[ALIASES[1]]['gpu_uuid']}
SERVICES = (
    'llama-swap.service', 'local-qwen.service',
    'hindsight-extract-llm.service', 'dr100-model.service',
)
PROTECTED_PORTS = (8080, 8082, 8091, 1235)
CANDIDATE_PORTS = (8086, 8087)
PARTIAL_RESULT = None


class Blocked(RuntimeError):
    pass


def utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def digest(path: Path) -> str:
    h = hashlib.sha256()
    with path.open('rb') as f:
        for block in iter(lambda: f.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def digest_text(value: str) -> str:
    return hashlib.sha256(value.encode('utf-8')).hexdigest()


def run(args: list[str], timeout: int = 20) -> str:
    proc = subprocess.run(args, text=True, capture_output=True, timeout=timeout)
    if proc.returncode:
        raise Blocked(f'command failed rc={proc.returncode}: {args[0]}: {proc.stderr[-600:]}')
    return proc.stdout.strip()


def gpu_rows() -> list[dict]:
    raw = run(['nvidia-smi', '--query-gpu=index,uuid,memory.total,memory.free,memory.used',
               '--format=csv,noheader,nounits'])
    rows = []
    for line in raw.splitlines():
        index, ident, total, free, used = [part.strip() for part in line.split(',')]
        rows.append({'index': int(index), 'uuid': ident, 'total_mib': int(total),
                     'free_mib': int(free), 'used_mib': int(used)})
    if {row['index']: row['uuid'] for row in rows} != EXPECTED_GPU_MAP:
        raise Blocked('GPU index/UUID attribution differs from frozen P4b pair')
    return rows


def gpu_pid_map() -> list[dict]:
    raw = run(['nvidia-smi', '--query-compute-apps=gpu_uuid,pid,used_memory',
               '--format=csv,noheader,nounits'])
    rows = []
    for line in raw.splitlines():
        fields = [field.strip() for field in line.split(',')]
        if len(fields) == 3:
            try:
                rows.append({'gpu_uuid': fields[0], 'pid': int(fields[1]), 'used_mib': int(fields[2])})
            except ValueError:
                continue
    return rows


def service_snapshot() -> dict:
    result = {}
    for unit in SERVICES:
        props = 'ActiveState,MainPID,NRestarts'
        if unit == 'dr100-model.service':
            props += ',UnitFileState,Result'
        raw = run(['systemctl', '--user', 'show', unit, '--property=' + props])
        result[unit] = dict(line.split('=', 1) for line in raw.splitlines() if '=' in line)
    return result


def port_snapshot(include_candidates: bool = True) -> dict:
    ports = PROTECTED_PORTS + (CANDIDATE_PORTS if include_candidates else ())
    lines = run(['ss', '-Hltpn']).splitlines()
    result = {}
    for port in ports:
        hits = [line for line in lines if re.search(rf':{port}\s', line)]
        result[str(port)] = sorted(set(re.findall(r'pid=(\d+)', '\n'.join(hits))))
    return result


def process_rows() -> list[dict]:
    rows = []
    for proc in Path('/proc').iterdir():
        if not proc.name.isdigit():
            continue
        try:
            argv = [v.decode(errors='replace') for v in (proc / 'cmdline').read_bytes().split(b'\0') if v]
            if '--alias' not in argv:
                continue
            alias = argv[argv.index('--alias') + 1]
            model_flag = '-m' if '-m' in argv else '--model' if '--model' in argv else None
            if model_flag is None:
                continue
            model_path = argv[argv.index(model_flag) + 1]
            env = (proc / 'environ').read_bytes().split(b'\0')
            visible = next((v.decode(errors='replace').split('=', 1)[1]
                            for v in env if v.startswith(b'CUDA_VISIBLE_DEVICES=')), None)
            stat = (proc / 'stat').read_text().rsplit(')', 1)[1].split()
            rows.append({'pid': int(proc.name), 'start_ticks': int(stat[19]), 'alias': alias,
                         'path': model_path, 'exe': os.path.realpath(f'/proc/{proc.name}/exe'),
                         'cuda_visible_devices': visible, 'cmd': ' '.join(argv)})
        except (OSError, ValueError, IndexError):
            continue
    return rows


def exact_processes(alias: str) -> list[dict]:
    spec = MODELS[alias]
    return [p for p in process_rows() if p['alias'] == alias and p['path'] == spec['path']
            and p['exe'] == os.path.realpath(LLAMA)]


def all_pair_processes() -> dict:
    found = {}
    for alias in ALIASES:
        rows = exact_processes(alias)
        if len(rows) > 1:
            raise Blocked(f'ambiguous exact backend processes for {alias}')
        found[alias] = rows[0] if rows else None
    return found


def endpoint_for(proc: dict) -> dict | None:
    lines = run(['ss', '-Hltpn']).splitlines()
    sockets = []
    for line in lines:
        if not re.search(rf'pid={proc["pid"]}(?:,|\))', line):
            continue
        fields = line.split()
        if len(fields) < 5:
            continue
        try:
            addr, port = fields[3].rsplit(':', 1)
            sockets.append((addr.strip('[]'), int(port)))
        except ValueError:
            continue
    sockets = sorted(set(sockets))
    if not sockets:
        return None
    if len(sockets) != 1:
        raise Blocked(f'backend PID {proc["pid"]} owns ambiguous listeners {sockets}')
    address, port = sockets[0]
    spec = MODELS[proc['alias']]
    if port != spec['port'] or not (address.startswith('127.') or address == '::1'):
        raise Blocked(f'backend socket mismatch for {proc["alias"]}: {address}:{port}')
    if port == 8080 or port in (8091, 1235):
        raise Blocked('resolved backend collided with a protected service')
    hz = os.sysconf('SC_CLK_TCK')
    ticks = proc['start_ticks']
    btime = int(next(line.split()[1] for line in Path('/proc/stat').read_text().splitlines()
                     if line.startswith('btime ')))
    started = btime + ticks / hz
    return {'pid': proc['pid'], 'start_ticks': ticks, 'alias': proc['alias'],
            'model_path': proc['path'], 'artifact_sha256': spec['sha'],
            'executable': proc['exe'], 'command': proc['cmd'],
            'cuda_visible_devices': proc['cuda_visible_devices'],
            'process_start_utc': datetime.fromtimestamp(started, timezone.utc).isoformat(),
            'address': address, 'port': port, 'endpoint': f'http://{address}:{port}'}


def get_json(url: str, timeout: int = 4) -> tuple[int, dict]:
    with urllib.request.urlopen(url, timeout=timeout) as response:
        return response.status, json.loads(response.read())


def verify_backend(alias: str, backend: dict) -> dict:
    status, props = get_json(backend['endpoint'] + '/props')
    if status != 200 or props.get('model_path') != MODELS[alias]['path']:
        raise Blocked(f'{alias} /props model path mismatch')
    reported_alias = props.get('model_alias') or props.get('alias')
    if reported_alias and reported_alias != alias:
        raise Blocked(f'{alias} /props alias mismatch: {reported_alias}')
    _, models = get_json(backend['endpoint'] + '/v1/models')
    ids = [item.get('id') for item in models.get('data', [])]
    if alias not in ids:
        raise Blocked(f'{alias} direct backend /v1/models identity mismatch')
    _, health = get_json(backend['endpoint'] + '/health')
    return {'model_path': props.get('model_path'), 'model_alias': reported_alias or alias,
            'v1_model_ids': ids, 'props_keys': sorted(props), 'health': health,
            'context': {k: v for k, v in props.items() if 'ctx' in k.lower()}}


def gateway_status(alias: str) -> str:
    _, data = get_json(GATEWAY + '/v1/models')
    for item in data.get('data', []):
        if item.get('id') == alias:
            return (item.get('status') or {}).get('value', 'unknown')
    raise Blocked(f'alias {alias} absent from llama-swap gateway model list')


def check_suite_and_p4(selected_task_ids: set[str] | None = None,
                       suite_v1: bool = False) -> tuple[dict, dict, object, object, str, str, str]:
    global TASKS_SHA, REFERENCE_SHA, VALIDATOR_SHA, SUITE_README_SHA, SUITE, MANIFEST_SHA
    SUITE = SUITE_V1 if suite_v1 else P7ROOT / 'p7_suite'
    MANIFEST_SHA = MANIFEST_V1_SHA if suite_v1 else MANIFEST_V2_SHA
    required = {
        SUITE / 'manifest.json': MANIFEST_SHA,
        P4 / 'p4_runner.py': P4_RUNNER_SHA,
        P4B / 'p4b_runner.py': P4B_RUNNER_SHA,
        P4 / 'oracle_reference.py': MERGE_ORACLE_SHA,
        P4 / 'heldout_parse_spec.txt': PARSE_SPEC_SHA,
        P4 / 'heldout_parse_reference.py': PARSE_ORACLE_SHA,
    }
    for path, expected in required.items():
        if not path.is_file() or digest(path) != expected:
            raise Blocked(f'frozen artifact SHA mismatch or missing: {path}')
    manifest = json.loads((SUITE / 'manifest.json').read_text(encoding='utf-8'))
    expected_version = 1 if suite_v1 else 2
    expected_count = 10 if suite_v1 else 12
    if (manifest.get('version') != expected_version or manifest.get('status') != 'ORACLE_PREVALIDATED'
            or (suite_v1 and manifest.get('revision') != 1)):
        raise Blocked(f'P7 suite manifest must be the pinned ORACLE_PREVALIDATED v{expected_version} manifest')
    TASKS_SHA = manifest.get('tasks_file_sha256', '')
    REFERENCE_SHA = manifest.get('reference_file_sha256', '')
    VALIDATOR_SHA = manifest.get('validator_file_sha256', '')
    SUITE_README_SHA = manifest.get('readme_file_sha256', '')
    suite_files = {
        SUITE / 'tasks.json': TASKS_SHA,
        SUITE / 'reference.py': REFERENCE_SHA,
        SUITE / 'validate.py': VALIDATOR_SHA,
        SUITE / 'README.md': SUITE_README_SHA,
    }
    if not all(expected and path.is_file() and digest(path) == expected
               for path, expected in suite_files.items()):
        raise Blocked(f'current v{expected_version} suite files do not match hashes declared by the pinned manifest')
    tasks_data = json.loads((SUITE / 'tasks.json').read_text(encoding='utf-8'))
    if tasks_data.get('version') != expected_version or len(tasks_data.get('tasks', [])) != expected_count:
        raise Blocked('frozen P7 task count or manifest binding changed')
    protocol = manifest.get('retry_protocol', {})
    if (protocol.get('seeds') != [42, 43, 44] or protocol.get('attempts_per_task') != 3
            or protocol.get('run_all_three_even_after_early_acceptance') is not True
            or protocol.get('same_prompt_bytes_every_attempt') is not True):
        raise Blocked(f'current v{expected_version} manifest retry protocol does not match runner behavior')
    by_id = {entry['id']: entry for entry in manifest['tasks']}
    if len(by_id) != expected_count:
        raise Blocked('P7 manifest task identities are not unique')
    for task in tasks_data['tasks']:
        entry = by_id.get(task['id'])
        if not entry or digest_text(task['prompt']) != entry['prompt_sha256'] or digest_text(task['spec']) != entry['spec_sha256']:
            raise Blocked(f'frozen P7 prompt/spec mismatch for {task.get("id")}')
    ref_spec = importlib.util.spec_from_file_location('p7_reference', SUITE / 'reference.py')
    ref = importlib.util.module_from_spec(ref_spec)
    assert ref_spec and ref_spec.loader
    ref_spec.loader.exec_module(ref)
    p4_tree = ast.parse((P4 / 'p4_runner.py').read_text(encoding='utf-8'))
    wanted = {'FIXED_PROMPT', 'HELDOUT_PROMPT', 'PREFILL_BLOCK', 'PREFILL_PROMPT'}
    nodes = [node for node in p4_tree.body if isinstance(node, ast.Assign)
             and any(isinstance(target, ast.Name) and target.id in wanted for target in node.targets)]
    p4_constants: dict = {}
    exec(compile(ast.Module(body=nodes, type_ignores=[]), '<frozen-p4-prompts>', 'exec'), p4_constants)
    merge_prompt = p4_constants['HELDOUT_PROMPT']
    parse_spec = (P4 / 'heldout_parse_spec.txt').read_text(encoding='utf-8')
    parse_prompt = 'Implement the following frozen specification exactly. Return Python source only; no Markdown.\n\n' + parse_spec
    prefill_prompt = p4_constants['PREFILL_PROMPT']
    prompt_checks = {'13_merge_intervals': ('merge_intervals', merge_prompt),
                     '14_parse_records': ('parse_records', parse_prompt)}
    selected_prompts = selected_p4_prompt_ids(selected_task_ids)
    for name, prompt in [prompt_checks[task_id] for task_id in sorted(selected_prompts)] + [('prefill', prefill_prompt)]:
        if digest_text(prompt) != P4_PROMPTS[name]:
            raise Blocked(f'P4 frozen {name} prompt hash mismatch')
    merge_spec = 'Frozen prompt and independent oracle in P4 oracle_reference.py.'
    extra = [
        {'id': '13_merge_intervals', 'kind': 'coding', 'function': 'merge_intervals(intervals)',
         'spec': merge_spec, 'prompt': merge_prompt, 'oracle_id': 'P4 oracle_reference.py'},
        {'id': '14_parse_records', 'kind': 'coding', 'function': 'parse_records(text)',
         'spec': parse_spec, 'prompt': parse_prompt, 'oracle_id': 'P4 heldout_parse_reference.py'},
    ]
    merge_mod_spec = importlib.util.spec_from_file_location('p4_merge_reference', P4 / 'oracle_reference.py')
    merge_ref = importlib.util.module_from_spec(merge_mod_spec)
    assert merge_mod_spec and merge_mod_spec.loader
    merge_mod_spec.loader.exec_module(merge_ref)
    parse_mod_spec = importlib.util.spec_from_file_location('p4_parse_reference', P4 / 'heldout_parse_reference.py')
    parse_ref = importlib.util.module_from_spec(parse_mod_spec)
    assert parse_mod_spec and parse_mod_spec.loader
    parse_mod_spec.loader.exec_module(parse_ref)
    # Pin the exact P4 oracle modules in the restricted sandbox at /p4.
    return tasks_data, manifest, ref, (merge_ref, parse_ref), merge_prompt, parse_prompt, prefill_prompt


def oracle_precheck(ref, p4refs) -> dict:
    merge_ref, parse_ref = p4refs
    assert merge_ref.merge_intervals([[1, 4], [4, 5]]) == [[1, 5]]
    assert parse_ref.parse_records('1|Name|000.00') == [{'id': 1, 'name': 'Name', 'score': 0.0}]
    call = lambda name, arguments: {'name': name, 'arguments': arguments}
    good = [call('inventory', {}), call('quote', {'item': 'sensor', 'quantity': 2}),
            call('quote', {'item': 'actuator', 'quantity': 1}), call('reserve', {'item': 'sensor', 'quantity': 2}),
            call('reserve', {'item': 'actuator', 'quantity': 1}),
            call('commit', {'reservation_ids': ['r-sensor', 'r-actuator']})]
    expected_results = [
        {'stock': {'sensor': 3, 'actuator': 2}},
        {'item': 'sensor', 'quantity': 2, 'unit_price': 10, 'available': 3},
        {'item': 'actuator', 'quantity': 1, 'unit_price': 15, 'available': 2},
        {'reservation_id': 'r-sensor', 'item': 'sensor', 'quantity': 2},
        {'reservation_id': 'r-actuator', 'item': 'actuator', 'quantity': 1},
        {'committed': True, 'total_cost': 35},
    ]
    good_result = ref.simulate_order_calls(good)
    if not good_result['committed'] or good_result['tool_results'] != expected_results:
        raise Blocked('P7 tool oracle exact-state transition precheck failed')
    invalid = [
        [good[1]], [good[0], good[1], good[3]],
        [good[0], call('quote', {'item': 'sensor', 'quantity': 99})],
        [good[0], good[1], good[1]],
        [good[0], good[1], good[2], call('reserve', {'item': 'sensor', 'quantity': 1})],
        [good[0], good[1], good[2], good[5]],
        [good[0], good[1], good[2], good[3], good[5]],
        good + [good[5]], [good[0], call('unknown', {})],
    ]
    rejected = 0
    for sequence in invalid:
        try:
            ref.simulate_order_calls(sequence)
        except ValueError:
            rejected += 1
    if rejected != 9:
        raise Blocked('P7 tool oracle did not reject all nine invalid/incomplete sequences')
    if ref.simulate_order_calls(good[:-1])['committed']:
        raise Blocked('P7 tool oracle accepted an incomplete order')
    return {'merge_touching_case': True, 'parse_ascii_spec_case': True,
            'tool_valid_exact_results': 6, 'tool_invalid_sequences_rejected': rejected,
            'tool_incomplete_rejected': True}


def p4b_config_bytes(original_text: str) -> bytes:
    config = yaml.safe_load(original_text)
    models = config['models']
    q27 = models['qwen3.8-27b-q6']
    q27.update(
        name='P4b Qwen3.8-27B Q6 GPU0',
        description='P4b pinned GPU0, single-GPU residency',
        cmd=f'/usr/bin/env CUDA_VISIBLE_DEVICES=0 {LLAMA} -m {MODELS["qwen3.8-27b-q6"]["path"]} --alias qwen3.8-27b-q6 --n-gpu-layers 999 --split-mode none --main-gpu 0 --device CUDA0 --flash-attn on --ctx-size 131072 --cache-type-k q8_0 --cache-type-v q8_0 --parallel 1 --jinja --host 127.0.0.1 --port 8086',
        proxy='http://127.0.0.1:8086', checkEndpoint='/health', ttl=0, unloadTimeout=15)
    q35 = models.pop('qwen3.6-35b-q4')
    q35.update(
        name='P4b Qwen3.6-35B-A3B Q5_K_M GPU1',
        description='P4b explicit Q5_K_M substitution; Q4_K_XL path absent in configured bakeoff directory',
        cmd=f'/usr/bin/env CUDA_VISIBLE_DEVICES=1 {LLAMA} -m {MODELS["qwen3.6-35b-q5"]["path"]} --alias qwen3.6-35b-q5 --n-gpu-layers 999 --split-mode none --main-gpu 0 --device CUDA0 --flash-attn on --ctx-size 131072 --cache-type-k q8_0 --cache-type-v q8_0 --parallel 1 --jinja --host 127.0.0.1 --port 8087',
        proxy='http://127.0.0.1:8087', checkEndpoint='/health', ttl=0, unloadTimeout=15)
    models['qwen3.6-35b-q5'] = q35
    config['routing'] = {'router': {'use': 'group', 'settings': {'groups': {
        'p4b-dual-residency': {'persistent': True, 'swap': False, 'exclusive': False,
                               'members': ['qwen3.8-27b-q6', 'qwen3.6-35b-q5']}}}}}
    return yaml.safe_dump(config, sort_keys=False).encode('utf-8')


def service_baseline_check(services: dict, ports: dict) -> None:
    expected = {
        'llama-swap.service': ('active', '2456835'),
        'local-qwen.service': ('inactive', '0'),
        'hindsight-extract-llm.service': ('active', '1653347'),
        'dr100-model.service': ('inactive', '0'),
    }
    for unit, (active, pid) in expected.items():
        row = services.get(unit, {})
        if row.get('ActiveState') != active or row.get('MainPID') != pid:
            raise Blocked(f'P4b protected service baseline mismatch: {unit} {row}')
    dr = services['dr100-model.service']
    if dr.get('NRestarts') != '0' or dr.get('UnitFileState') != 'static' or dr.get('Result') != 'success':
        raise Blocked(f'DR100 protected service state mismatch: {dr}')
    if ports.get('8080') != ['2456835'] or ports.get('8091') != ['1653347']:
        raise Blocked(f'gateway or Hindsight protected PID mismatch: {ports}')
    for port in ('8082', '1235'):
        if ports.get(port):
            raise Blocked(f'protected port {port} unexpectedly has a listener')


def preflight(tasks_data, p4refs) -> dict:
    gpu = gpu_rows()
    services = service_snapshot()
    ports = port_snapshot()
    service_baseline_check(services, ports)
    if any(ports.get(str(port)) for port in CANDIDATE_PORTS):
        raise Blocked('P4b candidate ports :8086/:8087 must be unoccupied before run')
    if digest(CONFIG) != '92fc615beece108474e96f000f519baf99e9be5ea44b203247fe11507343b1e9':
        raise Blocked('active llama-swap config differs from the P4b-reviewed baseline')
    if not P4B_BACKUP.is_file() or digest(P4B_BACKUP) != digest(CONFIG):
        raise Blocked('P4b protected config backup is missing or does not match active config')
    staged = p4b_config_bytes(CONFIG.read_text(encoding='utf-8'))
    if hashlib.sha256(staged).hexdigest() != '5a0a01c5d4060db1c20731c7bce5804e3628d22e9c2d3ffd2c222065e0b0696a':
        raise Blocked('reconstructed P4b staged configuration SHA differs from reviewed artifact')
    # Validate candidate aliases and build the staged document only in memory here.
    original_text = CONFIG.read_text(encoding='utf-8')
    for alias, spec in MODELS.items():
        if not Path(spec['path']).is_file() or digest(Path(spec['path'])) != spec['sha']:
            raise Blocked(f'exact candidate artifact SHA mismatch: {alias}')
        row = next(g for g in gpu if g['index'] == spec['gpu_index'])
        required = spec['weight_mib'] + spec['kv_mib'] + spec['buffer_mib'] + FREE_FLOOR_MIB
        if row['free_mib'] < required:
            raise Blocked(f'P4b fit gate fails for {alias}: free={row["free_mib"]}, required={required}')
        if alias not in original_text and spec['legacy_alias'] not in original_text:
            raise Blocked(f'no frozen config entry available to stage exact alias {alias}')
    if all_pair_processes() != {a: None for a in ALIASES}:
        raise Blocked('one or more exact P4b candidate processes already exist')
    if any(proc['alias'] in ALIASES for proc in process_rows()):
        raise Blocked('candidate alias is already running with a non-pinned model path or executable')
    for alias, spec in MODELS.items():
        configured_alias = alias if alias in original_text else spec['legacy_alias']
        if gateway_status(configured_alias) != 'unloaded':
            raise Blocked(f'{configured_alias} is not unloaded before P7 lease')
    sandbox_smoke()
    return {'gpus': gpu, 'services': services, 'ports': ports,
            'config_sha256': digest(CONFIG), 'staged_config_sha256': hashlib.sha256(staged).hexdigest(),
            'candidate_artifacts': {a: {'path': m['path'], 'sha256': m['sha'],
                                        'gpu_index': m['gpu_index'], 'gpu_uuid': m['gpu_uuid'],
                                        'port': m['port'], 'context': CTX}
                                   for a, m in MODELS.items()},
            'suite_task_count': len(tasks_data['tasks']) + 2}


def sandbox_smoke() -> None:
    bwrap = shutil.which('bwrap')
    if not bwrap or not Path('/usr/bin/python3').exists():
        raise Blocked('bubblewrap or /usr/bin/python3 absent')
    proc = subprocess.run([bwrap, '--unshare-all', '--die-with-parent', '--new-session',
                           '--ro-bind', '/usr', '/usr', '--ro-bind', '/lib', '/lib',
                           '--ro-bind', '/lib64', '/lib64', '--ro-bind', '/etc', '/etc', '--dev', '/dev',
                           '--proc', '/proc', '--tmpfs', '/tmp', '--chdir', '/tmp',
                           '/usr/bin/python3', '-I', '-c', "print('p7-sandbox-ok')"],
                          text=True, capture_output=True, timeout=12)
    if proc.returncode or proc.stdout.strip() != 'p7-sandbox-ok':
        raise Blocked(f'bubblewrap network isolation smoke check failed: {proc.stderr[-400:]}')


def fsync_dir(path: Path) -> None:
    fd = os.open(path, os.O_RDONLY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def write_json_atomic(path: Path, value: dict, mode: int = 0o600) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(prefix='.' + path.name + '.', dir=path.parent)
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as stream:
            json.dump(value, stream, ensure_ascii=False, sort_keys=True, indent=2)
            stream.write('\n'); stream.flush(); os.fsync(stream.fileno())
        os.chmod(temp_name, mode)
        os.replace(temp_name, path)
        fsync_dir(path.parent)
    finally:
        if os.path.exists(temp_name):
            os.unlink(temp_name)


class Lease:
    def __init__(self, lock_fd: int, parent: tuple[int, int], claim: dict, p4_module):
        self.lock_fd = lock_fd
        self.parent = parent
        self.claim = claim
        self.p4 = p4_module
        self.deadline = datetime.fromisoformat(claim['expires_utc']).timestamp()
        self.claim_lock = threading.Lock()
        self.renew_enabled = False
        self.stop = threading.Event()
        self.violations: list[str] = []
        self.peak = {g['uuid']: g['used_mib'] for g in gpu_rows()}
        self.minfree = {g['uuid']: g['free_mib'] for g in gpu_rows()}
        self.latest_gpu_pid_map: list[dict] = []
        self.pair_resident = False
        self.config_active = False
        self.cleanup_mode = False
        self.last_protected_check = 0.0
        self.thread = threading.Thread(target=self.sample, name='p7-lease-monitor', daemon=True)

    def start(self):
        self.thread.start()

    def renew_if_needed(self):
        with self.claim_lock:
            if not self.renew_enabled or time.time() < self.deadline - RENEW_BEFORE_SECONDS:
                return
            new_deadline = time.time() + LEASE_SECONDS
            self.claim['expires_utc'] = datetime.fromtimestamp(new_deadline, timezone.utc).isoformat()
            self.claim['renewed_utc'] = utc()
            self.claim['renewal_count'] = int(self.claim.get('renewal_count', 0)) + 1
            self.p4.write_claim(self.claim)
            self.deadline = new_deadline

    def update_claim(self, **fields):
        with self.claim_lock:
            self.claim.update(fields)
            self.p4.write_claim(self.claim)

    def check(self):
        if time.time() >= self.deadline:
            raise Blocked('P4b-protected lease expired before renewal')
        if os.getppid() != self.parent[0]:
            raise Blocked('runner parent exited')
        try:
            if self.p4.ticks(self.parent[0]) != self.parent[1]:
                raise Blocked('runner parent PID identity changed')
        except OSError as exc:
            raise Blocked(f'runner parent is gone: {exc}')
        self.renew_if_needed()
        if self.violations:
            raise Blocked(self.violations[0])

    def sample(self):
        while not self.stop.wait(1.0):
            try:
                self.renew_if_needed()
                rows = gpu_rows()
                for row in rows:
                    ident = row['uuid']
                    self.peak[ident] = max(self.peak.get(ident, row['used_mib']), row['used_mib'])
                    self.minfree[ident] = min(self.minfree.get(ident, row['free_mib']), row['free_mib'])
                    if row['free_mib'] < FREE_FLOOR_MIB:
                        raise Blocked(f'GPU free memory below 1 GiB floor: {ident} {row["free_mib"]} MiB')
                now = time.monotonic()
                if now - self.last_protected_check >= 3:
                    current_services = service_snapshot()
                    ports = port_snapshot()
                    service_baseline_check(current_services, ports)
                    procs = all_pair_processes()
                    for alias, port in zip(ALIASES, CANDIDATE_PORTS):
                        pids = ports.get(str(port), [])
                        proc = procs[alias]
                        if not self.config_active and pids:
                            raise Blocked(f'candidate listener :{port} appeared before staged config')
                        if self.pair_resident and not pids:
                            raise Blocked(f'resident candidate listener :{port} disappeared')
                        if pids and (proc is None or pids != [str(proc['pid'])]):
                            raise Blocked(f'candidate listener :{port} has unexpected PID {pids}')
                        if self.config_active and not self.cleanup_mode and pids and proc is None:
                            raise Blocked(f'candidate listener :{port} has no exact backend process')
                    self.last_protected_check = now
                if self.pair_resident:
                    procs = all_pair_processes()
                    if any(procs[a] is None for a in ALIASES):
                        raise Blocked('one exact P4b backend process disappeared during residency')
                    mapping = gpu_pid_map()
                    self.latest_gpu_pid_map = mapping
                    for alias, proc in procs.items():
                        attached = [m for m in mapping if m['pid'] == proc['pid']]
                        spec = MODELS[alias]
                        if not attached or {m['gpu_uuid'] for m in attached} != {spec['gpu_uuid']}:
                            raise Blocked(f'GPU PID attribution drift for {alias}: {attached}')
                if time.time() >= self.deadline:
                    raise Blocked('P4b lease expired before renewal')
            except Exception as exc:
                if not self.violations:
                    self.violations.append(f'{type(exc).__name__}: {exc}')

    def close(self):
        self.stop.set()
        self.thread.join(timeout=3)


def proc_start_ticks(pid: int) -> int:
    return int(Path(f'/proc/{pid}/stat').read_text().rsplit(')', 1)[1].split()[19])


def current_boot_id() -> str:
    return Path('/proc/sys/kernel/random/boot_id').read_text().strip()


class AttachedLease:
    """Read-only client guard for a separately owned RESIDENT lease."""
    def __init__(self, claim: dict, run_id: str, evidence_root: Path, holder_identity: dict,
                 backend_identities: dict, gpu_pid_identity: dict):
        self.claim = claim
        self.run_id = run_id
        self.evidence_root = evidence_root
        self.holder_identity = holder_identity
        self.backend_identities = backend_identities
        self.gpu_pid_identity = gpu_pid_identity
        self.request_endpoints = {alias: row['backend']['endpoint']
                                  for alias, row in backend_identities.items()}
        self.client_only = True
        self.pair_resident = True
        self.latest_gpu_pid_map = gpu_pid_map()
        self.last_gpu_check = time.monotonic()

    def check(self):
        try:
            live = json.loads(CLAIM.read_text(encoding='utf-8'))
        except Exception as exc:
            raise Blocked(f'resident lease claim became unreadable: {exc}')
        if live.get('lease_id') != self.claim.get('lease_id') or live.get('status') != 'RESIDENT':
            raise Blocked('resident holder lease ID/status changed')
        if live.get('owner') != self.claim.get('owner') or live.get('gpus') != self.claim.get('gpus'):
            raise Blocked('resident holder ownership or GPU set changed')
        if live.get('models') != self.claim.get('models'):
            raise Blocked('resident holder model identity records changed')
        if live.get('staged_config_sha256') != self.claim.get('staged_config_sha256'):
            raise Blocked('resident holder staged config identity changed')
        try:
            if datetime.fromisoformat(live['expires_utc']).timestamp() <= time.time():
                raise Blocked('resident holder lease expired')
            executor = live['executor']
            if executor.get('boot_id') != current_boot_id() or int(executor['pid']) != self.holder_identity['pid']:
                raise Blocked('resident holder executor identity changed')
            if proc_start_ticks(self.holder_identity['pid']) != self.holder_identity['start_ticks']:
                raise Blocked('resident holder PID was reused or exited')
        except (KeyError, ValueError, OSError) as exc:
            raise Blocked(f'resident holder executor cannot be verified: {exc}')
        active_sha = live.get('active_config_sha256')
        staged_sha = live.get('staged_config_sha256')
        if not active_sha or active_sha != staged_sha or digest(CONFIG) != staged_sha:
            raise Blocked('active llama-swap config no longer matches resident staged hash')
        for alias, expected in self.backend_identities.items():
            rows = exact_processes(alias)
            if len(rows) != 1 or rows[0]['pid'] != expected['backend']['pid'] or rows[0]['start_ticks'] != expected['backend']['start_ticks']:
                raise Blocked(f'exact resident backend PID identity changed for {alias}')
            endpoint = endpoint_for(rows[0])
            if not endpoint or endpoint['endpoint'] != expected['backend']['endpoint']:
                raise Blocked(f'exact resident backend endpoint changed for {alias}')
        if time.monotonic() - self.last_gpu_check >= 5:
            mapping = gpu_pid_map()
            for alias, expected in self.gpu_pid_identity['models'].items():
                attached = [row for row in mapping if row['pid'] == expected['pid']]
                if not attached or {row['gpu_uuid'] for row in attached} != {MODELS[alias]['gpu_uuid']}:
                    raise Blocked(f'resident GPU UUID attribution changed for {alias}')
            self.latest_gpu_pid_map = mapping
            self.last_gpu_check = time.monotonic()


def load_p4_helper():
    if digest(P4 / 'p4_runner.py') != P4_RUNNER_SHA:
        raise Blocked('P4 fail-closed lease helper changed')
    spec = importlib.util.spec_from_file_location('p4_lease_helper', P4 / 'p4_runner.py')
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


def prepare_staged_config(lease_id: str) -> tuple[Path, str, Path]:
    original_hash = digest(CONFIG)
    if original_hash != '92fc615beece108474e96f000f519baf99e9be5ea44b203247fe11507343b1e9':
        raise Blocked('active config changed after GO; refusing P4b config staging')
    staged_bytes = p4b_config_bytes(CONFIG.read_text(encoding='utf-8'))
    staged_hash = hashlib.sha256(staged_bytes).hexdigest()
    if staged_hash != '5a0a01c5d4060db1c20731c7bce5804e3628d22e9c2d3ffd2c222065e0b0696a':
        raise Blocked('P4b staged config no longer matches reviewed SHA')
    staged_path = P7ROOT / f'config.p7-p4b-{lease_id}.yaml'
    if staged_path.exists():
        raise Blocked(f'staged config path already exists: {staged_path}')
    with staged_path.open('xb') as f:
        f.write(staged_bytes); f.flush(); os.fsync(f.fileno())
    os.chmod(staged_path, 0o600)
    run([SWAP, '-validate', '-config', str(staged_path)], timeout=30)
    backup = P7ROOT / f'config.yaml.pre-p7-{lease_id}'
    if backup.exists():
        raise Blocked(f'run-specific config backup already exists: {backup}')
    shutil.copy2(CONFIG, backup)
    os.chmod(backup, 0o600)
    if digest(backup) != original_hash:
        raise Blocked('run-specific config backup does not match reviewed original')
    return staged_path, staged_hash, backup


def install_staged_config(staged_path: Path, staged_hash: str, backup: Path, lease: Lease) -> None:
    lease.check()
    if digest(CONFIG) != digest(backup):
        raise Blocked('active config changed since exact backup; refusing overwrite')
    if digest(staged_path) != staged_hash:
        raise Blocked('staged config hash drift')
    tmp = CONFIG.with_name(f'.config.p7-{lease.claim["lease_id"]}.tmp')
    shutil.copy2(staged_path, tmp)
    os.chmod(tmp, 0o600)
    if digest(tmp) != staged_hash:
        raise Blocked('staged config copy hash mismatch')
    os.replace(tmp, CONFIG)
    fsync_dir(CONFIG.parent)
    lease.config_active = True
    until = time.monotonic() + 15
    while time.monotonic() < until:
        lease.check()
        if service_snapshot()['llama-swap.service'].get('MainPID') != '2456835':
            raise Blocked('llama-swap PID changed during config reload')
        try:
            get_json(GATEWAY + '/health')
            return
        except Exception:
            time.sleep(0.25)
    raise Blocked('llama-swap did not become healthy after config watch reload')


def sse_request(alias: str, messages: list[dict], seed: int, max_tokens: int,
                lease: Lease, tools: list[dict] | None = None, evidence_path: Path | None = None) -> dict:
    lease.check()
    payload = {'model': alias, 'messages': messages, 'stream': True,
               'stream_options': {'include_usage': True},
               'chat_template_kwargs': {'enable_thinking': False},
               'temperature': 0, 'top_p': 1, 'seed': seed, 'max_tokens': max_tokens}
    if tools is not None:
        payload['tools'] = tools
        payload['tool_choice'] = 'auto'
    body = json.dumps(payload, ensure_ascii=False, separators=(',', ':')).encode('utf-8')
    request_base = getattr(lease, 'request_endpoints', {}).get(alias, GATEWAY)
    req = urllib.request.Request(request_base + '/v1/chat/completions', data=body, method='POST',
                                 headers={'Content-Type': 'application/json', 'Accept': 'text/event-stream'})
    start_mono, start_epoch, start_utc = time.monotonic(), time.time(), utc()
    chunks: queue.Queue = queue.Queue()
    first_visible = [None]
    last_visible = [None]

    def reader():
        try:
            with urllib.request.urlopen(req, timeout=900) as response:
                for raw in response:
                    chunks.put(('raw', raw))
            chunks.put(('done', None))
        except Exception as exc:
            chunks.put(('error', exc))

    thread = threading.Thread(target=reader, name=f'p7-stream-{alias}', daemon=True)
    thread.start()
    raw_lines = []
    content_parts = []
    reasoning_parts = []
    calls: dict[int, dict] = {}
    usage = {}
    timings = None
    finish_reason = None
    try:
        while True:
            lease.check()
            try:
                kind, value = chunks.get(timeout=0.25)
            except queue.Empty:
                continue
            if kind == 'error':
                raise Blocked(f'{alias} gateway request failed: {type(value).__name__}: {value}')
            if kind == 'done':
                break
            raw_lines.append(value)
            if not value.startswith(b'data:'):
                continue
            data = value[5:].strip()
            if data == b'[DONE]':
                continue
            try:
                item = json.loads(data)
            except json.JSONDecodeError:
                continue
            if item.get('usage'):
                usage = item['usage']
            if item.get('timings'):
                timings = item['timings']
            for choice in item.get('choices', []):
                finish_reason = choice.get('finish_reason') or finish_reason
                delta = choice.get('delta') or {}
                visible = False
                text = delta.get('content')
                if isinstance(text, str) and text:
                    content_parts.append(text); visible = True
                reasoning = delta.get('reasoning_content')
                if isinstance(reasoning, str) and reasoning:
                    reasoning_parts.append(reasoning)
                for call in delta.get('tool_calls', []) or []:
                    index = call.get('index', 0)
                    row = calls.setdefault(index, {'id': '', 'type': 'function', 'function': {'name': '', 'arguments': ''}})
                    if call.get('id'):
                        row['id'] += call['id']
                    if call.get('type'):
                        row['type'] = call['type']
                    function = call.get('function') or {}
                    row['function']['name'] += function.get('name', '')
                    row['function']['arguments'] += function.get('arguments', '')
                    if call.get('id') or function.get('name') or function.get('arguments'):
                        visible = True
                if visible:
                    now = time.monotonic()
                    if first_visible[0] is None:
                        first_visible[0] = now
                    last_visible[0] = now
    finally:
        thread.join(timeout=2)
        if evidence_path:
            evidence_path.write_bytes(b''.join(raw_lines))
    end_mono = time.monotonic()
    raw = b''.join(raw_lines)
    if evidence_path:
        evidence_path.write_bytes(raw)
    text = ''.join(content_parts)
    tool_calls = [calls[i] for i in sorted(calls)]
    active_ms = (last_visible[0] - first_visible[0]) * 1000 if first_visible[0] and last_visible[0] else None
    completion_tokens = usage.get('completion_tokens')
    return {
        'request_start_utc': start_utc,
        'request_end_utc': datetime.fromtimestamp(start_epoch + (end_mono - start_mono), timezone.utc).isoformat(),
        'wall_ms': round((end_mono - start_mono) * 1000, 1),
        'ttft_ms': round((first_visible[0] - start_mono) * 1000, 1) if first_visible[0] else None,
        'generation_ms': round(active_ms, 1) if active_ms is not None else None,
        'decode_tps': round((completion_tokens or 0) / (active_ms / 1000), 3)
        if completion_tokens and active_ms and active_ms > 0 else None,
        'prompt_tokens': usage.get('prompt_tokens'), 'completion_tokens': completion_tokens,
        'finish_reason': finish_reason, 'token_exhausted': finish_reason == 'length' or completion_tokens == max_tokens,
        'backend_timings': timings, 'content': text, 'reasoning_content': ''.join(reasoning_parts),
        'reasoning_content_sha256': digest_text(''.join(reasoning_parts)),
        'tool_calls': tool_calls, 'raw_sha256': hashlib.sha256(raw).hexdigest(),
        'content_sha256': digest_text(text), 'request_payload_sha256': hashlib.sha256(body).hexdigest(),
        '_visible_start_mono': first_visible[0], '_visible_end_mono': last_visible[0],
    }


def make_case_args(task_id: str, suite_ref) -> list[list]:
    rng = random.Random(20261111)
    common = {
        '01_toposort': [(['a', 'b', 'c'], {'c': ['a']}), (['a', 'a'], {}),
                        (['a'], {'a': ['missing']}), (['a', 'b'], {'a': ['b'], 'b': ['a']})],
        '02_json_pointer_get': [({'a/b': {'~key': [9]}, '': 7}, '/a~1b/~0key/0'),
                                ({'a/b': {'~key': [9]}, '': 7}, ''), ({'a/b': {'~key': [9]}, '': 7}, '/'),
                                ({'x': 1}, 'plain'), ({'x': 1}, '/x~'), ({'x': 1}, '/x~2'),
                                ({'x': 1}, '/missing'), ({'a': [1]}, '/a/00'),
                                ({'a': [1]}, '/a/7'), ({'a': [1]}, '/a/0/x')],
        '03_safe_join': [('/srv//app/.', './foo//bar'), ('/', ''), ('/srv/app', 'a\\b'),
                         ('srv', 'x'), ('/srv', '/etc/passwd'), ('/srv', '../x'),
                         ('/srv', 'a/../b'), ('/srv\0x', 'a'), ('/srv', 'x\0y')],
        '04_retry_delays': [(6, 2, 10), (0, 1, 1), (-1, 1, 2), (1, 0, 2), (1, 3, 2),
                            (True, 1, 2), (1, False, 2), (1, 1, True)],
        '05_pack_batches': [([('a', 4), ('b', 3), ('c', 6), ('d', 2)], 3, 8),
                            ([('a', 9)], 2, 8), ([('a', 1), ('a', 2)], 2, 8),
                            ([('a', 1)], 0, 8), ([('a', True)], 2, 8)],
        '06_lru_trace': [(2, [['put', 'a', 1], ['put', 'b', 2], ['get', 'a'], ['put', 'c', 3], ['get', 'b'], ['get', 'a'], ['get', 'c']]),
                         (0, [['put', 'a', 1], ['get', 'a']]), (True, []), (2, [['wat', 'x']]),
                         (1, [['put', 'x', float('nan')]]), (1, [['get', '']])],
        '07_redact_secrets': [('API_KEY=Abcd_123! Bearer token-ABC_1234, api_key=untouched123456',),
                              ('API_KEY=short Bearer abcdefg',), ('Bearer abcdefghX',), (None,)],
        '08_select_nonoverlapping': [([('a', 0, 3), ('b', 3, 5), ('c', 1, 2), ('d', 2, 4)],),
                                    ([('x', 1, 1)],), ([('x', 0, 1), ('x', 2, 3)],), ([('x', True, 3)],)],
        '09_aggregate_logs': [([{'service': 'api', 'timestamp': 8, 'severity': 'error'},
                               {'service': 'worker', 'timestamp': 4, 'severity': 'info'},
                               {'service': 'api', 'timestamp': 2, 'severity': 'warning'}],), ([],),
                             ([{'service': 'x', 'timestamp': True, 'severity': 'info'}],),
                             ([{'service': 'x', 'timestamp': 1, 'severity': 'fatal'}],), ([None],),
                             ([{'service': '', 'timestamp': 0, 'severity': 'debug'}],)],
        '10_dependency_closure': [({'a': ['b', 'c'], 'b': ['c'], 'c': ['a'], 'z': []}, ['a']),
                                  ({'a': ['missing']}, ['a']), ({'a': ['a', 'a']}, ['a']), ({'a': []}, ['z'])],
        '13_merge_intervals': [([[8, 10], [1, 3], [2, 6], [10, 12]],), ([],),
                               ([[4, 4], [5, 6]],), ([[1, 4], [4, 5]],),
                               ([[3, 1]],), ([[1]],), ([1, 2],), ([[1, 2, 3]],)],
        '14_parse_records': [('2| Ada Lovelace |98.5\n\n1|Grace Hopper|100\n3|Zero|0',), ('',), (' \n\t\n',),
                             ('1|Name|000.00',), ('0|Ada|10',), ('-1|Ada|10',), ('١|Ada|10',),
                             ('1||10',), ('1|Ada|',), ('1|Ada|-1',), ('1|Ada|100.01',),
                             ('1|Ada|1e2',), ('1|Ada|10|extra',), ('1|Ada|10\n01|Grace|11',), (None,), (3,)],
    }
    cases = list(common[task_id])
    if task_id == '01_toposort':
        for _ in range(100):
            count = rng.randrange(1, 10)
            nodes = [f'n{i}' for i in range(count)]
            order = nodes[:]; rng.shuffle(order)
            deps = {node: [prior for prior in order[:i] if rng.random() < .23]
                    for i, node in enumerate(order)}
            cases.append((nodes, deps))
    elif task_id == '04_retry_delays':
        for _ in range(200):
            count = rng.randrange(0, 20); base = rng.randrange(1, 100); cap = rng.randrange(base, 10000)
            cases.append((count, base, cap))
    elif task_id == '05_pack_batches':
        for _ in range(100):
            count = rng.randrange(0, 30)
            items = [(f'i{i}', rng.randrange(1, 9)) for i in range(count)]
            max_weight = rng.randrange(1, 20)
            items = [item for item in items if item[1] <= max_weight]
            cases.append((items, rng.randrange(1, 8), max_weight))
    elif task_id == '08_select_nonoverlapping':
        for _ in range(250):
            jobs = []
            for i in range(rng.randrange(0, 9)):
                start = rng.randrange(0, 12); end = rng.randrange(start + 1, 14)
                jobs.append((f'j{i}', start, end))
            cases.append((jobs,))
    elif task_id == '10_dependency_closure':
        for _ in range(100):
            nodes = [f'n{i}' for i in range(rng.randrange(1, 12))]
            graph = {node: [dep for dep in nodes if rng.random() < .12] for node in nodes}
            roots = rng.sample(nodes, rng.randrange(1, len(nodes) + 1))
            cases.append((graph, roots))
    return cases


def call_oracle(task_id: str, function, args: list):
    if task_id == '11_two_worker_reasoning_schedule':
        # Fixed DAG comes from the frozen independent reference.
        if args == [None]:
            return function.TWO_WORKER_TASKS
    return None


def fixtures_for(task: dict, refs, suite_ref) -> list[dict]:
    task_id = task['id']
    merge_ref, parse_ref = refs
    fn_name = task['function'].split('(')[0]
    fn = (merge_ref.merge_intervals if task_id == '13_merge_intervals'
          else parse_ref.parse_records if task_id == '14_parse_records'
          else getattr(suite_ref, fn_name))
    fixtures = []
    if task_id == '11_two_worker_reasoning_schedule':
        valid = suite_ref.TWO_WORKER_TASKS
        malformed = [{'id': 'A', 'duration': 4, 'prerequisites': ['missing']}]
        return [
            {'args': [valid], 'predicate': 'schedule'},
            {'args': [malformed], 'error': 'ValueError'},
        ]
    case_args = make_case_args(task_id, suite_ref)
    if task_id == '02_json_pointer_get':
        huge_index = '9' * 5000
        case_args.extend([([], '/' + huge_index), ([1], '/' + huge_index)])
    elif task_id == '09_aggregate_logs':
        case_args.append(([{'service': 'x', 'timestamp': 3, 'severity': 'info',
                            'extra': {'ignored': True}}],))
    for args in case_args:
        try:
            expected = fn(*args)
            fixtures.append({'args': args, 'expected': expected})
        except Exception as exc:
            fixtures.append({'args': args, 'error': type(exc).__name__})
    return fixtures


SANDBOX_HARNESS = r'''import contextlib, io, json, sys
def emit(obj):
    sys.__stdout__.write(json.dumps(obj, ensure_ascii=False, separators=(',', ':')) + '\n')
    sys.__stdout__.flush()
try:
    source = open('/input/generated.py', encoding='utf-8').read()
    fn_name = sys.argv[1]
    request = json.loads(sys.stdin.readline())
    if sys.stdin.read(1): raise ValueError('extra request bytes')
    args = request['args']
    before = json.dumps(args, sort_keys=True, ensure_ascii=False, separators=(',', ':'))
    ns = {}
    exec(compile(source, '<generated>', 'exec'), ns, ns)
    fn = ns.get(fn_name)
    if not callable(fn): raise LookupError('required function missing')
    captured_out, captured_err = io.StringIO(), io.StringIO()
    try:
        with contextlib.redirect_stdout(captured_out), contextlib.redirect_stderr(captured_err):
            result = fn(*args)
    except BaseException as exc:
        after = json.dumps(args, sort_keys=True, ensure_ascii=False, separators=(',', ':'))
        emit({'schema': 1, 'status': 'exception', 'exception_type': type(exc).__name__,
              'args_after': json.loads(after), 'candidate_stdout': captured_out.getvalue(),
              'candidate_stderr': captured_err.getvalue()})
    else:
        after = json.dumps(args, sort_keys=True, ensure_ascii=False, separators=(',', ':'))
        try:
            encoded_result = json.loads(json.dumps(result, ensure_ascii=False, allow_nan=False))
        except BaseException as exc:
            emit({'schema': 1, 'status': 'serialization_error', 'exception_type': type(exc).__name__,
                  'args_after': json.loads(after), 'candidate_stdout': captured_out.getvalue(),
                  'candidate_stderr': captured_err.getvalue()})
        else:
            emit({'schema': 1, 'status': 'result', 'result': encoded_result,
                  'args_after': json.loads(after), 'candidate_stdout': captured_out.getvalue(),
                  'candidate_stderr': captured_err.getvalue()})
except BaseException as exc:
    emit({'schema': 1, 'status': 'harness_error', 'exception_type': type(exc).__name__})
'''


def extract_code(raw: str) -> str:
    match = re.search(r'(?is)```[^\r\n]*\r?\n(.*?)```', raw)
    return match.group(1).strip() if match else raw


def sandbox_candidate(code: str, task: dict, cases: list[dict], attempt_dir: Path,
                     trusted_schedule_validator=None) -> dict:
    attempt_dir.mkdir(parents=True, exist_ok=True)
    input_dir = attempt_dir / 'sandbox-input'
    input_dir.mkdir(exist_ok=True)
    generated = input_dir / 'generated.py'
    generated.write_text(code, encoding='utf-8')
    bwrap = shutil.which('bwrap') or 'bwrap'
    fn_name = task['function'].split('(')[0]
    outcomes = []
    passing = True

    def same_typed_value(left, right):
        if type(left) is not type(right):
            return False
        if isinstance(left, dict):
            return (left.keys() == right.keys() and
                    all(same_typed_value(left[key], right[key]) for key in left))
        if isinstance(left, list):
            return len(left) == len(right) and all(same_typed_value(a, b) for a, b in zip(left, right))
        return left == right

    for index, case in enumerate(cases):
        # The trusted parent sends only this case's arguments. Expected values
        # and oracle modules never enter the sandbox namespace or filesystem.
        args = json.loads(json.dumps(case['args'], ensure_ascii=False, allow_nan=False))
        request = json.dumps({'args': args}, ensure_ascii=False, separators=(',', ':'), allow_nan=False) + '\n'
        cmd = [bwrap, '--unshare-all', '--die-with-parent', '--new-session', '--cap-drop', 'ALL',
               '--ro-bind', '/usr', '/usr', '--ro-bind', '/lib', '/lib', '--ro-bind', '/lib64', '/lib64',
               '--ro-bind', '/etc', '/etc', '--dev', '/dev', '--proc', '/proc', '--tmpfs', '/tmp',
               '--dir', '/input', '--ro-bind', str(generated), '/input/generated.py', '--chdir', '/tmp',
               '/usr/bin/python3', '-I', '-c', SANDBOX_HARNESS, fn_name]
        try:
            proc = subprocess.run(cmd, input=request, text=True, capture_output=True,
                                  timeout=10, env={})
            stdout, stderr, rc = proc.stdout, proc.stderr, proc.returncode
        except subprocess.TimeoutExpired as exc:
            stdout = exc.stdout.decode(errors='replace') if isinstance(exc.stdout, bytes) else (exc.stdout or '')
            stderr = exc.stderr.decode(errors='replace') if isinstance(exc.stderr, bytes) else (exc.stderr or '')
            rc = 124
            stderr += '\nP7_SANDBOX_TIMEOUT\n'
        outcome = {'index': index, 'input': args, 'returncode': rc, 'stdout': stdout, 'stderr': stderr}
        if rc != 0 or stderr or stdout.count('\n') != 1:
            outcome['failure'] = 'child_exit_or_protocol_noise'
            passing = False
        else:
            try:
                response = json.loads(stdout)
                common = {'schema', 'status', 'args_after', 'candidate_stdout', 'candidate_stderr'}
                if (not isinstance(response, dict) or not common <= set(response) or
                        response.get('schema') != 1 or response.get('candidate_stdout') or
                        response.get('candidate_stderr') or not same_typed_value(response.get('args_after'), args)):
                    raise ValueError('invalid response schema, candidate noise, or mutated arguments')
                expected_error = case.get('error')
                if expected_error:
                    valid = (set(response) == common | {'exception_type'} and
                             response.get('status') == 'exception' and
                             response.get('exception_type') == expected_error)
                else:
                    expected = case.get('expected')
                    if case.get('predicate') == 'schedule':
                        if trusted_schedule_validator is None:
                            raise ValueError('trusted schedule validator missing in parent')
                        valid = (set(response) == common | {'result'} and response.get('status') == 'result'
                                 and trusted_schedule_validator(response.get('result')) is None)
                    else:
                        expected_json = json.loads(json.dumps(expected, ensure_ascii=False, allow_nan=False))
                        valid = (set(response) == common | {'result'} and response.get('status') == 'result'
                                 and same_typed_value(response.get('result'), expected_json))
                outcome['response'] = response
                if not valid:
                    outcome['failure'] = 'typed_oracle_mismatch'
                    passing = False
            except Exception as exc:
                outcome['failure'] = f'invalid_child_protocol:{type(exc).__name__}:{exc}'
                passing = False
        outcomes.append(outcome)
        if not passing:
            break

    stdout_log = '\n'.join(row['stdout'] for row in outcomes)
    stderr_log = '\n'.join(row['stderr'] for row in outcomes)
    (attempt_dir / 'sandbox_stdout.txt').write_text(stdout_log, encoding='utf-8')
    (attempt_dir / 'sandbox_stderr.txt').write_text(stderr_log, encoding='utf-8')
    failed = next((row for row in outcomes if row.get('failure')), None)
    if failed:
        (attempt_dir / 'failing_input.json').write_text(
            json.dumps(failed, ensure_ascii=False, indent=2, default=repr) + '\n', encoding='utf-8')
    return {'passed': passing and len(outcomes) == len(cases),
            'returncode': 0 if passing else (failed or {}).get('returncode', 1),
            'stdout': stdout_log, 'stderr': stderr_log,
            'case_count': len(cases), 'cases_completed': len(outcomes),
            'failing_input': failed, 'sandbox_outputs': outcomes}


class OrderAttempt:
    def __init__(self, ref):
        self.ref = ref
        self.calls = []
        self.results = []
        self.violations = []
        self.committed = False

    def execute(self, name: str, arguments: dict) -> dict:
        call = {'name': name, 'arguments': arguments}
        try:
            result = self.ref.simulate_order_calls(self.calls + [call])
        except Exception as exc:
            self.violations.append(f'{type(exc).__name__}: {exc}')
            return {'error': f'{type(exc).__name__}: {exc}'}
        self.calls.append(call)
        exact = result['tool_results'][-1]
        self.results.append(exact)
        self.committed = bool(result['committed'])
        return exact

    def accepted(self) -> tuple[bool, str | None]:
        if self.violations:
            return False, 'tool_protocol_violation'
        try:
            result = self.ref.simulate_order_calls(self.calls)
            good = (result['committed'] and result['total_cost'] == 35
                    and result['reservations'] == {'sensor': 2, 'actuator': 1}
                    and [call['name'] for call in self.calls] == ['inventory', 'quote', 'quote', 'reserve', 'reserve', 'commit'])
            return good, None if good else 'tool_order_incomplete'
        except Exception as exc:
            return False, f'tool_oracle:{type(exc).__name__}'


def tool_attempt(alias: str, task: dict, prompt: str, seed: int, lease: Lease,
                 attempt_dir: Path, order_ref) -> dict:
    messages = [{'role': 'user', 'content': prompt}]
    state = OrderAttempt(order_ref)
    tool_schema = task['tools']
    calls_all, results_all, rounds = [], [], []
    start = time.monotonic(); start_utc = utc(); first = None; last = None
    token_count = 0; active_generation = 0.0; ttft = None; final_text = ''
    failure = None
    for round_index in range(1, 11):
        stream = sse_request(alias, messages, seed, MAX_TOKENS, lease, tool_schema,
                             attempt_dir / f'raw_response_round{round_index}.sse')
        rounds.append({k: v for k, v in stream.items() if k not in ('content', 'reasoning_content', 'tool_calls')})
        token_count += stream.get('completion_tokens') or 0
        if stream.get('_visible_start_mono') is not None:
            first = stream['_visible_start_mono'] if first is None else min(first, stream['_visible_start_mono'])
            last = stream['_visible_end_mono'] if last is None else max(last, stream['_visible_end_mono'])
        if stream['ttft_ms'] is not None:
            if stream['generation_ms'] is not None:
                active_generation += stream['generation_ms']
        final_text = stream['content']
        if stream['tool_calls']:
            if stream['content'] and not state.committed and re.search(r'\b(success|committed|order (?:is )?complete)\b', stream['content'], re.I):
                failure = 'premature_success_claim'
            assistant_calls = []
            for tool_call in stream['tool_calls']:
                function = tool_call.get('function', {})
                try:
                    arguments = json.loads(function.get('arguments') or '{}')
                    if not isinstance(arguments, dict):
                        raise ValueError('tool arguments must decode to an object')
                except Exception as exc:
                    arguments = {}
                    state.violations.append(f'invalid_tool_json:{exc}')
                    result = {'error': f'invalid_tool_json:{type(exc).__name__}'}
                else:
                    result = state.execute(function.get('name', ''), arguments)
                call_row = {'id': tool_call.get('id'), 'name': function.get('name'),
                            'arguments': arguments, 'result': result}
                calls_all.append(call_row); results_all.append(result)
                assistant_calls.append(tool_call)
            messages.append({'role': 'assistant', 'content': stream['content'] or None, 'tool_calls': assistant_calls})
            for tool_call, row in zip(assistant_calls, calls_all[-len(assistant_calls):]):
                # Preserve this compact JSON verbatim in the next tool message.
                encoded = json.dumps(row['result'], ensure_ascii=False, separators=(',', ':'))
                messages.append({'role': 'tool', 'tool_call_id': tool_call.get('id'), 'content': encoded})
            continue
        break
    else:
        failure = failure or 'tool_loop_round_limit'
    accepted, tool_failure = state.accepted()
    if failure is None and tool_failure:
        failure = tool_failure
    if not state.committed and final_text and re.search(r'\b(success|committed|order (?:is )?complete)\b', final_text, re.I):
        failure = failure or 'premature_success_claim'
    if not state.committed:
        accepted = False
    end = time.monotonic()
    if first is not None:
        ttft = (first - start) * 1000
    trace = {'calls': calls_all, 'exact_tool_results': results_all, 'messages_after_initial': messages[1:],
             'violations': state.violations, 'committed': state.committed, 'final_text': final_text}
    (attempt_dir / 'tool_trace.json').write_text(json.dumps(trace, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    if failure:
        (attempt_dir / 'failing_input.json').write_text(json.dumps({'tool_calls': calls_all, 'reason': failure}, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    return {'accepted': accepted and failure is None, 'failure_class': failure,
            'oracle_id': 'P7 reference.simulate_order_calls', 'exact_input_sha256': None,
            'start_utc': start_utc, 'end_utc': utc(), 'acceptance_end_utc': utc(),
            'response_end_utc': rounds[-1].get('request_end_utc') if rounds else None,
            'wall_ms': round((end - start) * 1000, 1),
            'response_wall_ms': round(sum(row.get('wall_ms', 0) for row in rounds), 1),
            'generation_ms': round((last - first) * 1000, 1) if first is not None and last is not None else None,
            'active_generation_ms': round(active_generation, 1) if active_generation else None,
            'ttft_ms': round(ttft, 1) if ttft is not None else None,
            'completion_tokens': token_count, 'decode_tps': round(token_count / (active_generation / 1000), 3) if active_generation else None,
            'tool_rounds': rounds, 'output': final_text, 'output_sha256': digest_text(final_text),
            'reasoning_content': None, 'token_exhausted': any(r.get('token_exhausted') for r in rounds)}


def coding_attempt(alias: str, task: dict, prompt: str, seed: int, lease: Lease,
                   attempt_dir: Path, fixtures: list[dict], suite_ref) -> dict:
    acceptance_start = time.monotonic()
    stream = sse_request(alias, [{'role': 'user', 'content': prompt}], seed, MAX_TOKENS, lease,
                         evidence_path=attempt_dir / 'raw_response.sse')
    raw_output = stream['content']
    (attempt_dir / 'raw_output.txt').write_text(raw_output, encoding='utf-8')
    (attempt_dir / 'reasoning_content.txt').write_text(stream['reasoning_content'], encoding='utf-8')
    source = extract_code(raw_output)
    (attempt_dir / 'generated_source.py').write_text(source, encoding='utf-8')
    checks = sandbox_candidate(source, task, fixtures, attempt_dir,
                               suite_ref.validate_reasoning_schedule if task['id'] == '11_two_worker_reasoning_schedule' else None)
    end = time.monotonic()
    acceptance_end_utc = utc()
    return {'accepted': checks['passed'], 'failure_class': None if checks['passed'] else 'oracle_or_sandbox_failure',
            'oracle_id': ('P7 reference.py' if task['id'] in {
                '01_toposort', '02_json_pointer_get', '03_safe_join', '04_retry_delays',
                '05_pack_batches', '06_lru_trace', '07_redact_secrets',
                '08_select_nonoverlapping', '09_aggregate_logs', '10_dependency_closure',
                '11_two_worker_reasoning_schedule', '12_mocked_order_agent'}
                else task.get('oracle_id', 'P4 frozen oracle')),
            'exact_input_sha256': digest_text(json.dumps(fixtures, ensure_ascii=False, sort_keys=True, default=repr)),
            'start_utc': stream['request_start_utc'], 'response_end_utc': stream['request_end_utc'],
            'end_utc': acceptance_end_utc, 'acceptance_end_utc': acceptance_end_utc,
            'response_wall_ms': stream['wall_ms'],
            'wall_ms': round((end - acceptance_start) * 1000, 1),
            'generation_ms': stream['generation_ms'], 'active_generation_ms': stream['generation_ms'],
            'ttft_ms': stream['ttft_ms'], 'prompt_tokens': stream['prompt_tokens'],
            'completion_tokens': stream['completion_tokens'], 'decode_tps': stream['decode_tps'],
            'backend_timings': stream['backend_timings'], 'token_exhausted': stream['token_exhausted'],
            'reasoning_content': stream['reasoning_content'], 'output_sha256': stream['content_sha256'],
            'sandbox': {k: v for k, v in checks.items() if k != 'failing_input'}}


def one_attempt(alias: str, task: dict, prompt: str, seed: int, index: int, lease: Lease,
                evidence_root: Path, fixtures: list[dict], suite_ref, p4refs) -> dict:
    attempt_dir = evidence_root / alias / task['id'] / f'attempt-{index}-seed-{seed}'
    attempt_dir.mkdir(parents=True, exist_ok=False)
    (attempt_dir / 'prompt.txt').write_text(prompt, encoding='utf-8')
    if digest_text(prompt) != task['_prompt_sha256']:
        raise Blocked(f'prompt changed before dispatch for {task["id"]}')
    if task['kind'] == 'tool_use_agent':
        result = tool_attempt(alias, task, prompt, seed, lease, attempt_dir, suite_ref)
    else:
        result = coding_attempt(alias, task, prompt, seed, lease, attempt_dir, fixtures, suite_ref)
    result['evidence_path'] = str(attempt_dir)
    return result


def backend_identity(alias: str, lease: Lease, timeout: int = 180) -> dict:
    end = time.monotonic() + timeout
    last_error = None
    while time.monotonic() < end:
        lease.check()
        procs = exact_processes(alias)
        if len(procs) > 1:
            raise Blocked(f'multiple exact candidate processes for {alias}')
        if procs:
            backend = endpoint_for(procs[0])
            if backend:
                try:
                    ident = verify_backend(alias, backend)
                    return {'backend': backend, 'identity': ident}
                except Exception as exc:
                    last_error = f'{type(exc).__name__}: {exc}'
        time.sleep(0.25)
    raise Blocked(f'{alias} backend readiness identity not verified: {last_error}')


def assert_pair_gpu_attribution(lease: Lease) -> dict:
    result = {}
    mapping = gpu_pid_map()
    processes = all_pair_processes()
    for alias in ALIASES:
        proc = processes[alias]
        if not proc:
            raise Blocked(f'{alias} exact process absent after warmup')
        rows = [row for row in mapping if row['pid'] == proc['pid']]
        expected = MODELS[alias]['gpu_uuid']
        if not rows or {row['gpu_uuid'] for row in rows} != {expected}:
            raise Blocked(f'{alias} PID is not attributed only to GPU UUID {expected}: {rows}')
        result[alias] = {'pid': proc['pid'], 'start_ticks': proc['start_ticks'], 'gpu_uuid': expected,
                         'per_process_gpu_memory': rows}
    lease.pair_resident = True
    lease.latest_gpu_pid_map = mapping
    return {'models': result, 'nvidia_smi_compute_apps': mapping}


def exact_unload(alias: str, lease: Lease) -> dict:
    spec = MODELS[alias]
    procs = exact_processes(alias)
    if len(procs) > 1:
        raise Blocked(f'refusing unload with ambiguous exact process set for {alias}')
    if not procs:
        if gateway_status(alias) == 'unloaded':
            return {'already_unloaded': True, 'unload_ms': 0.0}
        raise Blocked(f'refusing exact unload of {alias}: no matching model process, gateway status={gateway_status(alias)}')
    proc = procs[0]
    backend = endpoint_for(proc)
    if not backend or backend['model_path'] != spec['path'] or backend['executable'] != os.path.realpath(LLAMA):
        raise Blocked(f'refusing unload; exact path/executable/socket identity failed for {alias}')
    started = time.monotonic()
    request = urllib.request.Request(GATEWAY + f'/api/models/unload/{alias}', data=b'', method='POST',
                                     headers={'Content-Type': 'application/json'})
    with urllib.request.urlopen(request, timeout=90) as response:
        response.read()
    deadline = time.monotonic() + 90
    while time.monotonic() < deadline:
        current = [p for p in exact_processes(alias) if p['pid'] == proc['pid'] and p['start_ticks'] == proc['start_ticks']]
        if not current and gateway_status(alias) == 'unloaded':
            return {'unload_ms': round((time.monotonic() - started) * 1000, 1),
                    'pid': proc['pid'], 'start_ticks': proc['start_ticks'], 'status': 'exact_unloaded'}
        time.sleep(0.25)
    raise Blocked(f'exact unload did not remove {alias} PID {proc["pid"]}')


def restore_config_if_safe(staged_hash: str | None, backup: Path | None, original_hash: str, lease: Lease) -> dict:
    if not backup or not backup.exists():
        return {'restored': digest(CONFIG) == original_hash, 'reason': 'no run backup was made'}
    current_hash = digest(CONFIG)
    if current_hash == original_hash:
        return {'restored': True, 'reason': 'already at exact original bytes'}
    if current_hash != staged_hash:
        return {'restored': False, 'reason': 'active config differs from both exact staged and original hashes; preserved concurrent edit'}
    if digest(backup) != original_hash:
        return {'restored': False, 'reason': 'run backup hash drift; did not restore'}
    tmp = CONFIG.with_name(f'.config.p7-restore-{lease.claim["lease_id"]}.tmp')
    shutil.copy2(backup, tmp); os.chmod(tmp, 0o600)
    if digest(tmp) != original_hash:
        tmp.unlink(missing_ok=True)
        return {'restored': False, 'reason': 'restore temp hash mismatch'}
    os.replace(tmp, CONFIG); fsync_dir(CONFIG.parent)
    return {'restored': digest(CONFIG) == original_hash, 'reason': 'restored only from exact lease backup'}


def persist_result(data: dict, path: Path = RESULT) -> None:
    write_json_atomic(path, data, 0o600)


def run_benchmark(tasks_data: dict, manifest: dict, suite_ref, p4refs,
                  merge_prompt: str, parse_prompt: str, prefill_prompt: str,
                  baseline: dict, lease: Lease, selected_task_ids: set[str] | None = None,
                  client_only: bool = False, result_path: Path = RESULT) -> dict:
    global PARTIAL_RESULT
    tasks = list(tasks_data['tasks'])
    p4_extra = [
        {'id': '13_merge_intervals', 'kind': 'coding', 'function': 'merge_intervals(intervals)',
         'prompt': merge_prompt, 'spec': merge_prompt, 'oracle_id': 'P4 oracle_reference.py'},
        {'id': '14_parse_records', 'kind': 'coding', 'function': 'parse_records(text)',
         'prompt': parse_prompt, 'spec': (P4 / 'heldout_parse_spec.txt').read_text(encoding='utf-8'),
         'oracle_id': 'P4 heldout_parse_reference.py'},
    ]
    tasks += p4_extra
    if selected_task_ids is not None:
        known = {task['id'] for task in tasks}
        if not selected_task_ids or not selected_task_ids <= known:
            raise Blocked('task filter is empty or contains unknown frozen task IDs')
        tasks = [task for task in tasks if task['id'] in selected_task_ids]
    for task in tasks:
        task['_prompt_sha256'] = digest_text(task['prompt'])
    fixtures = {task['id']: fixtures_for(task, p4refs, suite_ref)
                for task in tasks if task['kind'] != 'tool_use_agent'}
    run_id = getattr(lease, 'run_id', lease.claim['lease_id'])
    evidence_root = getattr(lease, 'evidence_root', P7ROOT / f'evidence-{run_id}')
    evidence_root.mkdir(mode=0o700, exist_ok=False)
    p4_only_oracles = {'merge_touching_case': True, 'parse_ascii_spec_case': True}
    result = {
        'task': 'P7 paired P4b residency client benchmark' if client_only else 'P7 paired P4b residency benchmark',
        'status': 'RUNNING', 'client_only_attach': client_only,
        'run_id': run_id, 'lease_id': lease.claim['lease_id'], 'start_utc': utc(),
        'result_path': str(result_path),
        'suite': {'tasks_file_sha256': TASKS_SHA, 'reference_sha256': REFERENCE_SHA,
                  'manifest_sha256': MANIFEST_SHA, 'manifest_task_count': len(manifest['tasks']),
                  'runtime_task_count': len(tasks), 'p4_runner_sha256': P4_RUNNER_SHA,
                  'p4b_runner_sha256': P4B_RUNNER_SHA, 'merge_oracle_sha256': MERGE_ORACLE_SHA,
                  'parse_spec_sha256': PARSE_SPEC_SHA, 'parse_oracle_sha256': PARSE_ORACLE_SHA,
                  'runtime_tasks': [{'task_id': task['id'], 'prompt_sha256': digest_text(task['prompt']),
                                     'spec_sha256': digest_text(task['spec']),
                                     'oracle_id': task.get('oracle_id', 'P7 reference.py')}
                                    for task in tasks]},
        'p4_prompt_provenance': {
            'merge_intervals': {'prompt_sha256': P4_PROMPTS['merge_intervals'],
                                'oracle_sha256': MERGE_ORACLE_SHA},
            'parse_records': {'raw_spec_sha256': PARSE_SPEC_SHA,
                              'assembled_prompt_sha256': P4_PROMPTS['parse_records'],
                              'assembly': 'fixed prefix plus exact UTF-8 decoded heldout_parse_spec.txt'},
        },
        'decoding': {'temperature': 0, 'top_p': 1, 'max_tokens': MAX_TOKENS,
                     'context': CTX, 'enable_thinking': False, 'seeds': [42, 43, 44],
                     'stream': True, 'include_usage': True, 'inter_attempt_delay_ms': 0},
        'gateway_endpoint': GATEWAY,
        'request_route': ('direct resident backend endpoints; bypass llama-swap lifecycle routing' if client_only
                          else 'llama-swap gateway; direct backend endpoints used only for identity checks'),
        'inference_endpoints_by_alias': ({a: lease.request_endpoints[a] for a in ALIASES}
                                         if client_only else {a: GATEWAY for a in ALIASES}),
        'before': baseline,
        'oracle_precheck': p4_only_oracles if client_only else oracle_precheck(suite_ref, p4refs),
        'prefill_prompt_sha256': digest_text(prefill_prompt), 'prefill': {},
        'models': {}, 'task_results': [], 'paired_attempts': [],
        'evidence_root': str(evidence_root), 'residency_mode': True,
        'effective_time_definition': 'monotonic request-start through trusted oracle acceptance, summed across attempts through first acceptance; response_wall_ms separately records model response duration; all three attempts always run',
    }
    PARTIAL_RESULT = result
    result['models'] = {alias: {'candidate_id': MODELS[alias]['candidate_id'],
                                'model_path': MODELS[alias]['path'], 'artifact_sha256': MODELS[alias]['sha'],
                                'gpu_index': MODELS[alias]['gpu_index'], 'gpu_uuid': MODELS[alias]['gpu_uuid'],
                                'context': CTX, 'backend_identity': None, 'attempts': 0}
                       for alias in ALIASES}
    # P4b's exact cold backend prompt is used only to establish both pinned residents.
    p4tree = ast.parse((P4 / 'p4_runner.py').read_text(encoding='utf-8'))
    prompt_nodes = [n for n in p4tree.body if isinstance(n, ast.Assign)
                    and any(isinstance(t, ast.Name) and t.id == 'FIXED_PROMPT' for t in n.targets)]
    consts = {}; exec(compile(ast.Module(body=prompt_nodes, type_ignores=[]), '<p4-warmup>', 'exec'), consts)
    warmup_prompt = consts['FIXED_PROMPT']
    warmup_futures = {}
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
        for alias in ALIASES:
            warmup_futures[alias] = pool.submit(sse_request, alias,
                [{'role': 'user', 'content': warmup_prompt}], 42, 512, lease, None,
                evidence_root / f'warmup-{alias}.sse')
        warmups = {alias: future.result() for alias, future in warmup_futures.items()}
    result['warmup'] = {alias: {k: v for k, v in row.items() if k not in ('content', 'reasoning_content', 'tool_calls')}
                        for alias, row in warmups.items()}
    identities = {}
    for alias in ALIASES:
        identities[alias] = backend_identity(alias, lease)
    result['backend_identity'] = identities
    for alias in ALIASES:
        result['models'][alias]['backend_identity'] = identities[alias]
    result['gpu_pid_attribution_after_load'] = assert_pair_gpu_attribution(lease)
    # Exact P4 long-prefill prompt, streamed concurrently; usage must prove >=1,000 tokens each.
    prefill_futures = {}
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
        for alias in ALIASES:
            prefill_futures[alias] = pool.submit(sse_request, alias,
                [{'role': 'user', 'content': prefill_prompt}], 42, 64, lease, None,
                evidence_root / f'prefill-{alias}.sse')
        prefill_rows = {alias: future.result() for alias, future in prefill_futures.items()}
    for alias, row in prefill_rows.items():
        if not row.get('prompt_tokens') or row['prompt_tokens'] < 1000:
            raise Blocked(f'{alias} P4 prefill usage {row.get("prompt_tokens")} is below 1,000 tokens')
    result['prefill'] = {alias: {k: v for k, v in row.items() if k not in ('content', 'reasoning_content', 'tool_calls')}
                         for alias, row in prefill_rows.items()}
    # Pair every task/seed concurrently so both exact residents serve overlapping requests.
    for task in tasks:
        prompt = task['prompt']
        prompt_sha = digest_text(prompt)
        if prompt_sha != task['_prompt_sha256']:
            raise Blocked(f'prompt drift before task {task["id"]}')
        per_model = {alias: [] for alias in ALIASES}
        for index, seed in enumerate((42, 43, 44), 1):
            lease.check()
            pair_start = time.monotonic()
            with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
                futures = {alias: pool.submit(one_attempt, alias, task, prompt, seed, index, lease,
                                               evidence_root, fixtures.get(task['id'], []), suite_ref, p4refs)
                           for alias in ALIASES}
                pair_attempts = {alias: future.result() for alias, future in futures.items()}
            pair_wall = round((time.monotonic() - pair_start) * 1000, 1)
            result['paired_attempts'].append({'task_id': task['id'], 'attempt_index': index, 'seed': seed,
                                              'concurrent_pair_wall_ms': pair_wall,
                                              'per_model': pair_attempts})
            for alias in ALIASES:
                rec = pair_attempts[alias]
                rec.update({'task_id': task['id'], 'candidate_id': alias, 'attempt_index': index,
                            'seed': seed, 'prompt_sha256': prompt_sha,
                            'oracle_accepted': bool(rec.pop('accepted'))})
                per_model[alias].append(rec)
                result['models'][alias]['attempts'] += 1
        for alias in ALIASES:
            attempts = per_model[alias]
            successes = [i for i, rec in enumerate(attempts) if rec['oracle_accepted']]
            first_index = successes[0] + 1 if successes else None
            through = attempts[:first_index] if first_index else attempts
            accepted_wall = sum(row['wall_ms'] for row in through) if first_index else None
            accepted_generation = (None if not first_index or any(row['generation_ms'] is None for row in through)
                                  else sum(row['generation_ms'] for row in through))
            accept_generation_missing = (None if not first_index else
                                         sum(row['generation_ms'] is None for row in through))
            fail_first = not attempts[0]['oracle_accepted']
            penalty_rows = attempts[:1] if fail_first and first_index else attempts if not first_index else []
            penalty_generation_missing = sum(row['generation_ms'] is None for row in penalty_rows)
            penalty_generation = (0 if not penalty_rows else
                                  None if penalty_generation_missing else
                                  sum(row['generation_ms'] for row in penalty_rows))
            summary = {
                'task_id': task['id'], 'candidate_id': alias, 'prompt_sha256': prompt_sha,
                'attempts': attempts, 'pass_at_1': attempts[0]['oracle_accepted'],
                'pass_at_3': bool(successes), 'attempts_to_first_accept': first_index,
                'minimum_time_to_accepted_wall_ms': accepted_wall,
                'minimum_time_to_accepted_generation_ms': accepted_generation,
                'failed_first_attempt_penalty_wall_ms': sum(row['wall_ms'] for row in penalty_rows),
                'failed_first_attempt_penalty_generation_ms': penalty_generation,
                'generation_missing_attempt_count': sum(row['generation_ms'] is None for row in attempts),
                'time_to_accept_generation_missing_count': accept_generation_missing,
                'penalty_generation_missing_count': penalty_generation_missing,
                'all_attempts_failed': not bool(successes),
                'effective_time_to_accepted_wall_ms': accepted_wall,
                'effective_time_to_accepted_generation_ms': accepted_generation,
                'response_time_to_accepted_wall_ms': (sum(row.get('response_wall_ms', 0) for row in through)
                                                       if first_index else None),
            }
            result['task_results'].append(summary)
    for alias in ALIASES:
        rows = [r for r in result['task_results'] if r['candidate_id'] == alias]
        result['models'][alias]['pass_at_1'] = sum(r['pass_at_1'] for r in rows) / len(rows)
        result['models'][alias]['pass_at_3'] = sum(r['pass_at_3'] for r in rows) / len(rows)
    return result


def main() -> int:
    signal.signal(signal.SIGTERM, lambda *_: (_ for _ in ()).throw(Blocked('SIGTERM; cleanup required')))
    signal.signal(signal.SIGINT, lambda *_: (_ for _ in ()).throw(Blocked('SIGINT; cleanup required')))
    P7ROOT.mkdir(parents=True, exist_ok=True)
    tasks_data, manifest, suite_ref, p4refs, merge_prompt, parse_prompt, prefill_prompt = check_suite_and_p4()
    oracle_checks = oracle_precheck(suite_ref, p4refs)
    baseline = preflight(tasks_data, p4refs)
    baseline['oracle_precheck'] = oracle_checks
    lock_fd = os.open(LOCK, os.O_CREAT | os.O_RDWR, 0o600)
    try:
        fcntl.flock(lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        os.close(lock_fd)
        raise Blocked('shared P4b/P7 GPU lease lock is already held')
    claim = None
    lease = None
    p4 = None
    staged_path = None
    staged_hash = None
    backup = None
    may_have_loaded = False
    result = None
    cleanup_ok = False
    cleanup_errors = []
    unloads = {}
    original_config_hash = baseline['config_sha256']
    try:
        # This is the only stale-claim recovery path: P4's exact hash-pinned fail-closed helper.
        p4 = load_p4_helper()
        p4.refuse_existing_claim()
        now = time.time(); lease_id = str(uuid.uuid4()); pid = os.getpid(); parent_pid = os.getppid()
        boot_id = p4.boot()
        deadline = now + LEASE_SECONDS
        parent = (parent_pid, p4.ticks(parent_pid))
        claim = {
            'lease_id': lease_id, 'status': 'WAITING_GO',
            'owner': {'supervisor': SUPERVISOR, 'executor': 'P7 paired P4b residency'},
            'executor': {'pid': pid, 'start_ticks': p4.ticks(pid), 'boot_id': boot_id},
            'parent': {'pid': parent[0], 'start_ticks': parent[1], 'boot_id': boot_id},
            'gpus': [EXPECTED_GPU_MAP[0], EXPECTED_GPU_MAP[1]],
            'resources': 'P4b exact dual-RTX-5090 residency; qwen3.8-27b-q6 on GPU0 and qwen3.6-35b-q5 on GPU1',
            'candidates': [{**spec, 'alias': alias, 'model_sha256': spec['sha'],
                            'expected_gpu_uuid': spec['gpu_uuid'], 'ctx': CTX}
                           for alias, spec in MODELS.items()],
            'config_original_sha256': original_config_hash,
            'started_utc': datetime.fromtimestamp(now, timezone.utc).isoformat(),
            'expires_utc': datetime.fromtimestamp(deadline, timezone.utc).isoformat(),
            'lease_seconds': LEASE_SECONDS, 'renew_before_seconds': RENEW_BEFORE_SECONDS,
            'cleanup': 'exact aliases only; restore only when active config matches the exact staged SHA; preserve P4b baseline',
        }
        p4.write_claim(claim, create=True)
        lease = Lease(lock_fd, parent, claim, p4); lease.start()
        token = f'GO winter lease={lease_id}'
        print(f'WAITING_GO {token}', flush=True)
        print(f'LEASE {lease_id} expires={claim["expires_utc"]}; no config edit/model load before exact GO', flush=True)
        if not wait_for_go(token, lease):
            raise Blocked('exact Winter GO not received before lease expiry')
        lease.renew_enabled = True
        lease.update_claim(status='GO_RECEIVED', go_received_utc=utc())
        lease.check()
        current = {'gpus': gpu_rows(), 'services': service_snapshot(), 'ports': port_snapshot()}
        if current['services'] != baseline['services'] or current['ports'] != baseline['ports']:
            raise Blocked('protected service/port baseline drifted before GO')
        for g, b in zip(current['gpus'], baseline['gpus']):
            if g['uuid'] != b['uuid'] or g['free_mib'] < b['free_mib'] - FREE_FLOOR_MIB:
                raise Blocked('GPU free-memory baseline drift exceeded 1 GiB before GO')
        for alias, spec in MODELS.items():
            if digest(Path(spec['path'])) != spec['sha']:
                raise Blocked(f'{alias} model artifact SHA changed between preflight and GO')
        staged_path, staged_hash, backup = prepare_staged_config(lease_id)
        may_have_loaded = True
        install_staged_config(staged_path, staged_hash, backup, lease)
        lease.config_active = True
        lease.update_claim(status='RUNNING', active_config_sha256=staged_hash,
                           config_backup=str(backup), staged_config=str(staged_path),
                           config_backup_sha256=original_config_hash,
                           staged_config_sha256=staged_hash, config_installed_utc=utc())
        result = run_benchmark(tasks_data, manifest, suite_ref, p4refs, merge_prompt,
                               parse_prompt, prefill_prompt, baseline, lease)
        result['status'] = 'COMPLETE'
    except Exception as exc:
        if result is None:
            result = PARTIAL_RESULT or {'task': 'P7 paired P4b residency benchmark', 'status': 'BLOCKED',
                      'start_utc': claim.get('started_utc') if claim else utc(),
                      'error': f'{type(exc).__name__}: {exc}', 'before': baseline,
                      'oracle_precheck': oracle_checks, 'task_results': []}
            result['status'] = 'BLOCKED'
            result['error'] = f'{type(exc).__name__}: {exc}'
        else:
            result['status'] = 'BLOCKED'
            result['error'] = f'{type(exc).__name__}: {exc}'
    finally:
        if may_have_loaded and lease:
            lease.cleanup_mode = True
            lease.pair_resident = False
            # Exact backend identity must be proven before any unload request.
            for alias in ALIASES:
                try:
                    if exact_processes(alias):
                        unloads[alias] = exact_unload(alias, lease)
                    else:
                        configured_alias = alias if digest(CONFIG) == staged_hash else MODELS[alias]['legacy_alias']
                        if gateway_status(configured_alias) != 'unloaded':
                            raise Blocked(f'{configured_alias} reports loaded without the exact process identity; refusing unload')
                        unloads[alias] = {'already_unloaded': True}
                except Exception as exc:
                    cleanup_errors.append(f'{alias} unload: {type(exc).__name__}: {exc}')
            try:
                if not any(exact_processes(alias) for alias in ALIASES):
                    lease.pair_resident = False
            except Exception as exc:
                cleanup_errors.append(f'candidate process check: {exc}')
        if staged_hash and lease:
            try:
                restore = restore_config_if_safe(staged_hash, backup, original_config_hash, lease)
                lease.config_active = digest(CONFIG) == staged_hash
                if not restore['restored']:
                    cleanup_errors.append(restore['reason'])
            except Exception as exc:
                restore = {'restored': False, 'reason': f'{type(exc).__name__}: {exc}'}
                cleanup_errors.append(restore['reason'])
        else:
            restore = {'restored': digest(CONFIG) == original_config_hash,
                       'reason': 'active config untouched before GO' if digest(CONFIG) == original_config_hash else 'active config changed unexpectedly'}
            if not restore['restored']:
                cleanup_errors.append(restore['reason'])
        try:
            after = {'gpus': gpu_rows(), 'services': service_snapshot(), 'ports': port_snapshot(),
                     'gpu_pid_map': gpu_pid_map(), 'candidate_processes': all_pair_processes(),
                     'config_sha256': digest(CONFIG)}
            service_baseline_check(after['services'], after['ports'])
            if any(after['ports'].get(str(port)) for port in CANDIDATE_PORTS):
                raise Blocked('candidate port remains occupied after exact unload')
            if any(after['candidate_processes'].values()):
                raise Blocked('exact candidate process remains after unload')
            if after['config_sha256'] != original_config_hash:
                raise Blocked('active config not restored to exact original bytes')
            if any(g['free_mib'] < FREE_FLOOR_MIB for g in after['gpus']):
                raise Blocked('GPU free-memory floor remains breached after cleanup')
            if after['services'] != baseline['services']:
                raise Blocked('protected service baseline changed')
            expected_ports = baseline['ports']
            if any(after['ports'].get(k) != v for k, v in expected_ports.items() if k in map(str, (*PROTECTED_PORTS, *CANDIDATE_PORTS))):
                raise Blocked('protected port baseline changed')
            cleanup_ok = not cleanup_errors
        except Exception as exc:
            after = {'error': f'{type(exc).__name__}: {exc}'}
            cleanup_errors.append(after['error'])
            cleanup_ok = False
        if lease:
            lease.close()
        if result is None:
            result = {'task': 'P7 paired P4b residency benchmark', 'status': 'BLOCKED',
                      'error': 'runner ended without result', 'task_results': []}
        result.update({'end_utc': utc(), 'unloads': unloads, 'config_restore': restore,
                       'after': after, 'peak_used_mib_by_uuid': lease.peak if lease else {},
                       'minimum_free_mib_by_uuid': lease.minfree if lease else {},
                       'cleanup_errors': cleanup_errors, 'cleanup_verified': cleanup_ok})
        if claim and p4:
            claim['status'] = 'RELEASED' if cleanup_ok else 'CLEANUP_FAILED'
            claim['cleanup_verified'] = cleanup_ok
            claim['released_utc'] = utc() if cleanup_ok else None
            try:
                p4.write_claim(claim)
            except Exception as exc:
                cleanup_ok = False
                result['cleanup_errors'].append(f'lease release write failed: {exc}')
        result['cleanup_verified'] = cleanup_ok
        result['status'] = ('COMPLETE' if cleanup_ok and result.get('status') == 'COMPLETE'
                            else 'BLOCKED' if cleanup_ok else 'BLOCKED_CLEANUP')
        try:
            persist_result(result)
        except Exception as exc:
            print(f'result persistence failed: {exc}', file=sys.stderr, flush=True)
        try:
            fcntl.flock(lock_fd, fcntl.LOCK_UN)
            os.close(lock_fd)
        except Exception:
            pass
    print(f'{result["status"]} evidence={RESULT}', flush=True)
    return 0 if result['status'] == 'COMPLETE' else 2


P7_ATTACH_TASK_IDS = {
    '01_toposort', '02_json_pointer_get', '03_safe_join', '04_retry_delays',
    '05_pack_batches', '06_lru_trace', '07_redact_secrets',
    '08_select_nonoverlapping', '09_aggregate_logs', '10_dependency_closure',
}
P4_ATTACH_TASKS = {'13_merge_intervals', '14_parse_records'}
P4_ATTACH_TASK_ALIASES = {task_id: task_id for task_id in P4_ATTACH_TASKS}
P4_ATTACH_TASK_ALIASES.update({'merge_intervals': '13_merge_intervals', 'parse_records': '14_parse_records'})
P4_ATTACH_TASK_ALIASES.update({task_id.split('_', 1)[1]: task_id for task_id in P7_ATTACH_TASK_IDS})
P4_ATTACH_TASK_ALIASES.update({task_id: task_id for task_id in P7_ATTACH_TASK_IDS})


def parse_attach_tasks(value: str) -> set[str]:
    selected = set()
    for raw in value.split(','):
        name = raw.strip()
        if not name or name not in P4_ATTACH_TASK_ALIASES:
            raise Blocked('--tasks in attach mode accepts only P7 tasks 01-10 and P4 merge_intervals/parse_records')
        selected.add(P4_ATTACH_TASK_ALIASES[name])
    if not selected:
        raise Blocked('attach mode requires --tasks with a subset of P7 tasks 01-10 and/or the two P4 tasks')
    return selected


def selected_p4_prompt_ids(selected_task_ids):
    if selected_task_ids is None:
        return set(P4_ATTACH_TASKS)
    return set(selected_task_ids) & P4_ATTACH_TASKS


def _unique_json_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f'duplicate JSON key: {key}')
        result[key] = value
    return result


def validate_attach_job(job: object, lease_id: str | None = None) -> dict:
    """Validate the feeder's exact suite-v1 schema before holder/API checks."""
    if not isinstance(job, dict) or set(job) != ATTACH_JOB_FIELDS:
        raise Blocked(f'job keys must be exactly {sorted(ATTACH_JOB_FIELDS)}')
    if type(job['schema_version']) is not int or job['schema_version'] != 1:
        raise Blocked('unsupported attach job schema_version')
    if job['suite_id'] != 'suite-v1' or job['manifest_sha256'] != MANIFEST_V1_SHA:
        raise Blocked('attach job suite ID or suite-v1 manifest pin mismatch')
    manifest_path = SUITE_V1 / 'manifest.json'
    if not manifest_path.is_file() or digest(manifest_path) != MANIFEST_V1_SHA:
        raise Blocked('suite-v1 manifest bytes/hash mismatch')
    if not isinstance(job['job_id'], str) or not ATTACH_JOB_ID_RE.fullmatch(job['job_id']):
        raise Blocked('invalid attach job_id')
    task_ids = job['task_ids']
    if (not isinstance(task_ids, list) or not task_ids or
            any(not isinstance(item, str) for item in task_ids) or len(task_ids) != len(set(task_ids))):
        raise Blocked('task_ids must be a nonempty unique string list')
    if not set(task_ids) <= set(ATTACH_TASK_ORDER):
        raise Blocked('attach job contains an unknown or excluded task')
    if task_ids != [task_id for task_id in ATTACH_TASK_ORDER if task_id in task_ids]:
        raise Blocked('task_ids must follow suite-v1 canonical order')
    if job['seeds'] != [42, 43, 44] or job['streams'] is not True:
        raise Blocked('suite-v1 attach requires seeds [42,43,44] and streams=true')
    job_lease = job['lease_id']
    if not isinstance(job_lease, str) or not re.fullmatch(r'[A-Za-z0-9_-]{8,80}', job_lease):
        raise Blocked('invalid attach job lease_id')
    if lease_id is not None and job_lease != lease_id:
        raise Blocked('job lease_id differs from --attach-resident')
    try:
        created = datetime.fromisoformat(job['created_utc'].replace('Z', '+00:00'))
        if created.tzinfo is None or created.utcoffset() != timezone.utc.utcoffset(created):
            raise ValueError('not UTC')
    except Exception as exc:
        raise Blocked('created_utc must be timezone-aware UTC ISO-8601') from exc
    return job


def load_attach_job(job_path: str | Path, lease_id: str) -> dict:
    path = Path(job_path)
    if not path.is_file():
        raise Blocked('attach job file is missing or not a regular file')
    try:
        job = json.loads(path.read_text(encoding='utf-8'), object_pairs_hook=_unique_json_object)
    except Exception as exc:
        raise Blocked(f'attach job JSON is invalid: {type(exc).__name__}: {exc}') from exc
    return validate_attach_job(job, lease_id)


def verify_resident_holder(lease_id: str) -> tuple[dict, dict, dict, dict]:
    if not re.fullmatch(r'[A-Za-z0-9_-]{8,80}', lease_id):
        raise Blocked('invalid resident lease ID syntax')
    try:
        claim = json.loads(CLAIM.read_text(encoding='utf-8'))
    except Exception as exc:
        raise Blocked(f'cannot read resident lease claim: {exc}')
    if claim.get('lease_id') != lease_id or claim.get('status') != 'RESIDENT':
        raise Blocked('requested lease is not the exact current RESIDENT holder')
    if claim.get('owner', {}).get('supervisor') != SUPERVISOR or not str(claim.get('owner', {}).get('executor', '')).startswith('P7'):
        raise Blocked('resident claim is not owned by the P7 Winter holder')
    try:
        expiry = datetime.fromisoformat(claim['expires_utc']).timestamp()
        holder = claim['executor']
        holder_pid = int(holder['pid'])
        holder_ticks = int(holder['start_ticks'])
        holder_boot = str(holder['boot_id'])
    except (KeyError, TypeError, ValueError) as exc:
        raise Blocked(f'resident holder claim fields are malformed: {exc}')
    if expiry <= time.time() or holder_boot != current_boot_id():
        raise Blocked('resident holder lease is expired or belongs to another boot')
    try:
        if proc_start_ticks(holder_pid) != holder_ticks:
            raise Blocked('resident holder executor PID/start_ticks do not match the claim')
    except OSError as exc:
        raise Blocked(f'resident holder executor is not live: {exc}')
    holder_identity = {'pid': holder_pid, 'start_ticks': holder_ticks, 'boot_id': holder_boot}
    if set(claim.get('gpus', [])) != {MODELS[a]['gpu_uuid'] for a in ALIASES}:
        raise Blocked('resident holder GPU UUID list differs from the P4b pair')
    model_claims = claim.get('models')
    if not isinstance(model_claims, dict) or set(model_claims) != set(ALIASES):
        raise Blocked('resident holder does not claim exactly the two P4b models')
    staged_hash = claim.get('staged_config_sha256')
    if not staged_hash or claim.get('active_config_sha256') != staged_hash or digest(CONFIG) != staged_hash:
        raise Blocked('active llama-swap config hash differs from the holder staged hash')
    staged_path = Path(claim.get('staged_config_path', ''))
    if not staged_path.is_file() or digest(staged_path) != staged_hash:
        raise Blocked('holder staged config file is missing or differs from its claimed hash')
    backup_path = Path(claim.get('config_backup', ''))
    if not backup_path.is_file() or digest(backup_path) != claim.get('original_config_sha256'):
        raise Blocked('holder-owned config backup is missing or has a different hash')
    gpus = gpu_rows()
    if any(gpu['uuid'] != MODELS[ALIASES[gpu['index']]]['gpu_uuid'] for gpu in gpus):
        raise Blocked('GPU index/UUID mapping differs from the resident pair')
    identities = {}
    discovered = {}
    for alias, expected in MODELS.items():
        recorded = model_claims.get(alias, {})
        fields = {'path': expected['path'], 'sha': expected['sha'],
                  'gpu': expected['gpu_index'], 'expected_gpu_uuid': expected['gpu_uuid'],
                  'port': expected['port'], 'ctx': CTX}
        if any(recorded.get(key) != value for key, value in fields.items()):
            raise Blocked(f'resident claim model identity mismatch for {alias}')
        if not Path(expected['path']).is_file() or digest(Path(expected['path'])) != expected['sha']:
            raise Blocked(f'resident candidate artifact SHA mismatch for {alias}')
        procs = exact_processes(alias)
        if len(procs) != 1:
            raise Blocked(f'expected exactly one pinned backend PID for {alias}, found {len(procs)}')
        proc = procs[0]
        if proc['cuda_visible_devices'] != str(expected['gpu_index']):
            raise Blocked(f'{alias} CUDA_VISIBLE_DEVICES does not match GPU {expected["gpu_index"]}')
        argv = proc['cmd'].split()
        if '--ctx-size' not in argv or argv.index('--ctx-size') + 1 >= len(argv) or argv[argv.index('--ctx-size') + 1] != str(CTX):
            raise Blocked(f'{alias} process command does not specify the pinned {CTX} context')
        endpoint = endpoint_for(proc)
        if not endpoint or endpoint['port'] != expected['port']:
            raise Blocked(f'{alias} exact loopback endpoint is absent or mismatched')
        identity = verify_backend(alias, endpoint)
        identities[alias] = {'backend': endpoint, 'identity': identity}
        discovered[alias] = proc
    if len({row['pid'] for row in discovered.values()}) != len(ALIASES):
        raise Blocked('resident candidates do not have distinct backend PIDs')
    mapping = gpu_pid_map()
    model_pid_rows = {}
    for alias, proc in discovered.items():
        attached = [row for row in mapping if row['pid'] == proc['pid']]
        if not attached or {row['gpu_uuid'] for row in attached} != {MODELS[alias]['gpu_uuid']}:
            raise Blocked(f'{alias} PID is not attributed only to its exact GPU UUID: {attached}')
        model_pid_rows[alias] = {'pid': proc['pid'], 'start_ticks': proc['start_ticks'],
                                 'gpu_uuid': MODELS[alias]['gpu_uuid'], 'memory_rows': attached}
    gpu_identity = {'models': model_pid_rows, 'nvidia_smi_compute_apps': mapping, 'gpus': gpus}
    baseline = {'resident_lease_id': lease_id, 'holder_executor': holder_identity,
                'active_config_sha256': staged_hash, 'staged_config_path': str(staged_path),
                'models': identities, 'gpu_pid_attribution': gpu_identity}
    return claim, holder_identity, identities, {'gpu_identity': gpu_identity, 'baseline': baseline}


def attach_main(lease_id: str, task_filter_arg: str,
                attach_job: dict | None = None) -> int:
    global PARTIAL_RESULT
    PARTIAL_RESULT = None
    if not re.fullmatch(r'[A-Za-z0-9_-]{8,80}', lease_id):
        raise Blocked('invalid resident lease ID syntax')
    stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ') + '-' + uuid.uuid4().hex[:8]
    result_path = P7ROOT / f'attach-result-{lease_id}-{stamp}.json'
    evidence_root = P7ROOT / f'attach-evidence-{lease_id}-{stamp}'
    result = None
    try:
        selected = parse_attach_tasks(task_filter_arg)
        tasks_data, manifest, suite_ref, p4refs, merge_prompt, parse_prompt, prefill_prompt = check_suite_and_p4(
            selected, suite_v1=True)
        claim, holder_identity, identities, attached = verify_resident_holder(lease_id)
        guard = AttachedLease(claim, f'attach-{lease_id}-{stamp}', evidence_root,
                              holder_identity, identities, attached['gpu_identity'])
        guard.check()
        result = run_benchmark(tasks_data, manifest, suite_ref, p4refs, merge_prompt,
                               parse_prompt, prefill_prompt, attached['baseline'], guard,
                               selected_task_ids=selected, client_only=True, result_path=result_path)
        if attach_job is not None:
            result['attach_job_protocol'] = P7_ATTACH_JOB_PROTOCOL
            result['attach_job'] = attach_job
        result['status'] = 'COMPLETE'
        result['attach_verification'] = attached['baseline']
    except Exception as exc:
        result = PARTIAL_RESULT or {'task': 'P7 client-only resident attach', 'task_results': []}
        result.update({'status': 'BLOCKED', 'client_only_attach': True,
                       'lease_id': lease_id, 'result_path': str(result_path),
                       'error': f'{type(exc).__name__}: {exc}'})
    if result is None:
        result = {'task': 'P7 client-only resident attach', 'status': 'BLOCKED',
                  'lease_id': lease_id, 'result_path': str(result_path),
                  'error': 'attach ended without a client result'}
    result['end_utc'] = utc()
    if attach_job is not None:
        result['attach_job_protocol'] = P7_ATTACH_JOB_PROTOCOL
        result['attach_job'] = attach_job
    result['holder_lease_mutated'] = False
    result['holder_cleanup_attempted'] = False
    persist_result(result, result_path)
    print(f'{result["status"]} client_result={result_path}', flush=True)
    return 0 if result['status'] == 'COMPLETE' else 2


def attach_job_main(lease_id: str, job_file: str) -> int:
    # Full exact-key/schema/hash/task/seed/stream/lease validation happens
    # before attach_main can inspect the holder or make any API request.
    job = load_attach_job(job_file, lease_id)
    task_map = {'merge_intervals': '13_merge_intervals',
                'parse_records': '14_parse_records'}
    selected = [task_map.get(task_id, task_id) for task_id in job['task_ids']]
    return attach_main(lease_id, ','.join(selected), attach_job=job)


def wait_for_go(token: str, lease: Lease) -> bool:
    lines: queue.Queue = queue.Queue()
    def reader():
        lines.put(sys.stdin.readline())
    threading.Thread(target=reader, name='p7-go-reader', daemon=True).start()
    while time.time() < lease.deadline:
        lease.check()
        try:
            line = lines.get(timeout=0.25)
        except queue.Empty:
            continue
        if line.strip() == token:
            return True
        if not line:
            time.sleep(0.25)
    return False


if __name__ == '__main__':
    try:
        if any(arg == '--attach-resident' or arg.startswith('--attach-resident=') for arg in sys.argv[1:]):
            parser = argparse.ArgumentParser(description='Client-only P7 attach to a current RESIDENT holder lease')
            parser.add_argument('--attach-resident', required=True, metavar='LEASE_ID')
            parser.add_argument('--job-file', help='exact suite-v1-job-v1 JSON file used by the queue feeder')
            parser.add_argument('--tasks', help='comma-separated suite-v1 tasks 01-10 plus external P4 tasks')
            parser.add_argument('--seeds', help='must be 42,43,44 when specified')
            parser.add_argument('--streams', action='store_true')
            attach_args = parser.parse_args()
            if attach_args.job_file:
                if attach_args.tasks is not None or attach_args.seeds is not None or attach_args.streams:
                    raise Blocked('--job-file cannot be combined with --tasks, --seeds, or --streams')
                raise SystemExit(attach_job_main(attach_args.attach_resident, attach_args.job_file))
            if attach_args.tasks is None:
                raise Blocked('attach mode requires --job-file or --tasks')
            if attach_args.seeds is not None and attach_args.seeds != '42,43,44':
                raise Blocked('--seeds must be exactly 42,43,44')
            raise SystemExit(attach_main(attach_args.attach_resident, attach_args.tasks))
        if sys.argv[1:]:
            raise Blocked('unrecognized runner arguments; no lease-owning benchmark was started')
        raise SystemExit(main())
    except Blocked as exc:
        print(f'P7 BLOCKED before/after lease: {exc}', file=sys.stderr, flush=True)
        raise SystemExit(2)
