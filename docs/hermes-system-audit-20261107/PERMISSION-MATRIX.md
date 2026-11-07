# Permission Matrix

Audit timestamp: 2026-11-07T14:35:24-05:00. This is a read-only configuration/evidence audit. `Configured` means a file or process declares the capability; `Verified` means a safe runtime observation established it. Secrets were not printed.

| Worker | Shell | Sandbox | Filesystem RW | Sudo | SSH | GitHub RW | Network | MCP | Child agents | Approval | Status |
|---|---|---|---|---|---|---|---|---|---|---|---|
| hermes-supervisor | Configured local terminal; effective current session verified | Not explicitly declared; effective isolation unverified | Local cwd `/home/joe/repos/sabrtrader`; broad user filesystem capability configured, effective scope untested | OS user is in sudo group; no sudo test | Config/references exist; effective remote access unverified | GitHub tooling/config present; RW not verified | Cloud HTTPS plus loopback services observed | Hindsight eng loopback configured; no content/tool mutation | Delegation configured; child policy max 1 | Smart; write approval true | Active supervisor |
| qwen-worker | Configured local terminal/file toolsets | Not explicitly declared; unverified | Local user workspace capability configured; DR100 contract says infer/check only for model; effective FS write not tested in this audit | Inherits OS user; not tested | Unverified | Unverified | Loopback 8082 configured; no endpoint at capture | Hindsight eng loopback configured | Delegation toolset configured in profile; effective spawn not tested | Smart; write approval true | Configured, endpoint unavailable |
| qwen-worker-2 | Configured local terminal/file toolsets | Unverified | Configured similarly to qwen-worker; effective RW untested | Unverified | Unverified | Unverified | Loopback 8082 configured; unavailable | Hindsight configured | Delegation configured; profile is not in dispatch allowlist | Smart; write approval true | Historical/retired; dispatch disabled |
| qwen-windows-worker | Local terminal plus CUA foreground/background toolsets | Unverified | Workspace scope unverified; profile has Windows capability manifest | Unverified | Windows/SSH capability referenced, effective access not tested | Unverified | Loopback 8083 configured; unavailable | Hindsight configured | Delegation configured; Kanban dispatch disabled | Smart; write approval true | Configured but Windows admission blocked/unverified |
| codex-worker | Cloud Codex app-server tool profile | Provider sandbox semantics not locally verified | Cloud/Code mode boundary unverified | No local sudo evidence | Cloud environment remote capability configured by Codex; not tested | GitHub access depends on authenticated Codex environment; unverified | HTTPS to OpenAI/Codex | Codex app MCP; exact grants unverified | Delegation toolset configured | Configured in profile; exact mode not safely extracted | Inactive |
| reviewer-economy | Local terminal configured; provider-specific review backend also present | Unverified | cwd `/home/joe/.hermes/dr100-learning` configured | Unverified | Unverified | Unverified | Cloud provider route configured; no request made | Hindsight MCP configured | Not proven | Smart/write approval configured partially | Inactive; review dispatch false |
| senior-reviewer | Local terminal configured; Claude direct SDK provider | Unverified | cwd `/home/joe/.hermes/dr100-learning` configured | Unverified | Unverified | Unverified | `process://` Claude provider plus network inside client; not tested | Hindsight MCP configured | Not proven | Smart/write approval configured partially | Inactive; review dispatch false |
| gyro-coder-supervisor | Local terminal; openai-compatible local model | Unverified | cwd `/home/joe/repos/sabrtrader` | Inherits OS user; not tested | Unverified | Unverified | Loopback 8082; unavailable at capture | Hindsight eng configured | Delegation configured | Smart/write approval true | Inactive |
| gyro-coder-gpu1 | Local model client | Unverified | Unverified | Unverified | Unverified | Unverified | Loopback 8083; unavailable | Hindsight configured | Unverified | **Configured `off`**; risk requiring approval | Inactive |
| gyro-worker-1/2 | Local model clients | Unverified | Unverified | Unverified | Unverified | Unverified | Loopback 8082; unavailable | Hindsight configured | Unverified | Not fully extracted | Historical/inactive |

## Effective permission limits

The audit did not execute destructive tests, sudo, SSH, GitHub writes, process termination, file deletion, child-agent spawning, or external MCP mutations. Therefore those capabilities remain **UNAVAILABLE/UNVERIFIED** even where config or group membership suggests they may be possible.

The current OS identity is `joe`, a member of `sudo` and `lxd`, but membership is not equivalent to tested effective privilege. Local systemd services run as user `joe`; the Hermes gateway and active CodeBreaker llama-server are not root processes.

## Material permission drift

- `gyro-coder-gpu1` has an apparent `approvals.mode: off`, unlike the intended smart-approval baseline.
- Several local profiles expose delegation toolsets, although the intended production policy is one local worker and Kanban is suspended.
- `qwen-windows-worker` has CUA tools configured but is not currently admitted to Kanban and has no verified Windows execution in this audit.
- Hindsight MCP is configured broadly across profiles; per-profile effective tool grants were not invoked.
