#!/usr/bin/env python3
"""Deterministic offline telemetry analyzer for Hermes ``--format stream-json`` JSONL.

Standard library only, no clocks, no mutation of the input.  It reports measured
evidence and never invents any:

  * model turns: authoritative per-call evidence when present, otherwise a clearly
    labelled heuristic over assistant segments;
  * token aggregates: gateway ``result`` record, else deduplicated per-call sum,
    else a cumulative-delta maximum marked approximate; streaming deltas are never
    summed into the aggregate and cache fields are never folded into input;
  * unknown telemetry is ``None``; a gateway-reported zero stays ``0``;
  * tool-call summaries with pairing, errors, durations, and terminal exit codes;
  * first/final Cargo invocations with full diagnostics;
  * malformed lines, truncated tails and interrupted runs are classified, not fatal.

CLI:  python3 hermes_telemetry.py [--compact] FILE [FILE ...]
"""
import json, re, sys
from pathlib import Path

SCHEMA='gyro.hermes.telemetry.v1'
TOKEN_FIELDS=('input','output','total','cache_read','cache_write')
CALL_TYPES=frozenset(('api_call','api_call_complete','api_response','assistant','assistant_message','model_call','model_response','turn_complete'))
RESULT_TYPES=frozenset(('result','session_result','run_result'))
DELTA_TYPES=frozenset(('text','text_delta','delta'))
TOOL_USE_TYPES=frozenset(('tool_use','tool_call'))
TOOL_RESULT_TYPES=frozenset(('tool_result','tool_observation'))
SYSTEM_TYPES=frozenset(('system','init'))
ID_KEYS=('request_id','api_call_id','api_request_id','completion_id','response_id','call_id','tool_call_id','id')
USE_KEYS=('usage','tokens','token_usage')
TURN_KEYS=('num_turns','turns','turn_count','api_calls')
TERMINAL_TOOLS=frozenset(('terminal','shell','bash','exec','run_command'))
USE_ALTS={'input':'input','input_tokens':'input','prompt_tokens':'input','prompt':'input',
          'output':'output','output_tokens':'output','completion_tokens':'output','generation_tokens':'output',
          'total':'total','total_tokens':'total','cache_read':'cache_read','cached_tokens':'cache_read',
          'cache_read_input_tokens':'cache_read','cache_write':'cache_write','cache_creation_input_tokens':'cache_write'}
INT_RE=re.compile(r'^-?[0-9]+$')
CARGO_RE=re.compile(r'cargo(?![\w.-])')
SUITE_RE=re.compile(r'test result:\s*(\w+)\.?\s*(\d+) passed;\s*(\d+) failed;\s*(\d+) ignored')
RUN_RE=re.compile(r'running (\d+) tests')
ECODE_RE=re.compile(r'error\[[^\]]+\]')
ERR_LINE_RE=re.compile(r'^error\W', re.M)
PANIC_RE=re.compile(r'panicked at|^thread .* panicked', re.M)

def _int(value):
    """Int when genuinely measurable; None for null/absent/nonfinite/placeholder text."""
    if isinstance(value, bool) or value is None: return None
    if isinstance(value, int): return value
    if isinstance(value, float):
        return int(value) if value == value and value not in (float('inf'), float('-inf')) else None
    if isinstance(value, str):
        s=value.strip()
        return int(s) if INT_RE.match(s) else None
    return None

def _pos(value):
    """Non-negative measurable, used for token/duration counters."""
    n=_int(value)
    return n if n is not None and n>=0 else None

def _usage(candidate):
    """Canonical token dict from a mapping, or None when no field is measurable."""
    if not isinstance(candidate, dict): return None
    out=dict.fromkeys(TOKEN_FIELDS)
    known=False
    for key, value in candidate.items():
        field=USE_ALTS.get(key)
        n=_pos(value)
        if field and n is not None: out[field]=n; known=True
    return out if known else None

def _usage_of(record):
    """First usage-bearing payload in a record, including nested ``message``."""
    for key in USE_KEYS:
        u=_usage(record.get(key))
        if u: return u
    nested=record.get('message')
    if isinstance(nested, dict):
        for key in USE_KEYS:
            u=_usage(nested.get(key))
            if u: return u
    return None

def _id_of(record):
    for key in ID_KEYS:
        v=record.get(key)
        if isinstance(v, (str, int)) and str(v): return str(v)
    return None

