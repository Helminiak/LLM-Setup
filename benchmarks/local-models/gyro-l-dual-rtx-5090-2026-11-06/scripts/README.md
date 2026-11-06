# Reproduction notes

These scripts reproduce the measurement methods against an already running OpenAI-compatible llama.cpp server. They do not start, stop, or reconfigure a service. Python 3 standard library is sufficient. Install NVIDIA drivers/tools for `gpu_sample.py`.

1. Prepare a directory of non-sensitive `prompt_*.txt` files representing the workload you intend to measure. The original prompt source corpus is intentionally omitted from this public archive.
2. Start `python3 scripts/gpu_sample.py --out results/gpu_campaign.csv --hz 1` and `python3 scripts/slot_sample.py --out results/slot_campaign.csv`.
3. Run `python3 scripts/smoke_load.py --prompt-dir PROMPTS --lanes 1 --duration 60 --out results/A_single60.json --label A_single60` for a single lane. Repeat with `--lanes 2 --duration 120` and `--lanes 2 --duration 300` for dual and sustained phases. The load generator writes raw per-request records including timing metadata to its output; keep those local and review before sharing.
4. `python3 scripts/analyze.py --gpu-csv results/gpu_campaign.csv --load-json results/A_single60.json` computes GPU telemetry summaries. Use `analyze_windows.py` as a reference for the window-level aggregate calculations; the archived aggregate outputs are supplied under `../results/`.

The archived raw telemetry CSVs use elapsed seconds instead of wall-clock timestamps; slot task IDs were removed. `window_report.json` omits absolute start/end timestamps. Exact aggregate measurements are retained in the phase `.stats.json` files.
