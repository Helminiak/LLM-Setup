import sys, yaml

src, out = sys.argv[1], sys.argv[2]

block = """  # BASALT DeepSeek-V4.1-Flash UD-IQ1_M - cmd-managed under the BASALT GPU lease wrapper (2026-11-18)
  "basalt-deepseek-v41":
    name: "DeepSeek-V4.1-Flash UD-IQ1_M (BASALT)"
    description: "BASALT v0.4.1 dual RTX 5090, ctx 131072, parallel 1, kv fp8; launched via lease_guard_v2 (--gpus 0,1)"
    cmd: "/home/joe/.local/state/inference-research/p7-19-2026-11-11/dashboard/bin/lease_guard_v2.sh --gpus 0,1 /home/joe/models/basalt/engine/basalt-v0.4.1-linux-x64/bin/basalt serve --config /home/joe/models/basalt/config/basalt_config.json --port ${PORT} --host 127.0.0.1"
    proxy: http://127.0.0.1:${PORT}
    checkEndpoint: /health
    ttl: 0
    unloadTimeout: 15
"""

with open(src, encoding="utf-8") as f:
    lines = f.read().split("\n")

i = lines.index("models:") + 1
lines[i:i] = block.split("\n")[:-1] + [""]

with open(out, "w", encoding="utf-8") as f:
    f.write("\n".join(lines))

old = yaml.safe_load(open(src, encoding="utf-8"))
new = yaml.safe_load(open(out, encoding="utf-8"))
missing = set(old["models"]) - set(new["models"])
assert not missing, "existing model lost: %s" % missing
added = sorted(set(new["models"]) - set(old["models"]))
print("models old=%d new=%d added=%s" % (len(old["models"]), len(new["models"]), added))
