#!/usr/bin/env python3
"""Independent P2 result verifier and P1R paired comparison.

This implementation intentionally does not import the materializer's metric
code. It recomputes protocol and classification outcomes from persisted
predictions and independently checks durable evidence cardinality.
"""
from __future__ import annotations
import csv, hashlib, json, math, os, sqlite3
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path('/home/yanbo/net_vlm_person_fallen_v2_optimization')
P2 = ROOT / '05_p2_hard_negative_semantic_optimization'
VAL = P2 / '06_val'
P1R = ROOT / '04_p1r_freeze_binding_recovery/val'
OUT = VAL / 'result_verification.json'
LATENCY_GATE = 1.8520842

def sha(path: Path) -> str:
    h = hashlib.sha256()
    with path.open('rb') as f:
        for b in iter(lambda: f.read(1048576), b''):
            h.update(b)
    return h.hexdigest()

def load_csv(path: Path):
    with path.open(newline='', encoding='utf-8') as f:
        return list(csv.DictReader(f))

def ratio(a, b):
    return None if not b else a / b

def metrics(rows):
    valid = [r for r in rows if r['event_label'] in {'0', '1'} and r['canonical_ok'] == 'true']
    tp = fp = tn = fn = 0
    for r in valid:
        gt = r['event_label']; alert = r['predicted_binary_alert'] == 'true'
        if gt == '1' and alert: tp += 1
        elif gt == '1': fn += 1
        elif alert: fp += 1
        else: tn += 1
    hard = [r for r in valid if r['sample_role'] == 'hard_negative']
    ordinary = [r for r in valid if r['sample_role'] == 'negative']
    uncertain = sum(r['predicted_status'] == 'uncertain' for r in valid)
    return {
        'TP': tp, 'FP': fp, 'TN': tn, 'FN': fn,
        'precision': ratio(tp, tp + fp), 'recall': ratio(tp, tp + fn),
        'f1': ratio(2 * tp, 2 * tp + fp + fn),
        'accuracy': ratio(tp + tn, tp + tn + fp + fn),
        'fpr': ratio(fp, fp + tn), 'specificity': ratio(tn, tn + fp),
        'ordinary_negative_fpr': ratio(sum(r['predicted_binary_alert'] == 'true' for r in ordinary), len(ordinary)),
        'hard_negative_fpr': ratio(sum(r['predicted_binary_alert'] == 'true' for r in hard), len(hard)),
        'positive_recall': ratio(tp, tp + fn),
        'model_uncertain_count': uncertain, 'model_uncertain_rate': ratio(uncertain, len(valid)),
        'gt_uncertain_prediction_distribution': dict(Counter(r['predicted_status'] for r in rows if r['event_label'] == 'uncertain')),
    }

def atomic(path: Path, obj):
    tmp = path.with_suffix(path.suffix + '.tmp')
    with tmp.open('w', encoding='utf-8') as f:
        json.dump(obj, f, ensure_ascii=False, indent=2, sort_keys=True)
        f.write('\n'); f.flush(); os.fsync(f.fileno())
    os.replace(tmp, path)

