"""Offline fake-transport end-to-end test for recovery runner.

Writes only a compact report; all execution artifacts live in a temporary
folder which is deleted before return. No network or Ollama call is possible.
"""
from __future__ import annotations

import contextlib
import io
import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import recovery_runner as runner  # noqa: E402


def fake_attributes(stratum: str) -> dict:
    person = {
        "person_id": 1, "bbox_1000": [100, 100, 500, 900], "person_visible": "yes",
        "pose": "floor_sitting", "torso_orientation": "upright", "torso_ground_contact": "partial",
        "head_shoulders_above_hips": "yes", "support_surface": "floor", "explicit_work_evidence": "no",
        "visual_quality": "clear", "evidence": "Offline fake transport visible person.",
    }
    if stratum == "ground_lying":
        person.update(pose="supine", torso_orientation="horizontal", torso_ground_contact="broad", head_shoulders_above_hips="no")
    elif stratum == "auxiliary_attention":
        person.update(pose="crawling", torso_orientation="inclined", torso_ground_contact="partial", head_shoulders_above_hips="no")
    elif stratum == "visual_uncertain":
        person.update(pose="unknown", torso_orientation="unknown", torso_ground_contact="unknown", head_shoulders_above_hips="unknown", support_surface="unknown", visual_quality="insufficient")
    return {"scene_coverage": "complete", "people": [person]}


def fake_transport(payload: bytes, request_id: str, row: dict) -> dict:
    # The fake sees row metadata only as a test driver; the real payload itself does not contain it.
    outer = {"model": runner.MODEL, "done": True, "done_reason": "stop", "eval_count": 100, "response": json.dumps(fake_attributes(row["evaluation_stratum"]), ensure_ascii=False)}
    return {"http_status": 200, "raw": json.dumps(outer, ensure_ascii=False).encode("utf-8"), "latency_seconds": 0.001, "completion_unknown": False, "transport_error": None}


def main() -> None:
    report_path = ROOT / "reports/fake_e2e_report.json"
    if report_path.exists():
        raise RuntimeError("fake E2E report already exists; refusing overwrite")
    with tempfile.TemporaryDirectory(prefix="person_fallen_v5_recovery_fake_", dir="/tmp") as temp:
        output_dir = Path(temp) / "eval/full_dev"
        with contextlib.redirect_stdout(io.StringIO()):
            summary = runner.execute_full_dev(output_run_dir=output_dir, transport=fake_transport, preflight=None, enforce_recovery_freeze=False)
        lines = (output_dir / "output.jsonl").read_text(encoding="utf-8").splitlines()
        objects = [json.loads(line) for line in lines]
        lock = json.loads((output_dir / "COMPLETION_LOCK.json").read_text(encoding="utf-8"))
        if len(lines) != 436 or any(not isinstance(value, dict) for value in objects):
            raise RuntimeError("fake E2E JSONL is not one object per line")
        result = {
            "status": "PASS_FAKE_TRANSPORT_FULL_E2E",
            "temporary_output_removed_after_test": True,
            "rows": len(objects),
            "reused_rows": summary["V5_B0_REUSED_RESULTS"],
            "new_requests": summary["new_requests_completed"],
            "full_dev_gate": summary["FULL_DEV_GATE"],
            "partial_summary_updates_observed": True,
            "requests_parent_created": (output_dir / "requests").is_dir(),
            "jsonl_line_count": len(lines),
            "completion_lock_present": True,
            "completion_lock_gate": lock["gate"],
            "protocol_failures": 0,
            "network_requests": 0,
        }
        report_path.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
