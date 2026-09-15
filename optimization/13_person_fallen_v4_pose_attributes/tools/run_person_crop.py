#!/usr/bin/env python3
"""Run the frozen generic person detector and prepare full + crop views."""

from __future__ import annotations

import io
import math
import os
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
os.environ.setdefault("YOLO_CONFIG_DIR", str(ROOT / "detector/ultralytics_config"))

from PIL import Image, ImageOps
import ultralytics
from ultralytics import YOLO

from common import atomic_csv, atomic_json, load_csv, load_json, sha256


CONFIG = ROOT / "protocol/v4_diagnostic_config.json"
MANIFEST = ROOT / "manifests/v4_diagnostic_110.csv"
WEIGHT = ROOT / "assets/person_detector/yolo11n.pt"
DETECTIONS = ROOT / "detector/person_detections.csv"
CROPS = ROOT / "manifests/v4_crop_manifest.csv"
SUMMARY = ROOT / "detector/detector_summary.json"
RESAMPLE = getattr(getattr(Image, "Resampling", Image), "LANCZOS")


def letterbox_bytes(image: Image.Image, cfg: dict) -> bytes:
    width, height = cfg["width"], cfg["height"]
    view = image.convert("RGB")
    view.thumbnail((width, height), RESAMPLE)
    canvas = Image.new("RGB", (width, height), tuple(cfg["letterbox_rgb"]))
    canvas.paste(view, ((width - view.width) // 2, (height - view.height) // 2))
    buffer = io.BytesIO()
    canvas.save(buffer, "JPEG", quality=cfg["jpeg_quality"], optimize=True)
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


def atomic_bytes(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_bytes(data)
    os.replace(temporary, path)


def main() -> int:
    cfg = load_json(CONFIG)
    det = cfg["detector"]
    prep = cfg["preprocess"]
    if Path(sys.executable).resolve() != Path(det["runtime_python"]).resolve():
        raise RuntimeError(
            f"detector runtime mismatch: {sys.executable} != {det['runtime_python']}"
        )
    if ultralytics.__version__ != det["ultralytics_version"]:
        raise RuntimeError(
            f"ultralytics version mismatch: {ultralytics.__version__} != "
            f"{det['ultralytics_version']}"
        )
    if sha256(WEIGHT) != det["weight_sha256"]:
        raise RuntimeError("frozen detector weight SHA mismatch")
    rows = load_csv(MANIFEST)
    if len(rows) != 110:
        raise RuntimeError("diagnostic manifest must contain 110 rows")
    model = YOLO(str(WEIGHT))
    names = model.names
    if model.task != "detect" or (names.get(0) if hasattr(names, "get") else names[0]) != "person":
        raise RuntimeError("detector is not frozen COCO person model")

    detection_rows: list[dict[str, object]] = []
    crop_rows: list[dict[str, object]] = []
    for index, row in enumerate(rows, 1):
        source = Path(row["image_path"])
        if sha256(source) != row["image_sha256"]:
            raise RuntimeError(f"source image SHA mismatch: {row['diagnostic_id']}")
        with Image.open(source) as handle:
            image = ImageOps.exif_transpose(handle).convert("RGB")
        width, height = image.size
        result = model.predict(
            source=str(source), classes=[det["person_class_id"]],
            conf=det["confidence_threshold"], iou=det["nms_iou_threshold"],
            imgsz=det["imgsz"], max_det=det["max_persons"], verbose=False, device="cpu",
        )[0]
        boxes: list[dict[str, float]] = []
        result_boxes = getattr(result, "boxes", None)
        if result_boxes is not None:
            for xyxy, confidence, class_id in zip(
                result_boxes.xyxy.cpu().tolist(),
                result_boxes.conf.cpu().tolist(),
                result_boxes.cls.cpu().tolist(),
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
        full_path = ROOT / "prepared" / row["diagnostic_id"] / "full_scene.jpg"
        crop_path = ROOT / "prepared" / row["diagnostic_id"] / "person_crop.jpg"
        full_data = letterbox_bytes(image, prep)
        crop_data = letterbox_bytes(crop, prep)
        atomic_bytes(full_path, full_data)
        atomic_bytes(crop_path, crop_data)
        detection_rows.append({
            "diagnostic_id": row["diagnostic_id"], "item_id": row["item_id"],
            "diagnostic_class": row["diagnostic_class"], "source_width": width,
            "source_height": height, "detected_box_count": len(boxes),
            "accepted_box_count": len(accepted), "person_detected": str(chosen is not None).lower(),
            "confidence": "" if chosen is None else chosen["confidence"],
            "box_area_ratio": "" if chosen is None else chosen["box_area_ratio"],
            "x1": "" if chosen is None else chosen["x1"], "y1": "" if chosen is None else chosen["y1"],
            "x2": "" if chosen is None else chosen["x2"], "y2": "" if chosen is None else chosen["y2"],
            "crop_box": ",".join(str(value) for value in crop_box),
        })
        crop_rows.append({
            **row,
            "person_detected": str(chosen is not None).lower(),
            "detector_confidence": "" if chosen is None else chosen["confidence"],
            "detector_box_area_ratio": "" if chosen is None else chosen["box_area_ratio"],
            "full_view_path": str(full_path), "full_view_sha256": sha256(full_path),
            "crop_view_path": str(crop_path), "crop_view_sha256": sha256(crop_path),
            "view_count": 2 if chosen is not None else 1,
        })
        print(f"[{index}/110] {row['diagnostic_id']} detected={chosen is not None}", flush=True)

    detection_fields = list(detection_rows[0])
    crop_fields = list(crop_rows[0])
    atomic_csv(DETECTIONS, detection_fields, detection_rows)
    atomic_csv(CROPS, crop_fields, crop_rows)
    detected = sum(row["person_detected"] == "true" for row in crop_rows)
    by_class = {}
    for name in ("floor_sitting", "lying"):
        subset = [row for row in crop_rows if row["diagnostic_class"] == name]
        count = sum(row["person_detected"] == "true" for row in subset)
        by_class[name] = {"total": len(subset), "detected": count, "coverage": count / len(subset)}
    summary = {
        "status": "PASS",
        "detector_name": det["name"], "weight_sha256": sha256(WEIGHT),
        "runtime_python": sys.executable,
        "ultralytics_version": ultralytics.__version__,
        "sample_count": len(crop_rows), "person_detected_count": detected,
        "person_detection_coverage": detected / len(crop_rows), "by_class": by_class,
        "confidence_threshold": det["confidence_threshold"],
        "minimum_box_area_ratio": det["minimum_box_area_ratio"],
        "crop_manifest": str(CROPS), "crop_manifest_sha256": sha256(CROPS),
        "vlm_request_count": 0, "screen_rows_read": 0, "val_rows_read": 0,
        "holdout_rows_read": 0,
    }
    atomic_json(SUMMARY, summary)
    print(summary)
    return 0


if __name__ == "__main__":
    sys.exit(main())
