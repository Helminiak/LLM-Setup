# Infrastructure recall — previous Claude sessions vs current Mini PC Open WebUI

Date: 2026-11-10 (America/New_York). Host: 5090FE. Author: Hermes supervisor (P3 support).
Mode: read-only. No Llamactl, model, port, service or credential changes were made.
Every health/availability claim below was re-measured in this session; the old Claude
transcripts were used only to locate configuration, never as evidence of current health.

## 1. Sources located (not re-worked)

| Source | Content |
| --- | --- |
| `~/.claude/projects/-home-joe/d36db472-3b27-481a-a9e4-37cbff576f1b.jsonl`, `44b12084-d352-4375-9051-df5a20984961.jsonl` | "Llamactl Control Center launcher repair" session |
| `~/.claude/projects/-home-joe/b1581ed5-4767-4fd0-aa6a-0a2dfbd429a7.jsonl`, `0d088776-…jsonl`, `7270f4fe-…jsonl` | Mini PC Open WebUI / supervisor repair sessions |
| `~/.claude/projects/-home-joe/memory/mini-supervisor-t16-repair.md` | Handoff note: native (Ubuntu↔Mini) link drops ~10 s when the Mini supervisor restarts |
| `~/.local/state/llamactl-staging-20261109/` | `run-llamactl.sh`, `llamactl.yaml`, `llamactl.service`, launcher `.desktop` + `.desktop.bak`, `checksums.txt`, `llamactl.log`, `management.key` (values not reproduced here) |

Recovered Llamactl launch shape (from staging files, unchanged on disk):
dashboard bound to `127.0.0.1:19090`, `--no-browser`, `--no-tls`, `--auth-mode api-key`,
`--models-dir /home/joe/.cache/huggingface/hub`, `management_api_key` supplied by file,
`instances: []`. This matches the P0–P2 findings and needs no change.

## 2. 5090FE inference surface (re-verified live)

| Port | Unit / process | Verified state this session |
| --- | --- | --- |
| 8082 | `local-qwen.service` → `llama-server` (llama-gyro build) | `/health` 200. argv: `-m /home/joe/models/bakeoff/flash-iq3/Qwen3.8-Flash-Next-GSQ-RCO-IQ3_XXS-00001-of-00002.gguf --alias Qwen3.8-Flash-Next-GSQ-RCO-IQ3_XXS --n-gpu-layers 999 --split-mode layer --tensor-split 0.975,1.025 --flash-attn on --ngram-on-disk --ctx-size 128000 --cache-type-k q8_0 --cache-type-v q8_0 --parallel 1 --jinja --host 127.0.0.1 --port 8082`. No `--api-key` (loopback only). `/v1/models` → `Qwen3.8-Flash-Next-GSQ-RCO-IQ3_XXS`, `local-llm`. Chat completion 200, `finish_reason=stop` (scratch `infra-recall/direct-completion.json`) |
| 8091 | `hindsight-extract-llm.service` → `llama-server` | `/health` 200; model `/home/joe/models/Qwen3-4B-Q4_K_M.gguf`, alias `hindsight-extract`, `--device none -ngl 0 -np 2 -c 40960 --reasoning off --no-webui`; `/v1/models` → `hindsight-extract` |
| 8083 | `qwen-tailnet-fwd.service` (socat, tailnet-only) | `0.0.0.0:8083 → 127.0.0.1:8082`. 200 from 5090FE **and from the Mini PC**; chat completion over tailnet 200 (`fwd-completion.json`). No key required |
| 8093 | `stt-whisper.service` — "Faster-Whisper medium.en CPU INT8 (Tailscale-only)", active since 19:03 | `/v1/models` 200 with `whisper_key`, 401 without (probed from the Mini) |
| 1235 | `dr100-model.service` (profile `dr100-gsq-coder-mtp-250k`, 262 144 ctx, dual-5090, MTP, reasoning xhigh) | Unit installed but **not listening** — inactive, as previously recorded |
| 19090 | `llamactl.service` | active/enabled; `/` 200; `/api/v1/models` still 2 rows (P2 explains: cache registry vs local inventory) |

Independent management confirmed: each inference lane is its own systemd user unit with a
dedicated llama-server binary build, model path, port and context. Llamactl does not own
them and was not used to start them.

## 3. Mini PC supervisor + Open WebUI (re-verified live via HERDR)

Config recovered from `C:\AI\mini-supervisor` (values masked, files not modified):

- `watchdog.py` (edited 11-10 22:02) supervises `llama` 8081, `supervisor` 8082, `webui` 8080 and
  applies the Open WebUI environment: `OPENAI_API_BASE_URLS='http://127.0.0.1:8082/v1;http://100.80.218.34:8083/v1'`,
  `OPENAI_API_KEYS=<supervisor api_key>;none`, `OPENAI_API_BASE_URL=http://127.0.0.1:8082/v1`,
  `DEFAULT_MODELS='mini-supervisor'`, `ENABLE_OLLAMA_API=False`, `WEBUI_AUTH=True`,
  `ENABLE_SIGNUP=False`, `HF_HUB_OFFLINE=1`, `RAG_EMBEDDING_ENGINE='openai'`,
  `RAG_OPENAI_API_BASE_URL=http://127.0.0.1:8082/v1`, local whisper fallback (`base.en`) plus an
  STT base URL pointing at `http://100.80.218.34:8093/v1`.
