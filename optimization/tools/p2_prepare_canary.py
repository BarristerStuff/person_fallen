#!/usr/bin/env python3
"""Create one fixed DESIGN-only protocol canary without prediction access."""
from __future__ import annotations
import csv,hashlib,os
from collections import defaultdict
from pathlib import Path

ROOT=Path('/home/yanbo/net_vlm_person_fallen_v2_optimization')
P2=ROOT/'05_p2_hard_negative_semantic_optimization'
SOURCE=P2/'01_internal_split/p2_design_manifest.csv'
DEST=P2/'03_candidates/protocol_canary_manifest.csv'
SEED='PERSON_FALLEN_V2_P2_PROTOCOL_CANARY_V1'

def sha(path):
 h=hashlib.sha256()
 with path.open('rb') as f:
  for b in iter(lambda:f.read(1048576),b''):h.update(b)
 return h.hexdigest()

def main():
 if DEST.exists():raise SystemExit('P2_CANARY_MANIFEST_ALREADY_EXISTS')
 with SOURCE.open(newline='',encoding='utf-8') as f:rows=list(csv.DictReader(f))
 groups=defaultdict(list)
 for row in rows:groups[(row['sample_role'],row['group_id'])].append(row)
 need={'positive':3,'negative':2,'hard_negative':3,'uncertain':1};selected=[]
 for role,count in need.items():
  candidates=[]
  for (candidate_role,group),items in groups.items():
   if candidate_role!=role:continue
   items=sorted(items,key=lambda row:hashlib.sha256(f'{SEED}|{row["media_id"]}'.encode()).hexdigest())
   candidates.append((hashlib.sha256(f'{SEED}|{role}|{group}'.encode()).hexdigest(),items[0]))
  selected.extend(row for _,row in sorted(candidates)[:count])
 if len(selected)!=9 or len({row['group_id'] for row in selected})!=9:raise SystemExit('P2_CANARY_SELECTION_INVALID')
 selected.sort(key=lambda row:row['media_id']);tmp=DEST.with_suffix('.csv.tmp')
 with tmp.open('w',newline='',encoding='utf-8') as f:
  w=csv.DictWriter(f,fieldnames=list(selected[0]));w.writeheader();w.writerows(selected);f.flush();os.fsync(f.fileno())
 os.replace(tmp,DEST)
 side=P2/'03_candidates/protocol_canary_manifest.sha256'
 with side.open('x',encoding='utf-8') as f:f.write(f'{sha(DEST)}  protocol_canary_manifest.csv\n');f.flush();os.fsync(f.fileno())
 print({'rows':len(selected),'groups':len({r['group_id'] for r in selected}),'roles':need,'sha256':sha(DEST),'prediction_rows_read':0})
if __name__=='__main__':main()
