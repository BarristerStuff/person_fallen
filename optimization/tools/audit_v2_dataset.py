#!/usr/bin/env python3
"""Read-only checks for frozen V2 data/protocol boundaries."""
from __future__ import annotations
import csv, hashlib, json
from collections import Counter
from pathlib import Path

ROOT=Path('/home/yanbo/net_vlm_person_fallen_v2_optimization'); DATA=ROOT/'01_data'; DS=Path('/home/yanbo/net_vlm_xunjian_dataset')
def h(p):
 x=hashlib.sha256();x.update(p.read_bytes());return x.hexdigest()
def rows(p):
 with p.open(encoding='utf-8',newline='') as f:return list(csv.DictReader(f))
def main():
 m=rows(DATA/'frozen_manifest.csv'); split=rows(DATA/'frozen_splits.csv'); media=rows(DS/'01_annotations/media.csv');labels=rows(DS/'01_annotations/labels.csv')
 pfmedia=[r for r in media if r['capture_batch']=='batch_person-fallen-v2-camera1p5m']; pflabel=[r for r in labels if r['event_name']=='person_fallen']
 bad=[]
 if len(m)!=500 or len(split)!=500 or len(pfmedia)!=500 or len(pflabel)!=500:bad.append('count_mismatch')
 if any(r['split']=='HOLDOUT' and r['media_id']=='' for r in m):bad.append('missing_formal_holdout_id')
 group_splits={}
 for r in m:group_splits.setdefault(r['group_id'],set()).add(r['split'])
 if any(len(x)>1 for x in group_splits.values()):bad.append('group_crosses_split')
 payload={'status':'PASS' if not bad else 'FAIL','errors':bad,'frozen_manifest_count':len(m),'formal_person_fallen_media_count':len(pfmedia),'formal_person_fallen_label_count':len(pflabel),'event_definition_versions':sorted({r['event_definition_version'] for r in pflabel}),'split_counts':dict(Counter(r['split'] for r in m)),'role_counts':dict(Counter(r['sample_role'] for r in m)),'group_count':len(group_splits),'cross_split_group_count':sum(len(x)>1 for x in group_splits.values()),'frozen_manifest_sha256':h(DATA/'frozen_manifest.csv'),'frozen_splits_sha256':h(DATA/'frozen_splits.csv')}
 print(json.dumps(payload,ensure_ascii=False,indent=2))
if __name__=='__main__':main()
