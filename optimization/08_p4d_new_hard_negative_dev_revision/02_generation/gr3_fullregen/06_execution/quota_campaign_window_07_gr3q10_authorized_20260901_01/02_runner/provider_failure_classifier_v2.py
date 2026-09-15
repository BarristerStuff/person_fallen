#!/usr/bin/env python3
"""Structured provider-failure classifier for Q7 and later revisions.

Metadata keys such as ``safety_identifier`` are deliberately never inspected
as refusal evidence.  A refusal requires the image-generation call itself to
fail, a completed response, image_count=0, and an explicit refusal decision in
assistant output text.
"""
from __future__ import annotations
import json
import re
from typing import Any

def events(stderr: str) -> list[dict[str, Any]]:
    result=[]
    for line in stderr.splitlines():
        try: value=json.loads(line)
        except json.JSONDecodeError: continue
        if isinstance(value,dict): result.append(value)
    return result

def classify(raw: dict[str, Any]) -> dict[str, Any]:
    outer=raw.get('outer_json') or {}; error=outer.get('error') if isinstance(outer,dict) else {}
    error=error if isinstance(error,dict) else {}; code=str(error.get('code') or '')
    detail=str(error.get('detail') or ''); message=str(error.get('message') or '')
    stream=events(str(raw.get('stderr_redacted') or ''))
    response_completed=any(e.get('type')=='response.completed' for e in stream)
    image_call_failed=any(e.get('type')=='response.output_item.done' and isinstance(e.get('data',{}).get('item'),dict) and e['data']['item'].get('type')=='image_generation_call' and e['data']['item'].get('status')=='failed' for e in stream)
    image_count_zero=any(e.get('type')=='output_item_done' and e.get('data',{}).get('item_type')=='image_generation_call' and e.get('data',{}).get('image_count')==0 for e in stream)
    decision_text=' '.join(str(e.get('data',{}).get('text') or e.get('data',{}).get('part',{}).get('text') or '') for e in stream if e.get('type') in {'response.output_text.done','response.content_part.done'})
    explicit_decision=bool(re.search(r"(sorry[,! ]+i can.?t help|cannot help|can.?t help|content policy|safety policy|unable to comply)",decision_text,re.I))
    evidence={'error_code':code,'response_completed':response_completed,'image_generation_call_failed':image_call_failed,'image_count_zero':image_count_zero,'explicit_refusal_decision':explicit_decision,'metadata_fields_ignored':['safety_identifier','safety_id','metadata.safety_identifier']}
    if code=='network_error': return {'state':'COMPLETION_UNKNOWN','reason':'NETWORK_ERROR_COMPLETION_AMBIGUITY','evidence':evidence}
    if re.search(r'HTTP\s*429|usage_limit_reached',detail+' '+message,re.I): return {'state':'FAILED_CONFIRMED','reason':'HTTP429_USAGE_LIMIT_REACHED','evidence':evidence}
    if image_call_failed and response_completed and image_count_zero and explicit_decision:
        return {'state':'CONTENT_POLICY_REFUSAL_CONFIRMED','reason':'STRUCTURED_EXPLICIT_REFUSAL','evidence':evidence}
    return {'state':'FAILED_CONFIRMED','reason':'UNCLASSIFIED_PROVIDER_FAILURE','evidence':evidence}
