#!/usr/bin/env python3
"""Run independent P7 oracle checks and regenerate frozen manifest hashes."""
from copy import deepcopy
from datetime import datetime, timezone
import argparse, hashlib, itertools, json, random
from pathlib import Path
import reference as R

ROOT = Path(__file__).resolve().parent
TASKS = ROOT / "tasks.json"
MANIFEST = ROOT / "manifest.json"

def digest_bytes(b): return hashlib.sha256(b).hexdigest()
def digest_text(s): return digest_bytes(s.encode("utf-8"))
def expect_error(fn, *args):
    R.require_exact_error(ValueError, fn, *args)

def exhaustive_interval_count(jobs):
    best = 0
    for bits in range(1 << len(jobs)):
        chosen = [jobs[i] for i in range(len(jobs)) if bits & (1 << i)]
        if all(a[2] <= b[1] or b[2] <= a[1] for i,a in enumerate(chosen) for b in chosen[i+1:]):
            best = max(best, len(chosen))
    return best

def check_toposort(rng):
    assert R.toposort(["a","b","c","d"], {"c":["a"],"d":["b"]}) == ["a","b","c","d"]
    expect_error(R.toposort, ["a","a"], {})
    expect_error(R.toposort, ["a"], {"a":["missing"]})
    expect_error(R.toposort, ["a","b"], {"a":["b"],"b":["a"]})
    n_cases = 0
    for _ in range(100):
        n = rng.randrange(1, 10); nodes = [f"n{i}" for i in range(n)]
        order = nodes[:]; rng.shuffle(order); deps = {x:[] for x in nodes}
        for j, node in enumerate(order):
            deps[node] = [prior for prior in order[:j] if rng.random() < .23]
        before = deepcopy(deps); result = R.toposort(nodes, deps); pos = {x:i for i,x in enumerate(result)}
        assert set(result) == set(nodes) and len(result) == n and deps == before
        assert all(pos[d] < pos[x] for x, ds in deps.items() for d in ds)
        n_cases += 1
    return 4 + n_cases

def check_json_pointer():
    obj = {"a/b":{"~key":[{"x":9},None]},"":7}
    before = deepcopy(obj)
    assert R.json_pointer_get(obj, "") == obj
    assert R.json_pointer_get(obj, "/a~1b/~0key/0/x") == 9
    assert R.json_pointer_get(obj, "/") == 7
    for bad in ("a", "/x~", "/x~2"):
        R.require_exact_error(ValueError, R.json_pointer_get, obj, bad)
    R.require_exact_error(KeyError, R.json_pointer_get, obj, "/missing")
    R.require_exact_error(IndexError, R.json_pointer_get, obj, "/a~1b/~0key/00")
    R.require_exact_error(IndexError, R.json_pointer_get, obj, "/a~1b/~0key/7")
    R.require_exact_error(TypeError, R.json_pointer_get, obj, "/a~1b/~0key/0/x/y")
    assert obj == before
    assert R.evaluate_json_pointer_candidate(R.json_pointer_get)
    return {"fixed_cases":10,"candidate_exception_cases":10,"candidate_success_cases":1,"huge_index_cases":2}

def check_safe_join():
    assert R.safe_join("/srv//app/.", "./foo//bar") == "/srv/app/foo/bar"
    assert R.safe_join("/", "") == "/"
    assert R.safe_join("/srv/app", "a\\b") == "/srv/app/a\\b"
    for root, rel in (("srv", "x"),("/srv", "/etc/passwd"),("/srv", "../x"),("/srv", "a/../b"),("/srv\0x","a"),("/srv", "x\0y")):
        expect_error(R.safe_join, root, rel)
    return 9

def check_retry(rng):
    assert R.retry_delays(6,2,10) == [2,4,8,10,10,10]
    assert R.retry_delays(0,1,1) == []
    for args in ((-1,1,2),(1,0,2),(1,3,2),(True,1,2),(1,False,2),(1,1,True)):
        expect_error(R.retry_delays, *args)
    n=0
    for _ in range(200):
        count=rng.randrange(0,20); base=rng.randrange(1,100); cap=rng.randrange(base,10000)
        got=R.retry_delays(count,base,cap)
        assert got == [min(base*(2**i),cap) for i in range(count)]
        assert all(a<=b for a,b in zip(got,got[1:])) and all(x<=cap for x in got)
        n+=1
    return 8+n

