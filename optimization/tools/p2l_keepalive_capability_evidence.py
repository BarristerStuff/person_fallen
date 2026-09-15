#!/usr/bin/env python3
"""Record non-mutating evidence for top-level Ollama keep_alive support."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path


ROOT = Path("/home/yanbo/net_vlm_person_fallen_v2_optimization")
OUT = ROOT / "06_p2l_remote_latency_forensics/00_preflight/p2l_keepalive_capability_evidence.json"
SOURCES = [
    Path("/home/yanbo/net_vlm_yanboversion/vlm/script/ollama_vlm.py"),
    Path("/home/yanbo/net_vlm_yanboversion/vlm/test_server_gateway.py"),
    Path("/home/yanbo/net_vlm_yanboversion/person_smoking_p1s_work_20260803/test_p1s_output_stability.py"),
]


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


evidence = []
for path in SOURCES:
    lines = path.read_text(encoding="utf-8").splitlines()
    hits = [(i + 1, line) for i, line in enumerate(lines) if "keep_alive" in line]
    evidence.append({"path": str(path), "sha256": sha(path), "matching_lines": hits[:12]})

payload = {
    "captured_at_utc": __import__("datetime").datetime.now(__import__("datetime").timezone.utc).isoformat(),
    "observed_ollama_version": "0.23.2",
    "endpoint": "http://192.168.20.62:11434",
    "method": "read-only local/project source inspection; no compatibility request or server mutation",
    "top_level_keep_alive_evidence": evidence,
    "accepted_probe_value": "30m",
    "keep_alive_zero_used": False,
    "conclusion": "existing project code and tests construct keep_alive as a top-level /api/generate field; Probe B may use top-level keep_alive=30m, while this artifact does not claim causal or production validation",
}
OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n")
print(json.dumps(payload, ensure_ascii=False, indent=2))
