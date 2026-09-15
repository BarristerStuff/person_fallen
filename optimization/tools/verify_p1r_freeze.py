#!/usr/bin/env python3
"""Independent, read-only P1R freeze verifier.

The recovery freeze is an execution binding.  This verifier deliberately never
rewrites it or its unlock token: re-verification must not create a new freeze
revision after an evaluation has started.
"""
from __future__ import annotations
import csv,hashlib,json,os
from datetime import datetime,timezone
from pathlib import Path
ROOT=Path('/home/yanbo/net_vlm_person_fallen_v2_optimization');P1R=ROOT/'04_p1r_freeze_binding_recovery';CAND=P1R/'preflight/recovery_freeze_candidate.json'
def sha(p):
 h=hashlib.sha256()
 with p.open('rb') as f:
  for b in iter(lambda:f.read(1048576),b''):h.update(b)
 return h.hexdigest()
def atomic(p,d):
 t=p.with_suffix(p.suffix+'.tmp')
 with t.open('w') as f:json.dump(d,f,indent=2);f.write('\n');f.flush();os.fsync(f.fileno())
 os.replace(t,p)
def main():
 c=json.loads(CAND.read_text());checks={};errors=[]
 for name,item in c['file_hashes'].items():
  p=Path(item['path']);actual=sha(p) if p.is_file() else None;ok=actual==item['sha256'];checks[name]={'path':str(p),'expected':item['sha256'],'actual':actual,'match':ok}
  if not ok:errors.append('hash:'+name)
 with (P1R/'preflight/recovery_val_manifest.csv').open(newline='') as f:val=list(csv.DictReader(f))
 ids=[x['media_id'] for x in val];manifest_checks={'rows':len(val),'unique_media':len(set(ids)),'holdout_rows':sum(x['split']=='HOLDOUT' for x in val),'non_val_rows':sum(x['split']!='VAL' for x in val),'uncertain_gt_rows':sum(x['event_label']=='uncertain' for x in val)}
 if manifest_checks!={'rows':100,'unique_media':100,'holdout_rows':0,'non_val_rows':0,'uncertain_gt_rows':0}:errors.append('manifest_shape')
 h=c['file_hashes']; original=json.loads(Path(h['original_freeze']['path']).read_text());hist_ok=original.get('dev_manifest_sha256')!=h['dev_manifest']['sha256'] and c['historical_p1a_freeze_binding_error'] is True
 if not hist_ok:errors.append('historical_mismatch_not_bound')
 freeze_path=P1R/'freeze/p1r_recovery_freeze.json'
 if not freeze_path.is_file(): errors.append('freeze_missing')
 else:
  freeze=json.loads(freeze_path.read_text())
  if freeze.get('freeze_candidate_sha256')!=sha(CAND):errors.append('freeze_candidate_sha_mismatch')
  for key,value in c.items():
   if freeze.get(key)!=value:errors.append('freeze_field_mismatch:'+key)
 status='PASS' if not errors else 'FAIL';verify={'FREEZE_VERIFICATION':status,'ALL_FILE_HASHES_MATCH':not any(e.startswith('hash:') for e in errors),'VAL_MANIFEST_ROWS':len(val),'VAL_UNIQUE_MEDIA':len(set(ids)),'HOLDOUT_ROWS':manifest_checks['holdout_rows'],'FREEZE_ARTIFACT_SHA256':sha(freeze_path) if freeze_path.is_file() else None,'READ_ONLY_VERIFIER':True,'errors':errors,'checks':checks,'manifest_checks':manifest_checks,'verified_at_utc':datetime.now(timezone.utc).isoformat()}
 atomic(P1R/'preflight/recovery_freeze_verification.json',verify)
 if status!='PASS':raise SystemExit('P1R_FREEZE_VERIFICATION_FAIL')
 print(json.dumps({'P1R_FREEZE_VERIFICATION':'PASS','freeze_sha256':verify['FREEZE_ARTIFACT_SHA256'],'val_manifest_sha256':sha(P1R/'preflight/recovery_val_manifest.csv'),'read_only_verifier':True},ensure_ascii=False))
if __name__=='__main__':main()