def check_pack_batches(rng):
    fixed=R.pack_batches([("a",4),("b",3),("c",6),("d",2)],3,8)
    assert fixed == [["a","b"],["c","d"]]
    for items,mc,mw in (([("a",9)],2,8), ([("a",1),("a",2)],2,8), ([("a",True)],2,8),([],0,8)):
        expect_error(R.pack_batches,items,mc,mw)
    count=0
    for _ in range(100):
        n=rng.randrange(0,30); items=[(f"i{i}",rng.randrange(1,9)) for i in range(n)]
        mc=rng.randrange(1,8); mw=rng.randrange(1,20)
        items=[p for p in items if p[1]<=mw]
        batches=R.pack_batches(items,mc,mw)
        assert [x for b in batches for x in b] == [x[0] for x in items]
        assert all(len(b)<=mc and sum(dict(items)[x] for x in b)<=mw for b in batches)
        count+=1
    return 5+count

def check_lru():
    ops=[["put","a",1],["put","b",2],["get","a"],["put","c",3],["get","b"],["get","a"],["get","c"]]
    got=R.lru_trace(2,ops)
    assert got == [
        {"key":"a","found":True,"value":1},
        {"key":"b","found":False,"value":None},
        {"key":"a","found":True,"value":1},
        {"key":"c","found":True,"value":3},
    ]
    assert R.lru_trace(0,[["put","a",1],["get","a"]]) == [{"key":"a","found":False,"value":None}]
    expect_error(R.lru_trace, True, [])
    expect_error(R.lru_trace, 2, [["wat","x"]])
    expect_error(R.lru_trace, 1, [["put","x",float("nan")]])
    assert ops[0] == ["put","a",1]
    return 6

def check_redact():
    text="API_KEY=Abcd_123! Bearer token-ABC_1234, api_key=untouched123456"
    assert R.redact_secrets(text) == "API_KEY=[REDACTED]! Bearer [REDACTED], api_key=untouched123456"
    assert R.redact_secrets("API_KEY=short Bearer abcdefg") == "API_KEY=short Bearer abcdefg"
    assert R.redact_secrets("Bearer abcdefghX") == "Bearer [REDACTED]"
    expect_error(R.redact_secrets, None)
    return 4

def check_intervals(rng):
    fixed=[("a",0,3),("b",3,5),("c",1,2),("d",2,4)]
    assert R.select_nonoverlapping(fixed)==["c","d"]
    for bad in (([("x",1,1)]),([("x",0,1),("x",2,3)]),([("x",True,3)])):
        expect_error(R.select_nonoverlapping,bad)
    n=0
    for _ in range(250):
        jobs=[]
        for i in range(rng.randrange(0,9)):
            start=rng.randrange(0,12); end=rng.randrange(start+1,14); jobs.append((f"j{i}",start,end))
        chosen=R.select_nonoverlapping(jobs)
        assert len(chosen)==exhaustive_interval_count(jobs)
        lookup={x[0]:x for x in jobs}
        assert all(lookup[a][2]<=lookup[b][1] for a,b in zip(chosen,chosen[1:]))
        n+=1
    return 4+n

def check_logs():
    records=[{"service":"api","timestamp":8,"severity":"error"},{"service":"worker","timestamp":4,"severity":"info"},{"service":"api","timestamp":2,"severity":"warning"}]
    expected=[
        {"service":"api","count":2,"severity_counts":{"debug":0,"info":0,"warning":1,"error":1},"first_timestamp":2,"last_timestamp":8},
        {"service":"worker","count":1,"severity_counts":{"debug":0,"info":1,"warning":0,"error":0},"first_timestamp":4,"last_timestamp":4},
    ]
    assert R.aggregate_logs(records)==expected and R.aggregate_logs([])==[]
    for bad in ([{"service":"x","timestamp":True,"severity":"info"}],[{"service":"x","timestamp":1,"severity":"fatal"}], [None]):
        expect_error(R.aggregate_logs,bad)
    assert records[0]["timestamp"]==8
    assert R.evaluate_logs_candidate(R.aggregate_logs)
    def extra_output(records):
        return [dict(row, extra=1) for row in R.aggregate_logs(records)]
    R.require_exact_error(AssertionError, R.evaluate_logs_candidate, extra_output)
    return {"fixed_cases":6,"candidate_schema_cases":2,"extra_output_rejected":True}

