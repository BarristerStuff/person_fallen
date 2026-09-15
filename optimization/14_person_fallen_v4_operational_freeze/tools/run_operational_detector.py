#!/usr/bin/env python3
"""Prepare frozen full-scene and largest-person crop views for SCREEN/VAL."""

from __future__ import annotations

import argparse
import io
import math
import os
import sys
from collections import Counter
from pathlib import Path

from PIL import Image, ImageOps
import ultralytics
from ultralytics import YOLO

from common import ROOT, atomic_csv, atomic_json, load_csv, load_json, sha256


PLAN = ROOT / "protocol/final_operational_plan.json"
MANIFESTS = {
    "screen": ROOT / "manifests/person_fallen_v4_operational_screen.csv",
    "val": ROOT / "manifests/person_fallen_v4_operational_val.csv",
}
OUTPUTS = {
    "screen": (ROOT / "manifests/person_fallen_v4_operational_screen_crop.csv", ROOT / "detector/screen_detections.csv", ROOT / "detector/screen_detector_summary.json"),
    "val": (ROOT / "manifests/person_fallen_v4_operational_val_crop.csv", ROOT / "detector/val_detections.csv", ROOT / "detector/val_detector_summary.json"),
}
WEIGHT = ROOT / "assets/person_detector/yolo11n.pt"
RESAMPLE = getattr(getattr(Image, "Resampling", Image), "LANCZOS")


