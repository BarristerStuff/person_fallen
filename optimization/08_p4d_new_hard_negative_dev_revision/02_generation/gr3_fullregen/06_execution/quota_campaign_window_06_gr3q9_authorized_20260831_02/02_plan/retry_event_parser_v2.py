#!/usr/bin/env python3
"""Q6-native JSONL telemetry parser.

The parser deliberately counts *one parsed event line* at a time.  It never
counts substrings: a retry event may contain both a ``type`` and a ``phase``
whose values are ``retry_scheduled``.
"""
from __future__ import annotations

import json
from collections.abc import Iterable
from typing import Any


def parse_json_events(stderr_text: str) -> list[dict[str, Any]]:
    """Return only valid JSON-object lines from a provider stderr JSONL stream."""
    parsed: list[dict[str, Any]] = []
    for line in stderr_text.splitlines():
        try:
            value = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict):
            parsed.append(value)
    return parsed


def telemetry_from_events(events: Iterable[dict[str, Any]]) -> dict[str, int]:
    """Compute Q6 counters from event types, not textual occurrences."""
    retries: set[tuple[object, object, object]] = set()
    request_started_events = 0
    for event in events:
        event_type = event.get("type")
        data = event.get("data")
        if not isinstance(data, dict):
            data = {}
        if event_type == "retry_scheduled":
            # The tuple gives an optional deduplication key while preserving a
            # distinct parsed retry event if the provider did not supply fields.
            retries.add((data.get("logical_request_id"), data.get("retry_number"), data.get("status_code")))
        elif event_type == "request.started":
            request_started_events += 1
    return {
        "unique_native_retry_events": len(retries),
        "request_started_events": request_started_events,
        "physical_attempt_lower_bound": request_started_events,
    }
