#!/usr/bin/env python3
"""Bind prompt-derived records, local split freeze, and formal media IDs."""
from __future__ import annotations

import csv
import hashlib
from pathlib import Path

OUT = Path('/home/yanbo/net_vlm_person_fallen_v2_optimization/01_data')
DATA = Path('/home/yanbo/net_vlm_xunjian_dataset/01_annotations')
FIELDS = ['media_id','image_filename','formal_relative_path','source_image_path','image_sha256','prompt_filename','prompt_path','prompt_sha256','event_label','sample_role','scenario_id','group_id','split','split_reason','source_type','event_definition_version','gt_basis','review_status']

def load(path: Path):
    with path.open(encoding='utf-8',newline='') as f: return list(csv.DictReader(f))

def digest(path: Path) -> str:
    h=hashlib.sha256()
    with path.open('rb') as f:
        for b in iter(lambda:f.read(1024*1024),b''):h.update(b)
    return h.hexdigest()

def main():
    mapping={r['image_filename']:r for r in load(OUT/'prompt_image_mapping.csv')}
    cls={r['image_filename']:r for r in load(OUT/'prompt_classification.csv')}
    split={r['image_filename']:r for r in load(OUT/'frozen_splits.csv')}
    media={r['original_filename']:r for r in load(DATA/'media.csv') if r['capture_batch']=='batch_person-fallen-v2-camera1p5m'}
    labels={r['media_id']:r for r in load(DATA/'labels.csv') if r['event_name']=='person_fallen'}
    if set(mapping)!=set(media) or len(media)!=500 or len(labels)!=500:
        raise SystemExit(f'manifest join invariant failed mapping={len(mapping)} media={len(media)} labels={len(labels)}')
    rows=[]
    for name in sorted(mapping):
        m,c,s,f,l=mapping[name],cls[name],split[name],media[name],labels[media[name]['media_id']]
        if f['sha256'] != m['image_sha256'] or l['event_label'] != c['event_label'] or l['sample_role'] != c['sample_role']:
            raise SystemExit(f'formal/source mismatch for {name}')
        rows.append({'media_id':f['media_id'],'image_filename':name,'formal_relative_path':f['relative_path'],'source_image_path':m['image_path'],'image_sha256':m['image_sha256'],'prompt_filename':m['prompt_filename'],'prompt_path':m['prompt_path'],'prompt_sha256':m['prompt_sha256'],'event_label':c['event_label'],'sample_role':c['sample_role'],'scenario_id':s['scenario_id'],'group_id':s['group_id'],'split':s['split'],'split_reason':s['split_reason'],'source_type':'ai_generated','event_definition_version':l['event_definition_version'],'gt_basis':c['gt_basis'],'review_status':l['review_status']})
    with (OUT/'frozen_manifest.csv').open('w',encoding='utf-8',newline='') as f:
        w=csv.DictWriter(f,fieldnames=FIELDS,lineterminator='\n');w.writeheader();w.writerows(rows)
    with (OUT/'frozen_manifest.sha256').open('w',encoding='utf-8') as f: f.write(f'{digest(OUT/"frozen_manifest.csv")}  frozen_manifest.csv\n')
    print(f'FROZEN_MANIFEST=PASS rows={len(rows)} sha256={digest(OUT/"frozen_manifest.csv")}')
if __name__=='__main__': main()
