# Engineering Acceptance Report — worker-2 (gyro-worker-2)

Session UTC start: 2026-11-14T21:39:12Z (baseline recorded before any changes)
Workspace: /home/joe/.local/state/codex/dual-worker-20261114/worker-2 (empty at baseline)
Host: 5090FE | Python 3.14.9 | git 2.53.0

## Objective
Independent disposable acceptance: Git repo, half-open interval merger module +
unittest suite, file-tool write/read/patch, unittest evidence capture, tiny C
artifact compiled, REA inspect_with_objdump MCP call, Git metadata with real
exit codes, sha256 hashes.

## Tool receipts (actual commands + exit codes)
| Step | Command / Tool | Exit | Result |
|---|---|---|---|
| Baseline | hostname/pwd/python3 --version/git --version/date -u | 0 | as above |
| Repo init | git init -b main | 0 | initialized at workspace root |
| Write | write_file intervals.py, test_intervals.py | ok | lint clean |
| Read | read_file intervals.py | ok | 40 lines |
| Patch | patch test_intervals.py (+test_duplicates_collapse) | ok | 9 tests total |
| Tests | python3 -m unittest -v | 0 | Ran 9 tests, OK (stdout empty by design; verbose output on stderr — evidence/unittest.stderr) |
| C compile | gcc -c probe.c -o probe.o | 0 | probe.o 1232 bytes |
| Git meta (pre-commit) | git status --porcelain | 0 | 6 untracked entries (evidence/git-metadata-precommit.txt) |
| Git meta (pre-commit) | git rev-parse --show-toplevel | 0 | workspace path |
| Git meta (unborn HEAD) | git log | 128 | "fatal: your current branch 'main' does not have any commits yet" — expected unborn-HEAD handling |
| Commit | git commit | 0 | 2101f8d |
| Git meta (post-commit) | git status --porcelain / git log --oneline | 0 / 0 | clean except untracked __pycache__/; log = 2101f8d |

Evidence files: evidence/unittest.stdout, evidence/unittest.stderr,
evidence/unittest.exit (=0), evidence/gcc.stdout, evidence/gcc.stderr,
evidence/gcc.exit (=0), evidence/git-metadata-precommit.txt,
evidence/git-metadata-postcommit.txt, evidence/sha256sums.txt.

## Tests
9 unittest cases, all passing (exit 0): empty input, empty-interval drop,
touching merge ([1,3)+[3,5)→[1,5)), nested collapse, disjoint separation,
negative intervals, unsorted overlap chain, duplicate collapse, bad-pair
ValueError. Standard library only (unittest, typing).

## REA MCP result (mcp__rea__inspect_with_objdump)
Two calls on absolute path
/home/joe/.local/state/codex/dual-worker-20261114/worker-2/probe.o:
1. operation=disassemble, symbol=probe_add, detail=summary
   - exit_code 0, completion_status complete, output_truncated false
   - Disassembly: endbr64; push %rbp; mov args to -0x4/-0x8(%rbp); mov -0x4..%edx;
     mov -0x8..%eax; add %edx,%eax; pop %rbp; ret — correct int add body
   - evidence_id ev_6ec33d4d233c656457b2c0e1f583555c3dc242de0a594704b75ccbb89e9c3d9a
   - parent_evidence_id ev_dd01deac8586fbe31d3739f55b50b0a9edbd98c6e4ab99f409454b09e1f2ae87
   - artifact_sha256_after c94ed0f2b09e0167b3144775dce3c7c8e210c70f9c16db56b04b4e8d7f97450e,
     artifact_changed=false
2. operation=symbols, detail=summary
   - exit_code 0; SYMBOL TABLE shows g F .text probe_add (0x18 bytes), file format elf64-x86-64
   - evidence_id ev_1382eec0f06ad5843c89284c5da74ab8fab2653cef46f68684e8c27960bb4a8c
REA-reported probe.o sha256 matches local sha256sum exactly.

## SHA-256 (sha256sum, evidence/sha256sums.txt)
- intervals.py  a8ef2b86903ccd13a93f3eeb5c87f04ec4c5a039dd68f64a2bd592324526578c
- test_intervals.py  d15d25492597fd6bdfbcf941ff70bcfac786bca8ba311260739b9db78a7d494b
- probe.c  869a0f919e1cdd22e3798c918f6ae955bc782cd5b690299942d2f07e0afcb24d
- probe.o  c94ed0f2b09e0167b3144775dce3c7c8e210c70f9c16db56b04b4e8d7f97450e
- evidence/unittest.stdout  e3b0c442...b855 (empty stream; unittest -v writes to stderr)
- evidence/unittest.stderr  95371169b29af676972d2a291cc5825cf0edbd0d85fd8594dc1249ffacfcbe34

## Failures / blockers
None. 0 equivalent-failure retries used. No installs, no config/model/service
changes, no production touches.