- Open WebUI runs natively: `.webui\Scripts\open-webui.exe serve --host 0.0.0.0 --port 8080`
  (pid 29616, started 11-10 22:02, listening `0.0.0.0:8080`).
- `supervisor.py` (11-10 22:05; backup `supervisor.py.bak-20261110-191413-chatfix` from 17:38):
  `/v1/models` = `mini-supervisor` + `remote_workers.worker_models()`; `/v1/chat/completions`
  routes `worker/*` to `remote_workers.worker_chat`, everything else to llama 8081.
- Live: `/health` 200 `{"name":"mini-supervisor","status":"ready"}`; `/v1/models` 200 with 11 ids
  (`mini-supervisor`, `worker/codex-worker`, `worker/gyro-coder-gpu1`, `worker/gyro-worker-1`,
  `worker/gyro-worker-2`, `worker/qwen-worker`, `worker/reviewer-economy`, `worker/senior-reviewer`,
  `worker/luna-low`, …); chat with `model=mini-supervisor` → 200 in 383 ms; direct llama 8081 chat →
  200 in 880 ms; unauthenticated calls → 401 (by design, bearer key required).
- Mini → 5090FE routes verified from the Mini itself: `100.80.218.34:8083/v1/models` 200;
  `100.80.218.34:8093/v1/models` 200 with `whisper_key`, 401 without.

## 4. Actual Open WebUI chat failure (from `data/logs/webui.log`, live tail)

```
21:50:45 WARNING open_webui.events: Upstream openai-compatible request failed: HTTP 400
         url=http://127.0.0.1:8082/v1 model=worker/luna-low
21:50:45 ERROR   open_webui.main:process_chat:1671 - Error processing chat payload:
         Worker requires a final text user message
21:50:45 POST /api/chat/completions 400   (client 192.168.1.111)
21:52:29 POST /api/chat/completions 200   (chat succeeded)
21:57:54 GET  /api/models 401             (unauthenticated probe from 100.80.218.34)
21:58:34 POST /api/chat/completions 401 ×2 (unauthenticated, 127.0.0.1)
```

Two distinct causes, both verified:

1. **Model selection.** `worker/*` ids are HERDR dispatch pseudo-models, not chat models.
   `C:\AI\mini-supervisor\remote_workers.py:177`:
   `if not messages or messages[-1].get('role')!='user' or not isinstance(messages[-1].get('content'),str): raise HTTPException(400,'Worker requires a final text user message')`
   Open WebUI frequently sends multipart (list) content or a trailing non-user message
   (regeneration / continuation), so any `worker/*` selection returns 400. `worker_chat` also
   forwards only `messages[-1]['content']` — no conversation history.
   Chat through `mini-supervisor` or the tailnet Qwen route works today.
2. **Session.** The 401 entries are unsigned-in Open WebUI requests. Admin credentials exist in
   `data/secrets.json` (`webui_email`, `webui_password`); they were not used or printed, matching
   the owner's standing restriction on signing in from tooling.

## 5. Secondary defect: embeddings

`POST /v1/embeddings` → **501 "This server does not support embeddings"** on both 5090FE
llama-servers (8082, 8091) and **404** on the Mini supervisor, while Open WebUI is configured with
`RAG_EMBEDDING_ENGINE='openai'` + `RAG_OPENAI_API_BASE_URL=http://127.0.0.1:8082/v1`. Any chat that
attaches knowledge/documents will fail even though plain chat works.

## 6. Reusable as-is (nothing to build)

Tailnet forwarder 8083 (keyless, matches the `;none` slot in `OPENAI_API_KEYS`), supervisor bearer
auth, `whisper_key` path to 5090FE STT, Tailscale HTTPS certificate for `mini-pc.taila85ffa.ts.net`
(443 responds; LE cert renewed 11-09), and the LAN access path already exercised by `192.168.1.111`.

## 7. Open decisions (owner / operator — not executed here)

1. Immediate chat: sign in to Open WebUI and select `mini-supervisor` (or the tailnet Qwen model);
   do not select `worker/*` for chat.
2. If `worker/*` must accept Open WebUI payloads: normalize the payload at `remote_workers.py:177`
   (accept list-type content, fall back to the last user message) — requires a Mini supervisor
   restart, which drops the native Ubuntu↔Mini link ~10 s. Owner decision.
3. Embeddings: revert `RAG_EMBEDDING_ENGINE` to the shipped local engine, or authorize a dedicated
   embedding server (new service → outside the current no-new-services constraint).