def _text_of(value):
    if isinstance(value, str): return value
    if value is None: return ''
    try: return json.dumps(value, sort_keys=True)
    except Exception: return str(value)

def _cargo_kinds(command):
    """Cargo subwords in a shell command, in order of appearance."""
    if not isinstance(command, str) or 'cargo' not in command: return []
    kinds=[]
    for m in CARGO_RE.finditer(command):
        tail=command[m.end():]
        for tok in tail.split():
            if tok.startswith('-'): continue
            kinds.append(tok.rstrip('&|;'))
            break
    return [k for k in kinds if k]

def _terminal_payload(output):
    """`{"output":..,"exit_code":N,"error":..}` payload emitted by the terminal tool."""
    if isinstance(output, dict): return output
    if not isinstance(output, str): return None
    s=output.strip()
    if not s.startswith('{'): return None
    try: parsed=json.loads(s)
    except Exception: return None
    return parsed if isinstance(parsed, dict) else None

def _test_summary(output):
    """Cargo test suites, error codes and pass/fail evidence from full output text."""
    suites=[]; codes={}
    running=None
    for line in output.splitlines():
        m=RUN_RE.search(line)
        if m: running=_pos(m.group(1))
        m=SUITE_RE.search(line)
        if m:
            suites.append({'header':running,'status':m.group(1),'passed':int(m.group(2)),
                           'failed':int(m.group(3)),'ignored':int(m.group(4)),
                           'ok':m.group(1).lower().startswith('ok')})
            running=None
        for code in ECODE_RE.findall(line): codes[code]=codes.get(code,0)+1
    passed=sum(s['passed'] for s in suites); failed=sum(s['failed'] for s in suites)
    return {'suites':len(suites),'tests_passed':passed if suites else None,'tests_failed':failed if suites else None,
            'all_ok':bool(suites) and all(s['ok'] for s in suites) or None,
            'error_codes':dict(sorted(codes.items())) or None,
            'error_lines':len(ERR_LINE_RE.findall(output)) or None,
            'panic_lines':len(PANIC_RE.findall(output)) or None,
            'compile_observed':('compiling' in output.lower() or 'finished' in output.lower()) or None}