def check_closure(rng):
    graph={"a":["b","c"],"b":["c"],"c":["a"],"z":[]}
    assert R.dependency_closure(graph,["a"])==["a","b","c"]
    expect_error(R.dependency_closure,{"a":["missing"]},["a"])
    expect_error(R.dependency_closure,{"a":["a","a"]},["a"])
    expect_error(R.dependency_closure,{"a":[]},["z"])
    n=0
    for _ in range(100):
        nodes=[f"n{i}" for i in range(rng.randrange(1,12))]
        graph={x:[] for x in nodes}
        for x in nodes:
            graph[x]=[y for y in nodes if rng.random()<.12]
        roots=rng.sample(nodes,rng.randrange(1,len(nodes)+1)); expected=set(roots); todo=list(roots)
        while todo:
            for dep in graph[todo.pop()]:
                if dep not in expected: expected.add(dep); todo.append(dep)
        assert R.dependency_closure(graph,roots)==sorted(expected)
        n+=1
    return 4+n

def check_generation_aggregation():
    cases=0
    for first in (None,0,1,2):
        for missing_bits in range(8):
            attempts=[{"oracle_accepted":i==first,"wall_ms":10+i,
                       "generation_ms":None if missing_bits & (1<<i) else i+1} for i in range(3)]
            got=R.aggregate_attempt_times(attempts)
            included=list(range(first+1)) if first is not None else []
            penalty=[] if first==0 else [0] if first is not None else [0,1,2]
            for key, indices in (("minimum_time_to_accepted_generation_ms", included),
                                 ("failed_first_attempt_penalty_generation_ms", penalty)):
                expected=None if (key.startswith("minimum") and first is None) or any(missing_bits & (1<<i) for i in indices) else sum(i+1 for i in indices)
                assert got[key]==expected
            assert got["generation_missing_attempt_count"]==bin(missing_bits).count("1")
            assert got["penalty_generation_missing_count"]==sum(bool(missing_bits & (1<<i)) for i in penalty)
            assert got["time_to_accept_generation_missing_count"]==(None if first is None else sum(bool(missing_bits & (1<<i)) for i in included))
            assert got["minimum_time_to_accepted_wall_ms"]==(None if first is None else sum(10+i for i in included))
            assert got["failed_first_attempt_penalty_wall_ms"]==sum(10+i for i in penalty)
            cases+=1
    return cases


