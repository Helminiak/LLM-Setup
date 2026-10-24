#!/usr/bin/env python3
"""DR100 AI monitor v0.2 in-place patch: five stable status lines + durable clue log.

Updates only ~/.local/share/dr100-terminal-monitor/dr100_inference.py.
No model calls, service restarts, native Kanban modifications, or GUI changes.
"""
from __future__ import annotations
import ast
from datetime import datetime, timezone
import os
from pathlib import Path
import shutil
import sys

p = Path.home() / ".local/share/dr100-terminal-monitor/dr100_inference.py"
if not p.is_file() or p.is_symlink():
    raise SystemExit("STOP: installed regular monitor source missing or symlink; no changes")
original = p.read_text(encoding="utf-8")
if "def diagnostic_status(s):" in original and "diagnostic-events.log" in original:
    print("DR100 AI v0.2 persistent diagnostics already installed.")
    sys.exit(0)

replacements = [
    ("def display_lines(s, history, width):",
     "def display_lines(s, history, width, recent_clues=()):"),
    ('    lines += ["", "DIAGNOSTIC CLUES (hypotheses; not root-cause claims)"]\n'
     '    lines += ["  "+v for v in derived_clues(s)] or ["  No unusual thresholds observed"]',
     '    lines += ["", "DIAGNOSTIC STATUS (five lines always visible; not root-cause proof)"]\n'
     '    lines += ["  "+v for v in diagnostic_status(s)]\n'
     '    lines += ["", "RECENT FLAGS (last 5 transitions; retained until exit)"]\n'
     '    lines += ["  "+v for v in list(recent_clues)[-5:]] if recent_clues else ["  No flags yet in this session"]'),
    ("def curses_main(stdscr, collector, args, writer):",
     "def curses_main(stdscr, collector, args, writer, event_log):"),
    ("    history=collections.deque(maxlen=300)\n    nexttick=0.0",
     "    history=collections.deque(maxlen=300)\n"
     "    recent_clues=collections.deque(maxlen=5)\n"
     "    active_flags=set()\n    nexttick=0.0"),
    ("            history.append(s)\n            if writer: write_rows(writer,s)",
     "            history.append(s)\n"
     "            flags=set(derived_clues(s))\n"
     "            for clue in sorted(flags-active_flags):\n"
     "                line=f\"{s['utc'][11:19]} UTC {clue}\"\n"
     "                recent_clues.append(line)\n"
     "                event_log.write(s['utc']+' '+clue+'\\n')\n"
     "                event_log.flush()\n"
     "            active_flags=flags\n"
     "            if writer: write_rows(writer,s)"),
    ("display_lines(s,history,w)[:max(0,h-1)]",
     "display_lines(s,history,w,recent_clues)[:max(0,h-1)]"),
    ("                curses.wrapper(curses_main,collector,args,writer)",
     '                with (target/"diagnostic-events.log").open("a",encoding="utf-8") as event_log:\n'
     "                    curses.wrapper(curses_main,collector,args,writer,event_log)"),
]
new = original
for old, replacement in replacements:
    if new.count(old) != 1:
        raise SystemExit("STOP: incompatible installed monitor version; expected exact patch anchor: " + old[:72])
    new = new.replace(old, replacement, 1)
new = new.replace('monitor v0.1', 'monitor v0.2', 1)
# The user's v0.1 may have already received the empty-decode-history bugfix.
new = new.replace('    maxv=max(1.0, *[v for v in vals if v is not None])',
                  '    maxv=max([1.0]+[v for v in vals if v is not None])', 1)
addition = '''
def diagnostic_status(s):
    """Five stable observations, independent of the transient warning thresholds."""
    gs = s.get("gpus") or []
    util = " / ".join(f"GPU{g.get('gpu')} {fmt(g.get('gpu_util'),'%')}" for g in gs) or "GPU N/A"
    links = " / ".join(
        f"G{g.get('gpu')} Gen{g.get('pcie_gen','?')}x{g.get('pcie_width','?')}"
        f" RX/TX {fmt(mib(g.get('pcie_rx_kib_s')),'')}/{fmt(mib(g.get('pcie_tx_kib_s')),'')}"
        for g in gs
    ) or "PCIe unavailable"
    shard = f"shard {fmt(s.get('shard_pct'),'%')} cached" if s.get("shard_pct") is not None else "shard cache N/A"
    return [
        f"INFERENCE: decode {fmt(s.get('decode_tps'),' tok/s')} ({s.get('throughput_source') or 'unavailable'}); slots {s.get('slot_busy') if s.get('slot_busy') is not None else 'N/A'}; metrics {'on' if s.get('metrics_available') else 'off'}",
        f"COMPUTE: {util}; llama CPU {fmt(s.get('server_cpu_cores'),' cores')} (not a bottleneck proof)",
        f"MEMORY: {shard}; RAM available {fmt(s.get('mem_available_gib'),' GiB')}; swap used {fmt(s.get('swap_used_gib'),' GiB')}",
        f"PAGING/IO: swap in/out {fmt(s.get('swap_in_mib_s'),' MiB/s')}/{fmt(s.get('swap_out_mib_s'),' MiB/s')}; server disk read {fmt(s.get('server_disk_read_mib_s'),' MiB/s')}",
        f"TRANSFER: {links} (aggregate PCIe, not GPU-to-GPU copy rate)",
    ]


'''
anchor="def display_lines(s, history, width, recent_clues=()):"
if new.count(anchor)!=1:
    raise SystemExit("STOP: unexpected display function after patch")
new=new.replace(anchor,addition+anchor,1)
ast.parse(new,filename=str(p))
timestamp=datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
backup=p.with_name(p.name+".pre-v02."+timestamp+".bak")
shutil.copy2(p,backup)
tmp=p.with_name(p.name+".v02.tmp")
try:
    with tmp.open("x",encoding="utf-8") as f:
        f.write(new)
    os.chmod(tmp,p.stat().st_mode & 0o777)
    os.replace(tmp,p)
except BaseException:
    tmp.unlink(missing_ok=True)
    raise
print("PATCHED: "+str(p))
print("BACKUP: "+str(backup))
print("Five diagnostic lines will remain visible; last five flag transitions remain on-screen.")
print("All flag transitions saved to diagnostic-events.log in the monitor's telemetry session directory.")
print("Quit/reopen dr100-monitor-ai to activate. No llama-server restart needed.")
