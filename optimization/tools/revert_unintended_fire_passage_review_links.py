#!/usr/bin/env python3
"""Revert only the 45 cross-event review links created by this ingest run."""

from __future__ import annotations

import argparse
import csv
import json
import os
import sys
from collections import Counter
from pathlib import Path


DATASET_ROOT = Path("/home/yanbo/net_vlm_xunjian_dataset")
EVENT_NAME = "fire_passage_blocked"
REVIEW_ROOT = DATASET_ROOT / "02_review_by_event" / EVENT_NAME
RAW_ROOT = (
    DATASET_ROOT
    / "00_raw/ai_generated/images/fire_passage_blocked_aigc_v1_static"
).resolve()
LABELS_PATH = DATASET_ROOT / "01_annotations/labels.csv"
MEDIA_PATH = DATASET_ROOT / "01_annotations/media.csv"
LOWER_MTIME = 1788333156.58
UPPER_MTIME = 1788333156.60
EXPECTED_COUNT = 45
EXPECTED_ROLES = {"negative": 18, "positive": 27}
REPORT_PATH = Path(
    "/home/yanbo/net_vlm_person_fallen_v2_optimization/reports/"
    "person_fallen_v3_cross_event_rebuild_reversal_audit.json"
)


def read_rows(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def is_within(path: Path, root: Path) -> bool:
    try:
        return os.path.commonpath((str(path), str(root))) == str(root)
    except ValueError:
        return False


def inspect_candidates() -> tuple[list[dict[str, object]], list[str]]:
    media_by_id = {row["media_id"]: row for row in read_rows(MEDIA_PATH)}
    labels_by_pair = {
        (row["media_id"], row["event_name"]): row for row in read_rows(LABELS_PATH)
    }
    candidates: list[dict[str, object]] = []
    errors: list[str] = []
    for path in sorted(REVIEW_ROOT.rglob("*")):
        if not path.is_symlink():
            continue
        mtime = path.lstat().st_mtime
        if not (LOWER_MTIME <= mtime <= UPPER_MTIME):
            continue
        media_id = path.name.split("__", 1)[0]
        target = path.resolve(strict=False)
        role = path.parent.name
        label = labels_by_pair.get((media_id, EVENT_NAME))
        media = media_by_id.get(media_id)
        if label is None:
            errors.append(f"{path}: missing fire_passage_blocked label")
        elif label["sample_role"] != role:
            errors.append(f"{path}: role does not match label")
        if media is None:
            errors.append(f"{path}: missing media row")
        elif (DATASET_ROOT / media["relative_path"]).resolve() != target:
            errors.append(f"{path}: target does not match media row")
        if not target.is_file():
            errors.append(f"{path}: broken target")
        elif not is_within(target, RAW_ROOT):
            errors.append(f"{path}: target outside expected fire-passage raw root")
        candidates.append(
            {
                "relative_link": path.relative_to(DATASET_ROOT).as_posix(),
                "relative_target": target.relative_to(DATASET_ROOT).as_posix()
                if is_within(target, DATASET_ROOT.resolve())
                else str(target),
                "media_id": media_id,
                "role": role,
                "mtime": mtime,
            }
        )
    roles = Counter(str(item["role"]) for item in candidates)
    if len(candidates) != EXPECTED_COUNT:
        errors.append(f"candidate_count={len(candidates)} != {EXPECTED_COUNT}")
    if dict(roles) != EXPECTED_ROLES:
        errors.append(f"role_counts={dict(roles)} != {EXPECTED_ROLES}")
    return candidates, errors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="unlink verified candidates")
    args = parser.parse_args()
    candidates, errors = inspect_candidates()
    report = {
        "operation": "revert_unintended_cross_event_review_links",
        "event_name": EVENT_NAME,
        "reason": (
            "global rebuild-links created non-target links during the "
            "person_fallen v3 Codex ingest; restore the pre-task boundary"
        ),
        "apply_requested": args.apply,
        "candidate_count": len(candidates),
        "role_counts": dict(Counter(str(item["role"]) for item in candidates)),
        "expected_count": EXPECTED_COUNT,
        "expected_role_counts": EXPECTED_ROLES,
        "preflight_errors": errors,
        "candidates": candidates,
    }
    if args.apply and not errors:
        for item in candidates:
            path = DATASET_ROOT / str(item["relative_link"])
            if not path.is_symlink():
                errors.append(f"{path}: no longer a symlink at apply")
                break
            path.unlink()
        report["reverted_link_count"] = len(candidates) if not errors else 0
    else:
        report["reverted_link_count"] = 0
    report["status"] = "ok" if not errors else "error"
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(report, ensure_ascii=False, sort_keys=True))
    return 0 if not errors else 1


if __name__ == "__main__":
    sys.exit(main())
