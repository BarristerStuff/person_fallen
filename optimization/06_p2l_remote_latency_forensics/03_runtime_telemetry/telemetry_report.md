# P2L runtime telemetry report

## Collection boundary

The P2L runner captured direct `/api/ps` snapshots before, at the midpoint where applicable, and after each formal probe. It deliberately did not call `/api/ps` between every inference request, so instrumentation did not materially perturb the sequential latency stream. The endpoint was always `http://192.168.20.62:11434`; no tunnel or local alternate port was used.

`/api/ps` evidence:

| Probe/phase | Result |
|---|---|
| A before | HTTP 200, `models=[]` |
| A midpoint/after | HTTP 200, qwen3.5:4b loaded, digest `2a654d98e6fba55d452b7043684e9b57a947e393bbffa62485a7aac05ee4eefd`, `size_vram=6088300544`, context 8192 |
| B before/midpoint/after | HTTP 200, same model remained loaded |
| C before/after | HTTP 200, same model remained loaded |
| final | HTTP 200, same model remained loaded |

The raw timeline is [api_ps_samples.jsonl](/home/yanbo/net_vlm_person_fallen_v2_optimization/06_p2l_remote_latency_forensics/03_runtime_telemetry/api_ps_samples.jsonl), with a compact CSV at [api_ps_timeline.csv](/home/yanbo/net_vlm_person_fallen_v2_optimization/06_p2l_remote_latency_forensics/07_analysis/api_ps_timeline.csv).

## Remote read-only limitation

The preflight and each probe snapshot attempted only read-only SSH commands for `nvidia-smi`, compute-process inventory, `ps`/Ollama PID inventory and service status. Authentication failed consistently:

```text
tiga@192.168.20.62: Permission denied (publickey,password)
```

Consequently [nvidia_smi_samples.csv](/home/yanbo/net_vlm_person_fallen_v2_optimization/06_p2l_remote_latency_forensics/03_runtime_telemetry/nvidia_smi_samples.csv), [process_samples.csv](/home/yanbo/net_vlm_person_fallen_v2_optimization/06_p2l_remote_latency_forensics/03_runtime_telemetry/process_samples.csv), and [ollama_pid_history.csv](/home/yanbo/net_vlm_person_fallen_v2_optimization/06_p2l_remote_latency_forensics/03_runtime_telemetry/ollama_pid_history.csv) contain explicit `unavailable` rows rather than fabricated GPU, workload, or PID values. No 1-second external GPU sampler could be attached, and no server mutation was attempted.

This leaves GPU utilization/VRAM pressure, other compute workloads, runner PID stability, systemd state and journal events unresolved. `/api/ps` residency observations support a runtime-state hypothesis but are not a complete daemon or hardware trace.
