#!/usr/bin/env python3
"""Q6 pre-authorisation runner foundation; it cannot make provider calls.

This revision is intentionally frozen with ``authorized=false``.  The only
allowed actions now are ``--self-test`` and ``--initialize-ledger``.  An image
generation execution runner must be opened only after a separate top-level Q6
authorisation and a new execution freeze; this file never circumvents that
authorization gate.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import sqlite3
from pathlib import Path

from retry_event_parser_v2 import parse_json_events, telemetry_from_events

ROOT = Path(__file__).resolve().parent
Q5_RAW_FAILURE = ROOT.parent / "quota_campaign_window_02_policy_adapter_20260830_01" / "04_raw_responses" / "PF_P4D_NEG_CHAIR_G003_V03.json"
PLAN = ROOT / "02_plan/q6_balanced_window_33_plan.csv"
AUTH = ROOT / "05_checkpoints/authorization_gate.json"
LEDGER = ROOT / "03_ledger/gr3q6.sqlite3"

MAX_LOGICAL_INVOCATIONS = 33
MAX_PHYSICAL_ATTEMPT_LOWER_BOUND = 36
MAX_UNIQUE_NATIVE_RETRY_EVENTS = 3
MAX_CONFIRMED_POLICY_REFUSALS = 3
CONCURRENCY = 1
OUTER_RETRY = False
ADAPTER_VERSION = "CODEX_SAFE_STAGED_CV_V1"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def q5_parser_self_test() -> dict[str, int]:
    raw = json.loads(Q5_RAW_FAILURE.read_text(encoding="utf-8"))
    values = telemetry_from_events(parse_json_events(raw["stderr_redacted"]))
    assert values == {
        "unique_native_retry_events": 3,
        "request_started_events": 4,
        "physical_attempt_lower_bound": 4,
    }, values
    return values


def initialize_ledger() -> None:
    if LEDGER.exists():
        raise RuntimeError(f"ledger already exists: {LEDGER}")
    with PLAN.open(encoding="utf-8", newline="") as handle:
        plan = list(csv.DictReader(handle))
    if len(plan) != MAX_LOGICAL_INVOCATIONS or len({row["prompt_id"] for row in plan}) != len(plan):
        raise RuntimeError("invalid frozen Q6 plan")
    db = sqlite3.connect(LEDGER)
    try:
        db.execute("PRAGMA journal_mode=WAL")
        db.execute("PRAGMA synchronous=FULL")
        db.execute("CREATE TABLE metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
        db.execute("""CREATE TABLE slots (
            q6_order INTEGER PRIMARY KEY, prompt_id TEXT UNIQUE NOT NULL,
            group_id TEXT NOT NULL, role TEXT NOT NULL, taxonomy TEXT NOT NULL,
            planned_split TEXT NOT NULL, state TEXT NOT NULL,
            native_retry_events INTEGER NOT NULL DEFAULT 0,
            request_started_events INTEGER NOT NULL DEFAULT 0,
            physical_attempt_lower_bound INTEGER NOT NULL DEFAULT 0
        )""")
        db.execute("""CREATE TABLE invocation_events (
            id INTEGER PRIMARY KEY, prompt_id TEXT NOT NULL, event_type TEXT NOT NULL,
            event_json TEXT NOT NULL, created_utc TEXT NOT NULL
        )""")
        for key, value in {
            "stage": "P4D_GR3Q6_BALANCED_QUOTA_RESET_RECOVERY",
            "authorization_required": "true",
            "authorization_present": "false",
            "plan_sha256": sha256(PLAN),
            "adapter_version": ADAPTER_VERSION,
            "max_logical_invocations": str(MAX_LOGICAL_INVOCATIONS),
            "max_physical_attempt_lower_bound": str(MAX_PHYSICAL_ATTEMPT_LOWER_BOUND),
            "max_unique_native_retry_events": str(MAX_UNIQUE_NATIVE_RETRY_EVENTS),
            "max_confirmed_policy_refusals": str(MAX_CONFIRMED_POLICY_REFUSALS),
            "concurrency": str(CONCURRENCY),
            "outer_retry": str(OUTER_RETRY).lower(),
        }.items():
            db.execute("INSERT INTO metadata VALUES (?, ?)", (key, value))
        db.executemany(
            "INSERT INTO slots(q6_order,prompt_id,group_id,role,taxonomy,planned_split,state) VALUES(?,?,?,?,?,?,?)",
            [(int(r["q6_order"]), r["prompt_id"], r["group_id"], r["role"], r["taxonomy"], r["planned_split"], "NOT_STARTED") for r in plan],
        )
        db.commit()
        db.execute("PRAGMA wal_checkpoint(FULL)")
    finally:
        db.close()


def require_authorization() -> None:
    auth = json.loads(AUTH.read_text(encoding="utf-8"))
    if auth.get("authorized") is not True:
        raise RuntimeError("provider execution refused: Q6 has no independent top-level authorization")
    # This preparation revision is immutable.  Even a later authorization must
    # be bound into a new execution freeze rather than mutating this gate.
    raise RuntimeError("provider execution refused: create a new Q6 execution freeze after authorization")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument("--initialize-ledger", action="store_true")
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        print(json.dumps(q5_parser_self_test(), sort_keys=True))
    if args.initialize_ledger:
        initialize_ledger()
        print(json.dumps({"ledger": str(LEDGER), "status": "PREAUTHORIZED_NOT_STARTED"}, sort_keys=True))
    if args.execute:
        require_authorization()
    if not (args.self_test or args.initialize_ledger or args.execute):
        parser.error("select --self-test, --initialize-ledger, or --execute")


if __name__ == "__main__":
    main()