class StreamTelemetry:
    """Incremental accumulator; feed lines in order, then call report()."""

    def __init__(self, source=None, diagnostics_chars=20000):
        self.source=source
        self.diagnostics_chars=diagnostics_chars
        self.lines=0; self.blank_lines=0; self.records=0
        self.malformed_count=0; self.malformed_samples=[]
        self.non_object=0; self.untyped=0
        self.truncated_tail=False
        self.init=None; self.inits=0
        self.model=None; self.session_id=None
        self.calls=[]; self.call_ids=set(); self.calls_without_id=0; self.duplicate_call_ids=0
        self.result=None; self.results=0; self.result_tokens=None; self.result_exit=None
        self.result_turns=None; self.result_duration_ms=None; self.result_text_chars=None
        self.delta_usage_records=0; self.delta_usage=[]
        self.text_deltas=0; self.stream_text_chars=0
        self.tool_uses=0; self.tool_results=0
        self.open_tools={}; self.unmatched_results=[]; self.duplicate_result_ids=[]
        self.tools={}
        self.segment_open=False; self.turns_heuristic=0
        self.timestamps=[]; self.cargo=[]; self.order=0

    # ---- ingestion ---------------------------------------------------------
    def feed_text(self, text):
        lines=text.splitlines()
        tail_open=bool(text) and not text.endswith(('\n','\r'))
        for index, line in enumerate(lines):
            self._feed(line, index+1, last=(tail_open and index==len(lines)-1))
        return self

    def feed_file(self, path):
        path=Path(path)
        try: text=path.read_text(errors='replace')
        except FileNotFoundError: self.status_override='missing_file'
        except OSError as exc: self.status_override='unreadable:%s'%(getattr(exc,'errno','os') or exc.__class__.__name__)
        else: self.feed_text(text)
        return self

    def _malformed(self, lineno, line, reason, last):
        self.malformed_count+=1
        if last and not line.strip(): self.truncated_tail=True
        if len(self.malformed_samples)<5:
            self.malformed_samples.append({'line':lineno,'reason':reason,'head':line.strip()[:160]})

    def _feed(self, line, lineno, last=False):
        self.lines+=1
        stripped=line.strip()
        if not stripped:
            self.blank_lines+=1
            return
        try: record=json.loads(stripped)
        except ValueError as exc:
            self._malformed(lineno, line, exc.args[0] if exc.args else type(exc).__name__, last)
            return
        if not isinstance(record, dict):
            self.non_object+=1
            return
        self.records+=1
        kind=record.get('type')
        if not isinstance(kind, str): self.untyped+=1
        ts=_int(record.get('timestamp'))
        if ts is not None: self.timestamps.append(ts)
        handler=self._KINDERS.get(kind or '')
        if handler: handler(self, record)
        elif _usage_of(record) or _id_of(record): self._call(record, kind or 'untyped')
        else: self.untyped+=1 if not isinstance(kind, str) else 0

    # ---- per-type handlers ----------------------------------------------
    def _system(self, record):
        self.inits+=1
        if self.init is None:
            self.init={'subtype':record.get('subtype') if isinstance(record.get('subtype'), str) else None,
                       'model':record.get('model') if isinstance(record.get('model'), str) else None,
                       'session_id':record.get('session_id') if isinstance(record.get('session_id'), str) else None}
        self.model=self.model or (record.get('model') if isinstance(record.get('model'), str) else None)
        self.session_id=self.session_id or (record.get('session_id') if isinstance(record.get('session_id'), str) else None)

    def _delta(self, record):
        text=record.get('text')
        if isinstance(text, str):
            self.text_deltas+=1; self.stream_text_chars+=len(text)
            if not self.segment_open: self.segment_open=True; self.turns_heuristic+=1
        usage=_usage_of(record)
        if usage:
            self.delta_usage_records+=1
            previous=self.delta_usage[-1] if self.delta_usage else None
            if usage != previous: self.delta_usage.append(usage)   # cumulative stamps collapse; only maxima used

    def _call(self, record, kind):
        usage=_usage_of(record)
        ident=_id_of(record)
        if ident is None: self.calls_without_id+=1
        elif ident in self.call_ids: self.duplicate_call_ids+=1
        else: self.call_ids.add(ident)
        self.calls.append({'kind':kind,'id':ident,'usage':usage})

    def _tool_use(self, record):
        self.tool_uses+=1
        name=record.get('name') if isinstance(record.get('name'), str) else '<unknown>'
        ident=_id_of(record) or 'anon-%d' % self.tool_uses
        if not self.segment_open: self.segment_open=True; self.turns_heuristic+=1
        stat=self._stat(name); stat['calls']+=1
        invocation={'order':len(self.cargo)+1,'source':'stream','kind':None,'command':None,
                    'tool':name,'tool_call_id':ident,'exit_code':None,'is_error':None,
                    'duration_ms':None,'output':None,'output_chars':None,'output_truncated':False,'test':None}
        self.order+=1
        pending={'name':name,'id':ident,'invocations':[]}
        input_value=record.get('input')
        if isinstance(input_value, dict):
            command=input_value.get('command')
            if isinstance(command, str): invocation['command']=command
            for kind in _cargo_kinds(command):
                copy=dict(invocation, kind=kind, order=len(self.cargo)+1)
                self.cargo.append(copy); pending['invocations'].append(copy)
        self.open_tools[ident]=pending

    def _tool_result(self, record):
        self.tool_results+=1
        self.segment_open=False                       # next model activity is a new turn
        name=record.get('name') if isinstance(record.get('name'), str) else '<unknown>'
        ident=_id_of(record)
        pending=self.open_tools.pop(ident, None)
        if pending is None:
            if ident is None: self.unmatched_results.append('<anonymous>')
            else: self.unmatched_results.append(ident)
            stat=self._stat(name)
        else:
            stat=self._stat(pending['name'])
        stat['results']+=1
        if record.get('is_error') is True: stat['errors']+=1
        duration=_pos(record.get('duration_ms'))
        if duration is not None:
            stat['duration_ms_total']+=duration; stat['duration_ms_max']=max(stat['duration_ms_max'] or 0, duration)
        payload=_terminal_payload(record.get('output'))
        exit_code=_int(payload.get('exit_code')) if payload else None
        text=_text_of(payload.get('output')) if payload and 'output' in payload else _text_of(record.get('output'))
        stat['output_chars']+=len(text)
        if name in TERMINAL_TOOLS or payload is not None:
            key=str(exit_code) if exit_code is not None else 'unknown'
            stat['exit_codes'][key]=stat['exit_codes'].get(key, 0)+1
        for invocation in (pending or {}).get('invocations', ()):
            body=text if len(text)<=self.diagnostics_chars else text[:self.diagnostics_chars]
            invocation.update({'exit_code':exit_code,'is_error':record.get('is_error') is True,
                               'duration_ms':duration,'output':body,
                               'output_chars':len(text),'output_truncated':len(text)>self.diagnostics_chars,
                               'test':_test_summary(body) if invocation['kind']=='test' else None})

    def _result(self, record):
        self.results+=1
        self.result=record
        self.result_tokens=_usage_of(record)
        self.result_exit=_int(record.get('exit_code'))
        self.result_duration_ms=_pos(record.get('duration_ms'))
        text=record.get('text')
        self.result_text_chars=len(text) if isinstance(text, str) else None
        for key in TURN_KEYS:
            turns=_pos(record.get(key))
            if turns is not None: self.result_turns=turns; break
        if self.result_tokens:
            if not self.segment_open: self.segment_open=True; self.turns_heuristic+=1

    def _stat(self, name):
        stat=self.tools.get(name)
        if stat is None:
            stat={'calls':0,'results':0,'errors':0,'exit_codes':{},'duration_ms_total':0,
                  'duration_ms_max':None,'output_chars':0}
            self.tools[name]=stat
        return stat

    # ---- derivation ------------------------------------------------------
    def _per_call_total(self):
        """Deduplicated per-call sum: each identified call counted once."""
        total=dict.fromkeys(TOKEN_FIELDS); calls=0; seen=set()
        for call in self.calls:
            if call['id'] is not None:
                if call['id'] in seen: continue
                seen.add(call['id'])
            calls+=1
            for field, value in (call['usage'] or {}).items():
                if value is not None: total[field]=(total[field] or 0)+value
        known=any(v is not None for v in total.values())
        return (total if known else None), calls

    def _delta_max(self):
        total=dict.fromkeys(TOKEN_FIELDS); known=False
        for usage in self.delta_usage:
            for field, value in usage.items():
                if value is not None:
                    total[field]=max(total[field] or 0, value); known=True
        return total if known else None

    def _tokens(self, per_call, per_call_calls):
        chosen=None; source='unknown'; exact=False; derived=[]
        if self.result_tokens:
            chosen=dict(self.result_tokens); source='result_record'; exact=True
        elif per_call:
            chosen=dict(per_call); source='per_call_sum'; exact=True
        elif self._delta_max():
            chosen=self._delta_max(); source='delta_cumulative_max'; exact=False
        if chosen is not None and chosen.get('total') is None:
            if chosen.get('input') is not None and chosen.get('output') is not None:
                chosen['total']=chosen['input']+chosen['output']; derived.append('total=input+output')
        agreement=None
        if self.result_tokens and per_call:
            agreement=self.result_tokens==per_call
        zero=chosen is not None and all(v==0 for v in chosen.values())
        return {'input':chosen and chosen['input'], 'output':chosen and chosen['output'],
                'total':chosen and chosen['total'], 'cache_read':chosen and chosen['cache_read'],
                'cache_write':chosen and chosen['cache_write'],
                'source':source, 'exact':exact,
                'unknown_fields':[f for f in TOKEN_FIELDS if (chosen or {}).get(f) is None],
                'reported_zero':bool(zero),
                'per_call_sum':per_call, 'per_call_records':per_call_calls,
                'result_record_tokens':self.result_tokens,
                'delta_usage_records':self.delta_usage_records,
                'delta_cumulative_max':self._delta_max(),
                'result_and_per_call_agree':agreement,
                'derived':derived or None,
                'double_counting_guard':{'stream_deltas_included':False,
                                        'cache_merged_into_input':False,
                                        'result_and_per_call_summed':False,
                                        'duplicate_call_ids_collapsed':self.duplicate_call_ids}}

    def _turns(self):
        authoritative=None; source='none'
        if self.calls:
            identified=len(self.call_ids)
            authoritative=identified+self.calls_without_id if self.calls_without_id else identified
            source='authoritative_per_call_evidence'
        elif self.result_turns is not None:
            authoritative=self.result_turns; source='authoritative_result_field'
        heuristic=self.turns_heuristic if self.segment_open or self.turns_heuristic else None
        reported=authoritative if authoritative is not None else heuristic
        if reported is not None and source=='none': source='heuristic_assistant_segments'
        return {'reported':reported,'source':source,
                'authoritative':authoritative,'heuristic':heuristic,
                'authoritative_kinds':sorted({c['kind'] for c in self.calls}) or None,
                'note':'heuristic is a lower bound when the stream is interrupted' if reported is heuristic else None}

    def _tools(self):
        terminal={'calls':0,'results':0,'errors':0,'exit_codes':{},'duration_ms_total':0,'duration_ms_max':None}
        for name, stat in self.tools.items():
            if name in TERMINAL_TOOLS:
                terminal['calls']+=stat['calls']; terminal['results']+=stat['results']
                terminal['errors']+=stat['errors']; terminal['duration_ms_total']+=stat['duration_ms_total']
                terminal['duration_ms_max']=max([terminal['duration_ms_max'] or 0, stat['duration_ms_max'] or 0]) if stat['duration_ms_max'] else terminal['duration_ms_max']
                for key, value in stat['exit_codes'].items():
                    terminal['exit_codes'][key]=terminal['exit_codes'].get(key, 0)+value
        terminal['unknown_exit_results']=terminal['exit_codes'].get('unknown')
        terminal['outcome']=None if not terminal['results'] else ('all_success' if terminal['exit_codes'].keys()=={'0'} and not terminal['errors']
                              else 'any_failure' if any(k not in ('0','unknown') for k in terminal['exit_codes']) or terminal['errors']
                              else 'mixed_or_unknown')
        return {'calls':self.tool_uses,'results':self.tool_results,
                'errors':sum(s['errors'] for s in self.tools.values()),
                'by_name':{name:self.tools[name] for name in sorted(self.tools)},
                'terminal':terminal,
                'unpaired_calls':[{'tool':v['name'],'tool_call_id':v['id'],'command':(v['invocations'] or [{}])[0].get('command')}
                                  for v in sorted(self.open_tools.values(), key=lambda v: v['id'])] or None,
                'unmatched_results':sorted(set(self.unmatched_results)) or None,
                'result_without_call':len(self.unmatched_results)}

    def _cargo(self):
        tests=[i for i in self.cargo if i['kind']=='test']
        kinds={}
        for invocation in self.cargo: kinds[invocation['kind']]=kinds.get(invocation['kind'], 0)+1
        return {'invocation_count':len(self.cargo),'kinds':kinds or None,
                'test_count':len(tests),'first':tests[0] if tests else None,'final':tests[-1] if tests else None,
                'invocations':self.cargo}

    def report(self):
        per_call, per_call_calls=self._per_call_total()
        complete=self.results>0
        if getattr(self,'status_override',None)=='missing_file': status, reason='missing','missing_file'
        elif getattr(self,'status_override',None): status, reason='unreadable',self.status_override
        elif complete: status, reason='complete',None
        elif self.lines==0: status, reason='empty','no_bytes'
        elif self.records==0: status, reason='unanalysable','no_structured_records'
        elif self.truncated_tail: status, reason='interrupted','truncated_tail'
        else: status, reason='interrupted','no_result_record'
        flags=[]
        if self.malformed_count: flags.append('malformed_lines')
        if self.truncated_tail: flags.append('truncated_tail')
        if self.non_object: flags.append('non_object_records')
        if self.open_tools: flags.append('unpaired_tool_calls')
        if self.unmatched_results: flags.append('unmatched_tool_results')
        if self.calls_without_id: flags.append('per_call_evidence_without_id')
        if self.duplicate_call_ids: flags.append('duplicate_call_ids_collapsed')
        if self.delta_usage_records: flags.append('delta_token_records_excluded')
        if self.results>1: flags.append('multiple_result_records_last_wskipped')
        if self.inits>1: flags.append('multiple_init_records')
        return {'schema':SCHEMA,'source':self.source,'status':status,'status_reason':reason,'flags':flags or None,
                'lines':self.lines,'records':self.records,'blank_lines':self.blank_lines,
                'non_object_records':self.non_object,'untyped_records':self.untyped,
                'malformed_lines':self.malformed_count,'malformed_samples':self.malformed_samples or None,
                'init':self.init,'model':self.model,'session_id':self.session_id,
                'turns':self._turns(),'tokens':self._tokens(per_call, per_call_calls),
                'tools':self._tools(),'cargo':self._cargo(),
                'run':{'complete':complete,'result_count':self.results,'result_exit_code':self.result_exit,
                       'duration_ms':self.result_duration_ms,'result_text_chars':self.result_text_chars,
                       'stream_text_chars':self.stream_text_chars,'text_delta_records':self.text_deltas,
                       'first_timestamp':min(self.timestamps) if self.timestamps else None,
                       'last_timestamp':max(self.timestamps) if self.timestamps else None},
                'process':{'exit_code':None,'source':None}}

    _KINDERS={'system':_system,'init':_system,'text':_delta,'text_delta':_delta,'delta':_delta,
             'tool_use':_tool_use,'tool_call':_tool_use,'tool_result':_tool_result,'tool_observation':_tool_result,
             'result':_result,'session_result':_result,'run_result':_result}


