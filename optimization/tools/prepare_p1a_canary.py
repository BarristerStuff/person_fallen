#!/usr/bin/env python3
"""Create the immutable 12-image, cross-group, DEV-only P1A protocol canary."""
from __future__ import annotations
import csv,hashlib
from pathlib import Path
ROOT=Path('/home/yanbo/net_vlm_person_fallen_v2_optimization');SOURCE=ROOT/'01_data/frozen_manifest.csv';OUT=ROOT/'03_p1a_think_false_protocol/canary/canary_manifest.csv'
TARGETS={'positive':4,'negative':2,'hard_negative':4,'uncertain':2}
def sha(p):
 h=hashlib.sha256();h.update(p.read_bytes());return h.hexdigest()
def main():
 with SOURCE.open(encoding='utf-8',newline='') as f:rows=list(csv.DictReader(f))
 selected=[]
 for role,want in TARGETS.items():
  eligible=sorted((r for r in rows if r['split']=='DEV' and r['sample_role']==role),key=lambda r:(r['group_id'],r['media_id']))
  seen=set()
  for r in eligible:
   if r['group_id'] not in seen: selected.append(r);seen.add(r['group_id'])
   if len(seen)==want:break
  if len(seen)!=want:raise SystemExit(f'cannot select {want} distinct DEV groups for {role}')
 if len(selected)!=12 or len({r['group_id'] for r in selected})!=12:raise SystemExit('canary group invariant failed')
 fields=list(rows[0])+['image_path']
 with OUT.open('w',encoding='utf-8',newline='') as f:
  w=csv.DictWriter(f,fieldnames=fields,lineterminator='\n');w.writeheader()
  for r in selected:w.writerow(dict(r,image_path='/home/yanbo/net_vlm_xunjian_dataset/'+r['formal_relative_path']))
 print(f'CANARY_MANIFEST=PASS rows=12 distinct_groups=12 sha256={sha(OUT)}')
if __name__=='__main__':main()
