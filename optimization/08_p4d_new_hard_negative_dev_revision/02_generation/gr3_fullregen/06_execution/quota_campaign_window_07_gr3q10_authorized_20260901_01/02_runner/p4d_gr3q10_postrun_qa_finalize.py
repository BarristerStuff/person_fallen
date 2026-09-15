#!/usr/bin/env python3
"""Finalize GR3Q10 after a terminal provider stop without calling the provider.

The execution runner has already been frozen by its execution-start binding
audit and must not be edited after provider requests were sent.  This small
post-run wrapper reuses its mechanical-QA/freeze helpers, while correcting the
partition edge case where unattempted rows have no per-slot response JSON.
It deliberately performs no provider operation and records the executed
runner hash separately from this QA-only wrapper.
"""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path


RUNNER_PATH = Path(__file__).with_name("p4d_gr3q10_authorized_execution.py")
spec = importlib.util.spec_from_file_location("p4d_gr3q10_authorized_execution", RUNNER_PATH)
if spec is None or spec.loader is None:
    raise RuntimeError(f"cannot import execution runner: {RUNNER_PATH}")
runner = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runner)


def main() -> int:
    # This is a post-run-only tool.  These checks fail closed before any QA
    # artifact is written if the terminal execution evidence is incomplete.
    runner.require(runner.GLOBAL_STOP.is_file(), "missing terminal execution checkpoint")
    stop = runner.read_json(runner.GLOBAL_STOP)
    runner.require(
        stop.get("terminal_stop_reason") == "STOP_AFTER_FAILED_CONFIRMED",
        "post-run finalizer expects the observed confirmed-failure terminal stop",
    )
    runner.require(
        stop.get("no_provider_request_after_stop") is True,
        "terminal checkpoint does not prove provider stop",
    )

    rows = runner.plan_rows()
    db = runner.load_db_rows()
    runner.require(
        all(row["prompt_id"] in db for row in rows),
        "ledger does not contain every frozen plan row",
    )
    runner.require(
        not any(slot["state"] == "STARTED" for slot in db.values()),
        "cannot finalize while a durable STARTED slot remains unresolved",
    )

    # The runner identity used for the provider calls was bound before the
    # first request.  Verify that the execution runner itself is unchanged;
    # this wrapper is not allowed to substitute a new execution identity.
    config = runner.read_json(runner.CONFIG_PATH)
    executed_runner_sha = config.get("runner_sha256")
    runner.require(executed_runner_sha, "run config has no execution runner hash")
    runner.require(
        executed_runner_sha == runner.sha256_path(runner.RUNNER),
        "execution runner changed after the provider window",
    )

    # Any Q10 row that did not mechanically pass or become completion-unknown
    # must be returned to the prior safe-outstanding partition.  All selected
    # Q10 rows are present there at the Q9 boundary, so remove these rows from
    # the base list before the original helper adds them back exactly once.
    safe_return_ids = {
        row["prompt_id"]
        for row in rows
        if db[row["prompt_id"]]["state"] not in {"SUCCESS", "COMPLETION_UNKNOWN"}
    }
    original_partition = runner.base_partition_rows
    original_read_json = runner.read_json
    base_fields, base_verified, base_unknown, base_safe = original_partition()
    base_safe_ids = {row["prompt_id"] for row in base_safe}
    runner.require(
        safe_return_ids <= base_safe_ids,
        "a non-passing Q10 row is absent from the base safe-outstanding partition",
    )

    def corrected_base_partition():
        return (
            base_fields,
            base_verified,
            base_unknown,
            [row for row in base_safe if row["prompt_id"] not in safe_return_ids],
        )

    def allow_missing_unattempted_response(path: Path):
        # Original make_qa expects a response object for every planned row;
        # NOT_STARTED rows intentionally have no provider response artifact.
        if path.parent == runner.RAW_RESP_DIR and not path.is_file():
            return {}
        return original_read_json(path)

    runner.base_partition_rows = corrected_base_partition
    runner.read_json = allow_missing_unattempted_response

    runner.write_json(
        runner.QA_DIR / "postrun_qa_tool_binding.json",
        {
            "revision_id": runner.REV_ID,
            "tool": str(Path(__file__)),
            "tool_sha256": runner.sha256_path(Path(__file__)),
            "purpose": "post-run mechanical QA, partition repair, and terminal freeze only",
            "provider_operation_performed": False,
            "executed_runner_sha256": executed_runner_sha,
            "current_execution_runner_sha256": runner.sha256_path(runner.RUNNER),
            "safe_return_row_count": len(safe_return_ids),
            "safe_return_prompt_ids": sorted(safe_return_ids),
        },
    )

    qa = runner.make_qa()
    freeze_sha, sidecar_sha = runner.freeze_revision(qa)
    runner.write_final_report(qa, freeze_sha, sidecar_sha)
    print(
        json.dumps(
            {
                "status": "FINAL_REPORT_WRITTEN",
                "revision_id": runner.REV_ID,
                "provider_operation_performed": False,
                "accounting": qa["accounting_after"],
                "mechanical_pass_rows": qa["mechanical_pass_rows"],
                "completion_unknown_rows": qa["completion_unknown_rows"],
                "safe_return_rows": qa["safe_return_rows"],
                "freeze_sha256": freeze_sha,
                "freeze_sidecar_sha256": sidecar_sha,
                "final_report": str(runner.REPORT_FINAL),
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
