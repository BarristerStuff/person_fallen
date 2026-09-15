#!/usr/bin/env python3
"""Compatibility launcher for the frozen S1 shared response stream.

The candidate registry names the model adjudication view ``S1_DIRECT`` while
the filesystem stores its shared prompt under ``S1_STRUCTURED``.  This
launcher aliases only that name before calling the already-frozen durable
runner; it does not alter the runner source, request payload, or parser.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path("/home/yanbo/net_vlm_person_fallen_v2_optimization")
sys.path.insert(0, str(ROOT / "tools"))
import p3_inference_runner as runner  # noqa: E402

_original_prompt_path = runner.prompt_path
_original_verify_candidate_freeze = runner.verify_candidate_freeze


def _prompt_path(candidate: str) -> Path:
    if candidate == "S1_DIRECT":
        return runner.P3 / "03_candidates/S1_STRUCTURED/S1_prompt.txt"
    return _original_prompt_path(candidate)


runner.prompt_path = _prompt_path


def _verify_candidate_freeze(candidate: str, manifest: Path) -> None:
    # The frozen registry calls the shared stream S1_DIRECT/S1_RULE; the
    # durable runner's CLI calls the physical stream S1_STRUCTURED.
    if candidate == "S1_STRUCTURED":
        return _original_verify_candidate_freeze("S1_DIRECT", manifest)
    return _original_verify_candidate_freeze(candidate, manifest)


runner.verify_candidate_freeze = _verify_candidate_freeze
if len(sys.argv) >= 3 and sys.argv[2] == "S1_DIRECT":
    sys.argv[2] = "S1_STRUCTURED"
runner.main()
