# llama-swap "What's really running": BASALT telemetry adapter

This adapter lets the existing read-only monitoring sidecar (`llama-swap-reality.py`) recognise a
BASALT model server alongside llama.cpp servers. The sidecar keeps serving the same page and
endpoints; nothing was replaced.

## What changed

- **Process discovery.** A model server is either a `llama-server` process or a BASALT serve process
  (`python3 -m serve.server` with an engine binary whose path ends in `bin/basalt`). Unrelated CUDA
  processes are not classified as model servers.
- **Model identity.** The model ID and backend port come from llama-swap's own `/running` list,
  matched on the proxy port. `--alias` is not used for BASALT, because its alias lives in the config file.
- **GPU attribution.** Each GPU compute process is counted once, under the model server that is it or
  one of its ancestors (BASALT's engine runs as a child of the serve process). Compute processes with
  no such ancestor are ignored.
- **Live tokens/second.** BASALT's `/slots` rows carry `state` (`prefill`, `decoding`, `idle`) and a
  per-request `generated` counter. The sampler counts increments of `generated` while a slot is
  `decoding`. A counter that goes backwards means a new request started. The llama.cpp path is unchanged.
- **Last completed request and prompt throughput.** `GET /v1/status` returns `last_timings` for the last
  completed request, in llama.cpp field names. The sidecar polls it at most every 5 seconds for a BASALT
  port and exposes it as `stats[alias].last` in `/_reality/tps`.
- **Missing versus zero.** A model with no samples in the window has `stats` absent or `now: null`.
  A model that is running and idle reports `now: 0.0`.

## Fields used (BASALT, v0.4.1)

| Source | Field | Use |
|---|---|---|
| `GET /health` | `loaded`, `loading`, `percent` | loading / loaded state |
| `GET /slots` | `state`, `generated`, `is_processing` | live generation |
| `GET /v1/status` | `last_timings.predicted_per_second` | last completed decode tok/s |
| `GET /v1/status` | `last_timings.prompt_per_second` | prompt-processing tok/s |
| `GET /v1/status` | `last_timings.predicted_n`, `prompt_n`, `at` | last request size and time |
| llama-swap `GET /running` | `model`, `proxy` port, `state` | model ID and backend port |

## Read-only guarantees

Only `GET` requests are made to the BASALT backend (`/health`, `/slots`, `/v1/status`). Those endpoints do
not load or swap models. llama-swap's `/running` is read the same way. Inference requests are never made by
the sidecar.

## Known differences

- The sidecar's average tok/s counts generated tokens over sampled active time, which is lower than the
  engine's own decode figure (for one 220-token request: monitor average 27.0, engine 40.9). The engine
  figure is shown separately as the "last completed" value.
- BASALT's `/metrics` and `/api/logs` are not used. The `Activity` stream was not inspected for BASALT.

## Validation

- Unit tests: `test_reality_basalt.py` (12 tests, no network or GPU).
- Live check on 5090FE: the loaded `basalt-deepseek-v41` showed as `basalt`, owner `llama-swap`, state
  `loaded`, with per-GPU VRAM summing to the `nvidia-smi` totals within about 90 MiB. During a 220-token
  generation the live rate rose to about 39 tok/s (peak 42.4) and returned to 0.0 afterwards. The last
  completed value stayed visible. The CPU model `hindsight-extract` kept appearing as a llama.cpp server.