def atomic_bytes(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_bytes(data)
    os.replace(temporary, path)


def letterbox_bytes(image: Image.Image, cfg: dict) -> bytes:
    width, height = cfg["width"], cfg["height"]
    view = image.convert("RGB")
    view.thumbnail((width, height), RESAMPLE)
    canvas = Image.new("RGB", (width, height), tuple(cfg["letterbox_rgb"]))
    canvas.paste(view, ((width - view.width) // 2, (height - view.height) // 2))
    buffer = io.BytesIO()
    canvas.save(buffer, "JPEG", quality=cfg["jpeg_quality"], optimize=cfg["jpeg_optimize"])
    return buffer.getvalue()


def expanded_box(box: dict[str, float], width: int, height: int, cfg: dict) -> tuple[int, int, int, int]:
    bw = box["x2"] - box["x1"]
    bh = box["y2"] - box["y1"]
    return (
        max(0, math.floor(box["x1"] - cfg["crop_expand_x"] * bw)),
        max(0, math.floor(box["y1"] - cfg["crop_expand_y"] * bh)),
        min(width, math.ceil(box["x2"] + cfg["crop_expand_x"] * bw)),
        min(height, math.ceil(box["y2"] + cfg["crop_expand_y"] * bh)),
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("phase", choices=["screen", "val"])
    args = parser.parse_args()
    cfg = load_json(PLAN)
    det = cfg["detector"]
    prep = cfg["preprocess"]
    if Path(sys.executable).resolve() != Path(det["runtime_python"]).resolve():
        raise RuntimeError(f"detector runtime mismatch: {sys.executable}")
    if ultralytics.__version__ != det["ultralytics_version"]:
        raise RuntimeError(f"ultralytics version mismatch: {ultralytics.__version__}")
    if sha256(WEIGHT) != det["weight_sha256"]:
        raise RuntimeError("detector weight SHA mismatch")
    rows = load_csv(MANIFESTS[args.phase])
    if not rows:
        raise RuntimeError("empty evaluation manifest")
    model = YOLO(str(WEIGHT))
    names = model.names
    person_name = names.get(0) if hasattr(names, "get") else names[0]
    if model.task != "detect" or person_name != "person":
        raise RuntimeError("detector is not frozen COCO person model")

    crop_rows: list[dict] = []
    detection_rows: list[dict] = []
    for index, row in enumerate(rows, 1):
        source = Path(row["image_path"])
        if sha256(source) != row["image_sha256"]:
            raise RuntimeError(f"source SHA mismatch: {row['item_id']}")
        with Image.open(source) as handle:
            image = ImageOps.exif_transpose(handle).convert("RGB")
        width, height = image.size
        result = model.predict(
            source=str(source), classes=[det["person_class_id"]],
            conf=det["confidence_threshold"], iou=det["nms_iou_threshold"],
            imgsz=det["imgsz"], max_det=det["max_persons"], verbose=False, device="cpu",
        )[0]
        boxes = []
        result_boxes = getattr(result, "boxes", None)
        if result_boxes is not None:
            for xyxy, confidence, class_id in zip(
                result_boxes.xyxy.cpu().tolist(), result_boxes.conf.cpu().tolist(), result_boxes.cls.cpu().tolist()
            ):
                if int(class_id) != det["person_class_id"]:
                    continue
                x1, y1, x2, y2 = [float(value) for value in xyxy]
                area_ratio = max(0.0, x2 - x1) * max(0.0, y2 - y1) / (width * height)
                boxes.append({
                    "x1": max(0.0, min(width, x1)), "y1": max(0.0, min(height, y1)),
                    "x2": max(0.0, min(width, x2)), "y2": max(0.0, min(height, y2)),
                    "confidence": float(confidence), "box_area_ratio": area_ratio,
                })
        boxes.sort(key=lambda box: (-box["box_area_ratio"], -box["confidence"], box["x1"]))
        accepted = [box for box in boxes if box["box_area_ratio"] >= det["minimum_box_area_ratio"]]
        chosen = accepted[0] if accepted else None
        crop_box = (0, 0, width, height) if chosen is None else expanded_box(chosen, width, height, det)
        crop = image.crop(crop_box)
        full_path = ROOT / "prepared" / args.phase / row["operational_id"] / "full_scene.jpg"
        crop_path = ROOT / "prepared" / args.phase / row["operational_id"] / "person_crop.jpg"
        atomic_bytes(full_path, letterbox_bytes(image, prep))
        atomic_bytes(crop_path, letterbox_bytes(crop, prep))
        person_detected = chosen is not None
        detection_rows.append({
            "operational_id": row["operational_id"], "item_id": row["item_id"],
            "operational_class": row["operational_class"], "source_width": width,
            "source_height": height, "detected_box_count": len(boxes),
            "accepted_box_count": len(accepted), "person_detected": str(person_detected).lower(),
            "confidence": "" if chosen is None else chosen["confidence"],
            "box_area_ratio": "" if chosen is None else chosen["box_area_ratio"],
            "crop_box": ",".join(str(value) for value in crop_box),
        })
        crop_rows.append({
            **row,
            "person_detected": str(person_detected).lower(),
            "detector_confidence": "" if chosen is None else chosen["confidence"],
            "detector_box_area_ratio": "" if chosen is None else chosen["box_area_ratio"],
            "full_view_path": str(full_path), "full_view_sha256": sha256(full_path),
            "crop_view_path": str(crop_path), "crop_view_sha256": sha256(crop_path),
            "view_count": 2 if person_detected else 1,
        })
        print(f"[{index}/{len(rows)}] {row['operational_id']} detected={person_detected}", flush=True)

    crop_manifest, detections, summary_path = OUTPUTS[args.phase]
    atomic_csv(crop_manifest, list(crop_rows[0]), crop_rows)
    atomic_csv(detections, list(detection_rows[0]), detection_rows)
    detected = sum(row["person_detected"] == "true" for row in crop_rows)
    by_class = {}
    for name in ("ground_lying", "normal_negative"):
        subset = [row for row in crop_rows if row["operational_class"] == name]
        count = sum(row["person_detected"] == "true" for row in subset)
        by_class[name] = {"total": len(subset), "detected": count, "coverage": count / len(subset) if subset else None}
    summary = {
        "status": "PASS", "phase": args.phase, "sample_count": len(crop_rows),
        "person_detected_count": detected, "person_detection_coverage": detected / len(crop_rows),
        "by_operational_class": by_class, "detector_name": det["name"],
        "weight_sha256": sha256(WEIGHT), "runtime_python": sys.executable,
        "ultralytics_version": ultralytics.__version__, "crop_manifest": str(crop_manifest),
        "crop_manifest_sha256": sha256(crop_manifest), "vlm_request_count": 0,
        "screen_rows_read": 0, "val_rows_read": 0, "holdout_rows_read": 0,
    }
    atomic_json(summary_path, summary)
    print(summary)
    return 0


if __name__ == "__main__":
    sys.exit(main())