def main():
    summary = json.loads((VAL / 'summary.json').read_text())
    rows = load_csv(VAL / 'predictions.csv')
    raws = [json.loads(x) for x in (VAL / 'raw_responses.jsonl').read_text().splitlines()]
    logs = [json.loads(x) for x in (VAL / 'request_log.jsonl').read_text().splitlines()]
    manifest = load_csv(ROOT / '04_p1r_freeze_binding_recovery/preflight/recovery_val_manifest.csv')
    p1r = load_csv(P1R / 'predictions.csv')
    errors = []
    with sqlite3.connect(VAL / 'request_ledger.sqlite3') as db:
        states = dict(db.execute('SELECT state,count(*) FROM requests GROUP BY state'))
    ids = {r['media_id'] for r in manifest}; pred_ids = {r['media_id'] for r in rows}; raw_ids = {r['media_id'] for r in raws}; log_ids = {r['media_id'] for r in logs}; p1r_ids = {r['media_id'] for r in p1r}
    checks = {
        'manifest_count': len(manifest), 'prediction_count': len(rows), 'raw_count': len(raws), 'log_count': len(logs),
        'ledger_states': states, 'manifest_unique': len(ids), 'prediction_unique': len(pred_ids), 'raw_unique': len(raw_ids), 'log_unique': len(log_ids),
        'sets_match': ids == pred_ids == raw_ids == log_ids, 'canonical_all': all(r['canonical_ok'] == 'true' for r in rows),
        'holdout_rows': sum((r.get('split') or r.get('original_split')) == 'HOLDOUT' for r in manifest),
        'unknown_states': states.get('STARTED', 0) + states.get('NOT_STARTED', 0),
    }
    if any(checks[k] != 100 for k in ['manifest_count', 'prediction_count', 'raw_count', 'log_count']): errors.append('count_mismatch')
    if not checks['sets_match'] or checks['holdout_rows'] != 0 or checks['unknown_states'] != 0 or states != {'COMPLETED': 100} or not checks['canonical_all']: errors.append('durable_evidence_gate')
    recomputed = metrics(rows); reported = summary['metrics']
    compared_keys = ['TP', 'FP', 'TN', 'FN', 'precision', 'recall', 'f1', 'accuracy', 'fpr', 'specificity', 'ordinary_negative_fpr', 'hard_negative_fpr', 'positive_recall', 'model_uncertain_count', 'model_uncertain_rate']
    metric_match = all(recomputed.get(k) == reported.get(k) for k in compared_keys)
    if not metric_match: errors.append('metric_recompute_mismatch')
    p1r_by = {r['media_id']: r for r in p1r}; p2_by = {r['media_id']: r for r in rows}
    if p1r_ids != ids: errors.append('p1r_val_entity_set_mismatch')
    paired = {'baseline_FP_rescued': 0, 'new_FP_created': 0, 'baseline_TP_preserved': 0, 'new_FN_created': 0, 'baseline_FN_to_TP': 0}
    for media_id in sorted(ids):
        b = p1r_by[media_id]; w = p2_by[media_id]; gt = b['event_label']; ba = b['predicted_binary_alert'] == 'true'; wa = w['predicted_binary_alert'] == 'true'
        if gt == '0' and ba and not wa: paired['baseline_FP_rescued'] += 1
        if gt == '0' and not ba and wa: paired['new_FP_created'] += 1
        if gt == '1' and ba and wa: paired['baseline_TP_preserved'] += 1
        if gt == '1' and ba and not wa: paired['new_FN_created'] += 1
        if gt == '1' and not ba and wa: paired['baseline_FN_to_TP'] += 1
    lat = summary['protocol']['latency_seconds']; latency_gate = lat['p95'] <= LATENCY_GATE
    result = {
        'verification_result': 'PASS' if not errors else 'FAIL', 'checked_at_utc': datetime.now(timezone.utc).isoformat(),
        'checks': checks, 'recomputed_metrics': recomputed, 'summary_metrics': reported, 'metric_recompute_match': metric_match,
        'paired_vs_p1r': paired, 'p1r_baseline_metrics': json.loads((P1R / 'summary.json').read_text())['metrics'],
        'p2_val_protocol_gate': summary['protocol_gate_pass'], 'p2_val_latency_gate': latency_gate, 'latency_gate_limit_seconds': LATENCY_GATE,
        'p2_valid_validation_complete': bool(summary['protocol_gate_pass'] and not errors),
        'p2_reference_thresholds': {'precision_min': 0.93, 'hard_negative_fpr_max': 0.05, 'precision_pass': reported['precision'] >= 0.93, 'hard_negative_fpr_pass': reported['hard_negative_fpr'] <= 0.05},
        'errors': errors, 'P2_VALIDATION_COMPLETE': bool(summary['protocol_gate_pass'] and not errors), 'P2_VAL_IS_PRISTINE': False,
    }
    atomic(OUT, result); print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    if errors: raise SystemExit('P2_RESULT_VERIFICATION=FAIL')

if __name__ == '__main__': main()