def analyze_text(text, source=None, verifications=()):
    """Analyze JSONL text; `verifications` are externally run cargo checks appended last."""
    acc=StreamTelemetry(source=source)
    acc.feed_text(text)
    _extend(acc, verifications)
    return acc.report()

def analyze_file(path, verifications=()):
    """Analyze a JSONL file; missing/unreadable files are reported, never raised."""
    acc=StreamTelemetry(source=str(path))
    acc.feed_file(path)
    _extend(acc, verifications)
    return acc.report()

def _extend(acc, verifications):
    for item in verifications or ():
        command=item.get('command') if isinstance(item, dict) else None
        output=_text_of(item.get('output') if isinstance(item, dict) else item)
        kinds=_cargo_kinds(command) or ['test']
        for kind in kinds:
            acc.cargo.append({'order':len(acc.cargo)+1,'source':item.get('source','external') if isinstance(item, dict) else 'external',
                              'kind':kind,'command':command,'tool':None,'tool_call_id':None,
                              'exit_code':_int(item.get('exit_code') if isinstance(item, dict) else None),
                              'is_error':bool(item.get('is_error')) if isinstance(item, dict) else False,
                              'duration_ms':_pos(item.get('duration_ms') if isinstance(item, dict) else None),
                              'output':output[:acc.diagnostics_chars],'output_chars':len(output),
                              'output_truncated':len(output)>acc.diagnostics_chars,
                              'test':_test_summary(output) if kind=='test' else None})

