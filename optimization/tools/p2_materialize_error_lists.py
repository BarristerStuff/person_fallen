#!/usr/bin/env python3
"""Write derivative P2 VAL error lists after the one-shot run."""
from __future__ import annotations
import csv, os
from pathlib import Path

OUT = Path('/home/yanbo/net_vlm_person_fallen_v2_optimization/05_p2_hard_negative_semantic_optimization/06_val')

def main():
    with (OUT / 'predictions.csv').open(newline='', encoding='utf-8') as f:
        rows = list(csv.DictReader(f))
    if not rows:
        raise SystemExit('P2_ERROR_LISTS_NO_PREDICTIONS')
    fields = list(rows[0])
    subsets = {
        'false_positives.csv': [r for r in rows if r['event_label'] == '0' and r['predicted_binary_alert'] == 'true'],
        'false_negatives.csv': [r for r in rows if r['event_label'] == '1' and r['predicted_binary_alert'] != 'true'],
        'model_uncertain.csv': [r for r in rows if r['predicted_status'] == 'uncertain'],
    }
    for name, subset in subsets.items():
        tmp = OUT / (name + '.tmp')
        with tmp.open('w', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=fields)
            writer.writeheader(); writer.writerows(subset)
            f.flush(); os.fsync(f.fileno())
        os.replace(tmp, OUT / name)
    print({'false_positives': len(subsets['false_positives.csv']), 'false_negatives': len(subsets['false_negatives.csv']), 'model_uncertain': len(subsets['model_uncertain.csv'])})

if __name__ == '__main__':
    main()