def main():
    parser=argparse.ArgumentParser(description="Immutable prevalidation by default; --freeze explicitly writes manifest")
    mode=parser.add_mutually_exclusive_group()
    mode.add_argument("--check",action="store_true")
    mode.add_argument("--freeze",action="store_true")
    args=parser.parse_args()
    frozen=None if args.freeze else json.loads(MANIFEST.read_text(encoding="utf-8"))
    data=json.loads(TASKS.read_text(encoding="utf-8")); assert len(data["tasks"])==10
    ids=[t["id"] for t in data["tasks"]]; assert len(set(ids))==10
    rng=random.Random(20261111)
    counts={
        "01_toposort":check_toposort(rng),
        "02_json_pointer_get":check_json_pointer(),
        "03_safe_join":check_safe_join(),
        "04_retry_delays":check_retry(rng),
        "05_pack_batches":check_pack_batches(rng),
        "06_lru_trace":check_lru(),
        "07_redact_secrets":check_redact(),
        "08_select_nonoverlapping":check_intervals(rng),
        "09_aggregate_logs":check_logs(),
        "10_dependency_closure":check_closure(rng),
    }
    task_index={t["id"]:t for t in data["tasks"]}
    task_manifest=[]
    for task_id in ids:
        t=task_index[task_id]
        entry={"id":task_id,"kind":t["kind"],"function":t["function"],
               "spec_sha256":digest_text(t["spec"]),"prompt_sha256":digest_text(t["prompt"]),
               "oracle_checks":counts[task_id]}
        for field in ("tools","environment","expected_call_names"):
            if field in t: entry[field+"_sha256"]=digest_text(json.dumps(t[field],sort_keys=True,ensure_ascii=False,separators=(",",":")))
        task_manifest.append(entry)
    retry_protocol={"attempts_per_task":3,"seeds":[42,43,44],"same_prompt_bytes_every_attempt":True,
                    "prompt_tuning_or_human_feedback_between_attempts":False,"run_all_three_even_after_early_acceptance":True,
                    "fresh_tool_environment_each_attempt":True,
                    "pass_at_1":"attempt 1 independently accepted",
                    "pass_at_3":"at least one of attempts 1-3 independently accepted",
                    "attempts_to_first_accept":"lowest successful attempt index; null if none within 3 (right-censored)",
                    "minimum_time_to_accepted_wall_ms":"sum of wall_ms from attempt 1 through first accepted attempt; null if no acceptance",
                    "minimum_time_to_accepted_generation_ms":"sum of generation_ms from attempt 1 through first accepted attempt; null if no acceptance",
                    "failed_first_attempt_penalty":"if attempt 1 fails and a later attempt passes, penalty is attempt-1 wall_ms/generation_ms; if none pass, penalty is the sum of all failed attempt wall_ms/generation_ms; zero if attempt 1 passes",
                    "inter_attempt_delay":"zero intentional delay; only unavoidable API/runner overhead",
                    "primary_timing_metric":"wall_ms",
                    "generation_aggregation":"sum included generation_ms only if all are non-null; otherwise null; empty penalty sum is zero",
                    "generation_missing_counts":"generation_missing_attempt_count counts all 3; time_to_accept_generation_missing_count counts through first accept or null if none; penalty_generation_missing_count counts the penalty subset",
                    "generation_time":"first non-empty visible content token to final visible content token; null when no visible content",
                    "wall_time":"client request start through complete response including TTFT and generation"}
    attempt_record_schema={"task_id":"string","candidate_id":"string","attempt_index":"1|2|3",
                           "seed":"42|43|44","prompt_sha256":"hex","start_utc":"ISO-8601",
                           "end_utc":"ISO-8601","wall_ms":"number","generation_ms":"number|null",
                           "ttft_ms":"number|null","output_sha256":"hex","oracle_accepted":"boolean",
                           "failure_class":"string|null","oracle_id":"string","exact_input_sha256":"hex|null"}
    summary_record_schema={"task_id":"string","candidate_id":"string","attempts":"array of exactly 3 attempt records",
                           "pass_at_1":"boolean","pass_at_3":"boolean","attempts_to_first_accept":"1|2|3|null",
                           "minimum_time_to_accepted_wall_ms":"number|null","minimum_time_to_accepted_generation_ms":"number|null",
                           "failed_first_attempt_penalty_wall_ms":"number","failed_first_attempt_penalty_generation_ms":"number|null",
                           "generation_missing_attempt_count":"integer 0..3",
                           "time_to_accept_generation_missing_count":"integer 0..3|null",
                           "penalty_generation_missing_count":"integer 0..3",
                           "all_attempts_failed":"boolean"}
    manifest={"suite":data["suite"],"version":data["version"],"status":"ORACLE_PREVALIDATED",
              "revision":data["revision"],
              "historical_v2_manifest_sha256":"f705357888003fe37a1d6794857ccae9c55ad57efaab48b6344c9a018104c5f6",
              "external_p4_tasks":["merge_intervals","parse_records"],
              "frozen_utc":datetime.now(timezone.utc).isoformat() if args.freeze else frozen["frozen_utc"],"seed":20261111,
              "readme_file_sha256":digest_bytes((ROOT/"README.md").read_bytes()),
              "tasks_file_sha256":digest_bytes(TASKS.read_bytes()),
              "reference_file_sha256":digest_bytes((ROOT/"reference.py").read_bytes()),
              "validator_file_sha256":digest_bytes(Path(__file__).read_bytes()),
              "retry_protocol":retry_protocol,"attempt_record_schema":attempt_record_schema,
              "task_candidate_summary_schema":summary_record_schema,"tasks":task_manifest,
              "validation_summary":{"toposort_seeded_dags":100,"retry_random_cases":200,
                                    "batch_random_cases":100,"interval_random_vs_bruteforce":250,
                                    "dependency_random_graphs":100,
                                    "generation_aggregation_cases":check_generation_aggregation()}}
    if args.freeze:
        MANIFEST.write_text(json.dumps(manifest,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")
    elif manifest != frozen:
        raise AssertionError("frozen manifest mismatch; review changes and explicitly --freeze a new revision")
    print(json.dumps({"status":"ORACLE_PREVALIDATED","mode":"freeze" if args.freeze else "check","task_count":len(ids),"counts":counts,
                      "manifest_sha256":digest_bytes(MANIFEST.read_bytes())},indent=2))

if __name__ == "__main__": main()