def digest(report):
    """Compact, deterministic summary for console and summary files."""
    tokens=report['tokens']; turns=report['turns']; cargo=report['cargo']; terminal=report['tools']['terminal']
    def slim(invocation):
        if not invocation: return None
        test=invocation.get('test') or {}
        return {'order':invocation['order'],'source':invocation['source'],'exit_code':invocation['exit_code'],
                'tests_passed':test.get('tests_passed'),'tests_failed':test.get('tests_failed'),
                'error_codes':list((test.get('error_codes') or {}))[:8],'command':invocation['command']}
    return {'status':report['status'],'status_reason':report['status_reason'],'flags':report['flags'],
            'turns':turns['reported'],'turn_source':turns['source'],
            'tokens_input':tokens['input'],'tokens_output':tokens['output'],'tokens_total':tokens['total'],
            'cache_read':tokens['cache_read'],'cache_write':tokens['cache_write'],'token_source':tokens['source'],
            'tools':report['tools']['calls'],'tool_errors':report['tools']['errors'],
            'terminal_exit_codes':terminal['exit_codes'] or None,'terminal_outcome':terminal['outcome'],
            'cargo_first':slim(cargo['first']),'cargo_final':slim(cargo['final']),
            'process_exit':report['process']['exit_code']}

def main(argv=None):
    argv=list(sys.argv[1:] if argv is None else argv)
    compact='--compact' in argv
    paths=[a for a in argv if a!='--compact']
    if not paths:
        print(__doc__.strip().splitlines()[-1], file=sys.stderr); return 2
    reports=[analyze_file(p) for p in paths]
    for report in reports:
        payload=digest(report) if compact else report
        print(json.dumps(payload, sort_keys=True))
    return 0

if __name__=='__main__':
    raise SystemExit(main())
