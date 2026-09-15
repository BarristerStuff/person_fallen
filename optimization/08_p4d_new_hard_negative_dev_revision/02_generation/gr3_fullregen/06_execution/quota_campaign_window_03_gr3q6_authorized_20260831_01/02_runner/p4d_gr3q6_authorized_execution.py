#!/usr/bin/env python3
"""Authorized, single-run Q6 generation window with durable stop guards.

The script has exactly one provider-call site.  It only targets the separately
created Q6 execution revision and never mutates Q5 or the sealed preparation
revision.  The default workflow is ``init`` followed by ``run`` once.
"""
from __future__ import annotations

import argparse
import csv
import fcntl
import hashlib
import importlib.util
import json
import os
import re
import shutil
import sqlite3
import subprocess
import sys
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from PIL import Image

ROOT = Path('/home/yanbo/net_vlm_person_fallen_v2_optimization')
GR3 = ROOT / '08_p4d_new_hard_negative_dev_revision/02_generation/gr3_fullregen'
PREP = GR3 / '06_execution/quota_campaign_window_03_gr3q6_20260831_02'
EXEC = GR3 / '06_execution/quota_campaign_window_03_gr3q6_authorized_20260831_01'
Q5 = GR3 / '06_execution/quota_campaign_window_02_policy_adapter_20260830_01'
MANIFEST = GR3 / '03_fullregen_plan/full_regen_prompt_manifest.csv'
PLAN = PREP / '02_plan/q6_balanced_window_33_plan.csv'
ADAPTER_MANIFEST = Q5 / '01_adapter/render_prompt_manifest_v1.csv'
PARSER = PREP / 'retry_event_parser_v2.py'
CLI = Path('/home/yanbo/.codex/skills/gpt-image-2-skill/scripts/gpt_image_2_skill.cjs')
VALIDATOR = Path('/home/yanbo/net_vlm_xunjian_dataset/tools/validate_dataset.py')
ANNOTATIONS = Path('/home/yanbo/net_vlm_xunjian_dataset/01_annotations')

EXPECTED_Q5 = '3c219c9d75803cd5427862c0255ab557e92969085a864b116435aea85f8817f2'
EXPECTED_PREP = '0895c36bb13ce7fbd7c8eebb24deeea6ba650ef6247c294cc9656722b19dd900'
EXPECTED_SUPP = 'ad26987713e0a0910393a3c6613d24b7d5a1d63b63f3810bebfbe8ee8c56143b'
EXPECTED_PLAN = '11821c0b090706467cac98e84cddcecd76f9d2ac7d7a2b3ae0368e86c3a1f2f8'
MAX_LOGICAL = 33
MAX_PHYSICAL = 36
MAX_RETRIES = 3
MAX_REFUSALS = 3
FINAL_SIZE = (1920, 1080)
NATIVE_SIZE = '1536x1024'
QUALITY = 'medium'
MODEL = 'gpt-5.4'
PROVIDER = 'codex'
ADAPTER = 'CODEX_SAFE_STAGED_CV_V1'

DB = EXEC / '03_ledger/gr3q6_execution.sqlite3'
RAW = EXEC / '04_raw_responses'
RAW_IMAGES = EXEC / '07_generated_raw'
FINAL = EXEC / '08_final'
CHECK = EXEC / '05_checkpoints'
PREFLIGHT = EXEC / '00_preflight'
QA = EXEC / '06_partial_qa'
RUNNER = EXEC / '02_runner'
LOCK = GR3 / '06_execution/.p4d_gr3q6_active_runner.lock'


def utc() -> str:
    return datetime.now(timezone.utc).isoformat(timespec='milliseconds')


def digest(path: Path) -> str:
    h = hashlib.sha256()
    with path.open('rb') as f:
        for block in iter(lambda: f.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def atomic_json(path: Path, obj: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(path.name + '.tmp')
    with temp.open('w', encoding='utf-8') as f:
        json.dump(obj, f, ensure_ascii=False, indent=2, sort_keys=True)
        f.write('\n')
        f.flush(); os.fsync(f.fileno())
    os.replace(temp, path)
    fd = os.open(str(path.parent), os.O_DIRECTORY)
    try: os.fsync(fd)
    finally: os.close(fd)


def append_jsonl(path: Path, obj: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('a', encoding='utf-8') as f:
        f.write(json.dumps(obj, ensure_ascii=False, sort_keys=True) + '\n')
        f.flush(); os.fsync(f.fileno())


def csv_rows(path: Path) -> list[dict[str, str]]:
    with path.open(encoding='utf-8', newline='') as f:
        return list(csv.DictReader(f))


def scrub(value: str) -> str:
    value = re.sub(r'(?i)(authorization\s*:\s*bearer\s+)[^\s"\']+', r'\1<REDACTED>', value)
    value = re.sub(r'(?i)(access[_-]?token\s*[=:]\s*)[^\s,}"\']+', r'\1<REDACTED>', value)
    return value


def parse_stdout(text: str) -> dict[str, Any]:
    try:
        x = json.loads(text)
        return x if isinstance(x, dict) else {'ok': False, 'error': {'code': 'invalid_provider_output'}}
    except json.JSONDecodeError:
        return {'ok': False, 'error': {'code': 'invalid_provider_output', 'message': 'stdout is not valid JSON'}}


def all_text(value: Any) -> str:
    if isinstance(value, dict): return ' '.join(all_text(v) for v in value.values())
    if isinstance(value, list): return ' '.join(all_text(v) for v in value)
    return str(value)


def nested_detail(payload: dict[str, Any]) -> dict[str, Any]:
    err = payload.get('error')
    if not isinstance(err, dict): return {}
    detail = err.get('detail')
    if isinstance(detail, str):
        try:
            x = json.loads(detail)
            return x if isinstance(x, dict) else {}
        except json.JSONDecodeError: pass
    return {}


def http_status(payload: dict[str, Any], code: int | None) -> int | None:
    text = all_text(payload)
    match = re.search(r'\bHTTP\s*(\d{3})\b', text, re.I)
    if match: return int(match.group(1))
    match = re.search(r'\b(429|401|403|5\d\d)\b', text)
    if match: return int(match.group(1))
    return 200 if code == 0 and payload.get('ok') is True else None


def policy_refusal(payload: dict[str, Any], stderr: str, out: Path) -> bool:
    text = (all_text(payload) + ' ' + stderr).lower()
    evidence = ('image_generation_call' in text and 'failed' in text and not out.exists())
    return evidence and any(word in text for word in ('refusal', 'safety', 'content_policy', 'content policy', 'moderation'))


def import_parser() -> Any:
    spec = importlib.util.spec_from_file_location('q6_parser', PARSER)
    if spec is None or spec.loader is None: raise RuntimeError('cannot load Q6 retry parser')
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    return module


def verify_freeze(path: Path, expected: str) -> dict[str, Any]:
    actual = digest(path)
    sidecar = Path(str(path) + '.sha256')
    sidecar_ok = sidecar.exists() and sidecar.read_text(encoding='utf-8').split()[0] == actual
    value = json.loads(path.read_text(encoding='utf-8'))
    checks = {name: Path(name).is_file() and digest(Path(name)) == want for name, want in value.get('artifact_sha256', {}).items()}
    result = {'path': str(path), 'expected_sha256': expected, 'actual_sha256': actual, 'sidecar_match': sidecar_ok, 'bound_artifact_count': len(checks), 'all_bound_artifacts_match': all(checks.values())}
    if actual != expected or not sidecar_ok or not all(checks.values()): raise RuntimeError(f'freeze integrity failure: {result}')
    return result


def validator_snapshot(label: str) -> dict[str, Any]:
    proc = subprocess.run(['python3', str(VALIDATOR), '--json'], capture_output=True, text=True, timeout=240)
    payload = parse_stdout(proc.stdout)
    hits: dict[str, int] = {}
    counts: dict[str, int] = {}
    for name in ('media.csv', 'labels.csv', 'batches.csv', 'splits.csv'):
        p = ANNOTATIONS / name
        lines = p.read_text(encoding='utf-8').splitlines()
        counts[name] = max(0, len(lines) - 1)
        hits[name] = sum('p4d' in x.lower() or 'person-fallen-v2-p4d' in x.lower() for x in lines)
    result = {'captured_at': utc(), 'label': label, 'validator_returncode': proc.returncode, 'validator': payload, 'counts': counts, 'p4d_active_reference_hits': hits, 'p4d_active_reference_total': sum(hits.values())}
    atomic_json(PREFLIGHT / f'dataset_{label}.json', result)
    if proc.returncode != 0 or payload.get('status') != 'valid' or payload.get('error_count') != 0 or not payload.get('full_hash_check') or result['p4d_active_reference_total'] != 0:
        raise RuntimeError(f'dataset read-only gate failed: {result}')
    return result


def safe_profile(runtime: dict[str, Any]) -> str | None:
    auth = runtime.get('payload', {}).get('providers', {}).get('codex', {}).get('auth', {})
    account = auth.get('account_id')
    return hashlib.sha256(str(account).encode()).hexdigest() if account else None


def init() -> None:
    if EXEC.exists(): raise RuntimeError(f'execution revision already exists: {EXEC}')
    q5 = verify_freeze(Q5 / 'freeze/p4d_gr3q5_terminal_freeze.json', EXPECTED_Q5)
    prep = verify_freeze(PREP / 'freeze/p4d_gr3q6_preparation_freeze.json', EXPECTED_PREP)
    supp = verify_freeze(PREP / 'freeze/p4d_gr3q6_preparation_supplement_freeze.json', EXPECTED_SUPP)
    plan = csv_rows(PLAN); manifest = csv_rows(MANIFEST); adapter = {r['prompt_id']: r for r in csv_rows(ADAPTER_MANIFEST)}
    if digest(PLAN) != EXPECTED_PLAN or len(plan) != MAX_LOGICAL or len({r['prompt_id'] for r in plan}) != MAX_LOGICAL:
        raise RuntimeError('frozen Q6 plan mismatch')
    if [r['prompt_id'] for r in plan[:3]] != ['PF_P4D_NEG_CHAIR_G003_V03','PF_P4D_NEG_CHAIR_G003_V04','PF_P4D_NEG_CHAIR_G003_V05']:
        raise RuntimeError('first three plan rows mismatch')
    if Counter(r['role'] for r in plan) != Counter({'hard_negative':10,'positive':20,'ordinary_negative':3}) or Counter(r['planned_split'] for r in plan) != Counter({'NEW_DESIGN':18,'NEW_SCREEN':15}):
        raise RuntimeError('plan role/split mismatch')
    manifest_by = {r['prompt_id']: r for r in manifest}
    for row in plan:
        frozen = manifest_by.get(row['prompt_id']); ad = adapter.get(row['prompt_id'])
        if not frozen or not ad or row['render_prompt_sha256'] != ad['render_prompt_sha256'] or row['adapter_version'] != ADAPTER:
            raise RuntimeError(f'plan adapter binding mismatch: {row["prompt_id"]}')
        p = Path(frozen['original_prompt_path'])
        if not p.is_file() or digest(p) != frozen['prompt_sha256']:
            raise RuntimeError(f'semantic prompt integrity mismatch: {row["prompt_id"]}')
    EXEC.mkdir()
    for d in ('00_preflight','01_authorization','02_runner','03_ledger','04_raw_responses','05_checkpoints','06_partial_qa','07_generated_raw','08_final','freeze'):
        (EXEC / d).mkdir()
    runtime_proc = subprocess.run(['node', str(CLI), '--json', '--provider', 'codex', 'doctor'], capture_output=True, text=True, timeout=90)
    runtime = {'returncode': runtime_proc.returncode, 'payload': parse_stdout(runtime_proc.stdout), 'provider_requests': 0}
    if runtime_proc.returncode != 0 or runtime['payload'].get('ok') is not True or runtime['payload'].get('provider_selection', {}).get('resolved') != 'codex':
        raise RuntimeError(f'provider preflight failed: {runtime}')
    before = validator_snapshot('before')
    authorization = {'authorization_present': True, 'scope': 'P4D_GR3Q6 33-slot frozen plan', 'max_logical_invocations': MAX_LOGICAL, 'concurrency': 1, 'outer_retry': False, 'native_max_retries': 3, 'max_physical_attempt_lower_bound': MAX_PHYSICAL, 'max_unique_native_retry_events': MAX_RETRIES, 'max_confirmed_policy_refusals': MAX_REFUSALS, 'formal_ingest': False, 'c3': False, 'new_val': 0, 'val': 0, 'holdout_requests': 0, 'profile_safe_hash': safe_profile(runtime)}
    atomic_json(EXEC / '01_authorization/authorization.json', authorization)
    atomic_json(PREFLIGHT / 'parent_freeze_verification.json', {'q5':q5,'preparation':prep,'supplement':supp})
    atomic_json(PREFLIGHT / 'provider_runtime.json', runtime)
    shutil.copy2(PLAN, EXEC / '02_runner/q6_balanced_window_33_plan.csv')
    shutil.copy2(PARSER, EXEC / '02_runner/retry_event_parser_v2.py')
    shutil.copy2(Path(__file__), EXEC / '02_runner/p4d_gr3q6_authorized_execution.py')
    config = {'provider': PROVIDER, 'request_model': MODEL, 'generation_backend':'image_generation', 'adapter_version':ADAPTER, 'native_size':NATIVE_SIZE, 'quality':QUALITY, 'format':'png', 'final_size':list(FINAL_SIZE), 'concurrency':1, 'outer_retry':False, 'native_max_retries':3, 'semantic_frozen_prompt_changed':False, 'provider_render_prompt_changed':True, 'q6_plan_sha256':digest(PLAN), 'runner_sha256':digest(Path(__file__)), 'parser_sha256':digest(PARSER)}
    atomic_json(EXEC / '02_runner/run_config.json', config)
    db = sqlite3.connect(DB)
    try:
        db.execute('PRAGMA journal_mode=WAL'); db.execute('PRAGMA synchronous=FULL')
        db.execute('CREATE TABLE meta(key TEXT PRIMARY KEY, value TEXT NOT NULL)')
        db.execute('''CREATE TABLE slots(q6_order INTEGER PRIMARY KEY,prompt_id TEXT UNIQUE NOT NULL,group_id TEXT NOT NULL,variant_id TEXT NOT NULL,role TEXT NOT NULL,taxonomy TEXT NOT NULL,planned_split TEXT NOT NULL,render_prompt_sha256 TEXT NOT NULL,state TEXT NOT NULL,started_at TEXT,finished_at TEXT,http_status INTEGER,error_class TEXT,error_message TEXT,raw_path TEXT,final_path TEXT,raw_sha256 TEXT,final_sha256 TEXT,native_width INTEGER,native_height INTEGER,final_width INTEGER,final_height INTEGER,crop_box TEXT,latency_seconds REAL,native_retry_events INTEGER NOT NULL DEFAULT 0,request_started_events INTEGER NOT NULL DEFAULT 0,physical_attempt_lower_bound INTEGER NOT NULL DEFAULT 0,profile_safe_hash TEXT)''')
        db.execute('CREATE TABLE events(id INTEGER PRIMARY KEY AUTOINCREMENT,prompt_id TEXT,event_type TEXT,payload_json TEXT,captured_at TEXT)')
        db.executemany('INSERT INTO slots(q6_order,prompt_id,group_id,variant_id,role,taxonomy,planned_split,render_prompt_sha256,state) VALUES(?,?,?,?,?,?,?,?,?)', [(int(r['q6_order']),r['prompt_id'],r['group_id'],r['variant_id'],r['role'],r['taxonomy'],r['planned_split'],r['render_prompt_sha256'],'NOT_STARTED') for r in plan])
        for key,val in {'stage':'P4D_GR3Q6_BALANCED_QUOTA_RESET_RECOVERY','authorization':'true','plan_sha256':digest(PLAN),'starting_success':'142','starting_outstanding':'298','provider_requests':'0'}.items(): db.execute('INSERT INTO meta VALUES(?,?)',(key,val))
        db.commit(); db.execute('PRAGMA wal_checkpoint(FULL)')
    finally: db.close()
    atomic_json(CHECK / 'ready.json', {'status':'READY_FOR_AUTHORIZED_EXECUTION','provider_requests':0,'plan_rows':33,'starting_success':142,'starting_outstanding':298,'dataset_before':before})
    print(json.dumps({'status':'READY_FOR_AUTHORIZED_EXECUTION','execution_revision':str(EXEC),'plan_sha256':digest(PLAN)},sort_keys=True))


def convert(raw: Path, final: Path) -> dict[str, Any]:
    with Image.open(raw) as im: im.verify()
    with Image.open(raw) as im:
        im.load(); width,height=im.size; rgb=im.convert('RGB')
        target=FINAL_SIZE[0]/FINAL_SIZE[1]; ratio=width/height
        if ratio > target:
            cw=round(height*target); left=(width-cw)//2; box=(left,0,left+cw,height)
        elif ratio < target:
            ch=round(width/target); top=(height-ch)//2; box=(0,top,width,top+ch)
        else: box=(0,0,width,height)
        resample=getattr(getattr(Image,'Resampling',Image),'LANCZOS')
        img=rgb.crop(box).resize(FINAL_SIZE,resample)
        temp=final.with_name(final.name+'.tmp'); img.save(temp,'PNG')
    with Image.open(temp) as im: im.verify()
    with Image.open(temp) as im: im.load(); fw,fh=im.size
    if (fw,fh) != FINAL_SIZE: raise ValueError(f'final dimensions {(fw,fh)}')
    os.replace(temp,final)
    return {'native_width':width,'native_height':height,'final_width':fw,'final_height':fh,'crop_box':list(box),'resize_method':'Pillow_LANCZOS'}


def previous_hashes() -> tuple[set[str],set[str]]:
    # Existing lineage only; the new Q6 execution root is excluded by construction.
    raw_hashes:set[str]=set(); gr1_hashes:set[str]=set()
    for p in GR3.rglob('*.png'):
        if EXEC in p.parents: continue
        try: raw_hashes.add(digest(p))
        except OSError: pass
    gr1 = ROOT / '08_p4d_new_hard_negative_dev_revision/02_generation/gr1_generation_resume'
    if gr1.exists():
        for p in gr1.rglob('*.png'):
            try: gr1_hashes.add(digest(p))
            except OSError: pass
    return raw_hashes, gr1_hashes


def update_event(db: sqlite3.Connection, prompt_id: str, kind: str, payload: Any) -> None:
    db.execute('INSERT INTO events(prompt_id,event_type,payload_json,captured_at) VALUES(?,?,?,?)',(prompt_id,kind,json.dumps(payload,ensure_ascii=False,sort_keys=True),utc()))


def terminal(stop_reason: str) -> dict[str, Any]:
    db=sqlite3.connect(DB); db.row_factory=sqlite3.Row
    try:
        states=Counter(dict(r) for r in [])
        slots=[dict(r) for r in db.execute('SELECT * FROM slots ORDER BY q6_order')]
        counts=Counter(r['state'] for r in slots)
        success=[r for r in slots if r['state']=='SUCCESS']
        retries=sum(r['native_retry_events'] for r in slots); physical=sum(r['physical_attempt_lower_bound'] for r in slots)
        http=Counter(str(r['http_status']) for r in slots if r['http_status'] is not None)
        db.execute('PRAGMA wal_checkpoint(FULL)'); db.commit()
    finally: db.close()
    prior=csv_rows(PREP/'01_inventory/current_verified_success_142.csv')
    plan_by={r['prompt_id']:r for r in csv_rows(PLAN)}
    all_success=[{'prompt_id':r['prompt_id'],'role':r['role'],'taxonomy':r['taxonomy'],'planned_split':r['planned_split'],'source':'Q6_EXECUTION','raw_path':r['raw_path'],'final_path':r['final_path'],'raw_sha256':r['raw_sha256'],'final_sha256':r['final_sha256'],'profile_safe_hash':r['profile_safe_hash'],'adapter_version':ADAPTER} for r in success]
    combined=[{'prompt_id':r['prompt_id'],'role':r['role'],'taxonomy':r['taxonomy'],'planned_split':r['planned_split'],'source':'PRE_Q6_VERIFIED'} for r in prior]+all_success
    frozen={r['prompt_id'] for r in csv_rows(MANIFEST)}; ids={r['prompt_id'] for r in combined}; outstanding=frozen-ids
    if len(ids)!=len(combined) or ids & outstanding or ids|outstanding != frozen: raise RuntimeError('inventory partition failed')
    with (QA/'current_verified_success.csv').open('w',encoding='utf-8',newline='') as f:
        fields=['prompt_id','role','taxonomy','planned_split','source','raw_path','final_path','raw_sha256','final_sha256','profile_safe_hash','adapter_version']; w=csv.DictWriter(f,fieldnames=fields,extrasaction='ignore');w.writeheader();w.writerows(combined)
    with (QA/'current_outstanding.csv').open('w',encoding='utf-8',newline='') as f:
        fields=['prompt_id','role','taxonomy','planned_split','execution_state'];w=csv.DictWriter(f,fieldnames=fields);w.writeheader()
        for pid in sorted(outstanding):
            m=plan_by.get(pid) or next(x for x in csv_rows(MANIFEST) if x['prompt_id']==pid)
            slot=next((x for x in slots if x['prompt_id']==pid),None)
            w.writerow({'prompt_id':pid,'role':m.get('role',m.get('target_role')),'taxonomy':m['taxonomy'],'planned_split':m.get('planned_split',m.get('planned_internal_split')),'execution_state':slot['state'] if slot else 'NOT_SCHEDULED'})
    raw_hashes, gr1_hashes = previous_hashes(); duplicate_hits=sum(r['raw_sha256'] in raw_hashes or r['final_sha256'] in raw_hashes for r in success); gr1_hits=sum(r['raw_sha256'] in gr1_hashes or r['final_sha256'] in gr1_hashes for r in success)
    qa={'partial_mechanical_qa':'PASS' if not any(r['state']=='MECHANICAL_QA_FAILED' for r in slots) else 'FAIL','new_raw_count':len(success),'new_final_count':len(success),'pillow_failures':sum(r['state']=='MECHANICAL_QA_FAILED' for r in slots),'dimension_failures':0,'exact_duplicate_hits':duplicate_hits,'gr1_sha_hits':gr1_hits,'full_440_qa':'NOT_REACHED' if len(ids)<440 else 'REACHED','P4D_IMAGES_ACCEPTED':0,'current_verified_success':len(ids),'current_outstanding':len(outstanding),'role_distribution':dict(Counter(r['role'] for r in combined)),'split_distribution':dict(Counter(r['planned_split'] for r in combined)),'taxonomy_distribution':dict(Counter(r['taxonomy'] for r in combined))}
    atomic_json(QA/'partial_qa.json',qa)
    after=validator_snapshot('after')
    summary={'stage':'P4D_GR3Q6_BALANCED_QUOTA_RESET_RECOVERY','status':stop_reason,'stop_reason':stop_reason,'starting_verified_success':142,'starting_outstanding':298,'q6_plan_sha256':digest(PLAN),'q6_plan_rows':33,'provider':PROVIDER,'request_model':MODEL,'generation_backend':'image_generation','runtime_version':json.loads((PREFLIGHT/'provider_runtime.json').read_text())['payload'].get('payload',{}).get('version'),'adapter_version':ADAPTER,'logical_invocations':sum(r['state']!='NOT_STARTED' for r in slots),'success':counts['SUCCESS'],'policy_refusals':counts['CONTENT_POLICY_REFUSAL_CONFIRMED'],'other_failures':counts['FAILED_CONFIRMED']+counts['MECHANICAL_QA_FAILED'],'completion_unknown':counts['COMPLETION_UNKNOWN'],'unique_native_retry_events':retries,'observed_physical_attempt_lower_bound':physical,'http200':http['200'],'http429':http['429'],'http401':http['401'],'http403':http['403'],'http5xx':sum(v for k,v in http.items() if k.startswith('5')),'timeouts':counts['COMPLETION_UNKNOWN'],'current_verified_success':len(ids),'current_outstanding':len(outstanding),'new_raw_count':len(success),'new_final_count':len(success),'qa':qa,'formal_ingest':False,'media_added':0,'labels_added':0,'c3':False,'new_val':0,'val':0,'holdout_requests':0,'holdout_consumed':False,'dataset_after':after}
    atomic_json(CHECK/'terminal_summary.json',summary)
    artifacts=[DB,EXEC/'01_authorization/authorization.json',EXEC/'02_runner/q6_balanced_window_33_plan.csv',EXEC/'02_runner/retry_event_parser_v2.py',EXEC/'02_runner/p4d_gr3q6_authorized_execution.py',EXEC/'02_runner/run_config.json',PREFLIGHT/'parent_freeze_verification.json',PREFLIGHT/'provider_runtime.json',PREFLIGHT/'dataset_before.json',PREFLIGHT/'dataset_after.json',CHECK/'ready.json',CHECK/'global_stop.json',CHECK/'terminal_summary.json',QA/'partial_qa.json',QA/'current_verified_success.csv',QA/'current_outstanding.csv',*sorted(RAW.glob('*.json')),*sorted(RAW_IMAGES.glob('*.png')),*sorted(FINAL.glob('*.png'))]
    freeze={'stage':summary['stage'],'terminal':summary,'artifact_sha256':{str(p):digest(p) for p in artifacts}}
    f=EXEC/'freeze/p4d_gr3q6_execution_terminal_freeze.json';atomic_json(f,freeze);d=digest(f);Path(str(f)+'.sha256').write_text(f'{d}  {f.name}\n',encoding='utf-8')
    verify={'freeze_sha256':d,'sidecar_match':Path(str(f)+'.sha256').read_text().split()[0]==d,'bound_artifact_count':len(artifacts),'all_bound_artifacts_match':all(digest(Path(p))==h for p,h in freeze['artifact_sha256'].items())}
    atomic_json(CHECK/'terminal_freeze_verification.json',verify)
    return summary | {'terminal_freeze_sha256':d,'terminal_freeze_verification':verify}


def run() -> None:
    if not EXEC.exists() or (EXEC/'freeze/p4d_gr3q6_execution_terminal_freeze.json').exists(): raise RuntimeError('missing init or terminal freeze already exists')
    lock=LOCK.open('w')
    try:
        try: fcntl.flock(lock.fileno(), fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError: raise RuntimeError('BLOCKED_CONCURRENT_RUNNER')
        process_lines = subprocess.run(['ps', '-eo', 'pid=,args='], capture_output=True, text=True, check=True).stdout.splitlines()
        external = []
        for line in process_lines:
            fields = line.strip().split(None, 1)
            if len(fields) != 2 or 'p4d_gr3q6_authorized_execution.py' not in fields[1]:
                continue
            pid = int(fields[0])
            # The shell which launched this runner contains the command text;
            # it is not a second active generation runner.
            if pid not in {os.getpid(), os.getppid()}:
                external.append(line)
        if external: raise RuntimeError(f'BLOCKED_CONCURRENT_RUNNER: {external}')
        parser=import_parser(); plan=csv_rows(EXEC/'02_runner/q6_balanced_window_33_plan.csv'); renders={r['prompt_id']:r for r in csv_rows(ADAPTER_MANIFEST)}
        db=sqlite3.connect(DB);db.row_factory=sqlite3.Row
        stop=None
        try:
            for row in plan:
                if stop: break
                slot=dict(db.execute('SELECT * FROM slots WHERE prompt_id=?',(row['prompt_id'],)).fetchone())
                if slot['state']!='NOT_STARTED': raise RuntimeError(f'non-pristine execution slot: {slot["prompt_id"]}={slot["state"]}')
                db.execute("UPDATE slots SET state='STARTED',started_at=? WHERE prompt_id=?",(utc(),row['prompt_id']));update_event(db,row['prompt_id'],'STARTED',{'q6_order':row['q6_order']});db.commit()
                request={'model':MODEL,'provider':PROVIDER,'generation_backend':'image_generation','size':NATIVE_SIZE,'quality':QUALITY,'format':'png','adapter_version':ADAPTER,'render_prompt_sha256':row['render_prompt_sha256'],'outer_retry':False,'native_max_retries':3}
                append_jsonl(EXEC/'request_log.jsonl',{'timestamp':utc(),'prompt_id':row['prompt_id'],'split':row['planned_split'],'request':request})
                raw_path=RAW_IMAGES/f"{row['prompt_id']}.png"; final_path=FINAL/f"{row['prompt_id']}.png"; cmd=['node',str(CLI),'--json','--json-events','--provider','codex','images','generate','--model',MODEL,'--prompt',renders[row['prompt_id']]['render_prompt'],'--out',str(raw_path),'--format','png','--size',NATIVE_SIZE,'--quality',QUALITY]
                started=time.monotonic(); proc=None; timeout=False
                try: proc=subprocess.run(cmd,capture_output=True,text=True,timeout=1800)
                except subprocess.TimeoutExpired as e: timeout=True; stdout=e.stdout or ''; stderr=e.stderr or ''
                else: stdout=proc.stdout; stderr=proc.stderr
                if isinstance(stdout,bytes): stdout=stdout.decode('utf-8','replace')
                if isinstance(stderr,bytes): stderr=stderr.decode('utf-8','replace')
                payload=parse_stdout(stdout); telemetry=parser.telemetry_from_events(parser.parse_json_events(stderr)); hs=http_status(payload,proc.returncode if proc else None); latency=time.monotonic()-started
                ok=bool(proc and proc.returncode==0 and payload.get('ok') is True and raw_path.is_file() and raw_path.stat().st_size>0)
                state='SUCCESS'; error_class='NONE'; error_message=''
                if timeout: state='COMPLETION_UNKNOWN';error_class='TIMEOUT_COMPLETION_UNKNOWN';error_message='subprocess timeout'
                elif ok:
                    try: details=convert(raw_path,final_path)
                    except Exception as exc: state='MECHANICAL_QA_FAILED';error_class='MECHANICAL_QA_FAILED';error_message=str(exc);details={}
                elif policy_refusal(payload,stderr,raw_path): state='CONTENT_POLICY_REFUSAL_CONFIRMED';error_class=state;details={}
                else: state='FAILED_CONFIRMED';error_class='FAILED_CONFIRMED_NO_IMAGE_UNCLASSIFIED';error_message=all_text(payload)[:500];details={}
                raw={'prompt_id':row['prompt_id'],'command_config':request,'returncode':proc.returncode if proc else None,'http_status':hs,'outer_json':payload,'stderr_redacted':scrub(stderr),'state':state,'failure_class':error_class,'latency_seconds':latency,'telemetry':telemetry,'adapter_version':ADAPTER,'render_prompt_sha256':row['render_prompt_sha256'],'timeout':timeout}
                atomic_json(RAW/f"{row['prompt_id']}.json",raw);append_jsonl(EXEC/'raw_responses.jsonl',raw)
                db.execute('''UPDATE slots SET state=?,finished_at=?,http_status=?,error_class=?,error_message=?,raw_path=?,final_path=?,raw_sha256=?,final_sha256=?,native_width=?,native_height=?,final_width=?,final_height=?,crop_box=?,latency_seconds=?,native_retry_events=?,request_started_events=?,physical_attempt_lower_bound=?,profile_safe_hash=? WHERE prompt_id=?''',(state,utc(),hs,error_class,error_message,str(raw_path) if raw_path.exists() else None,str(final_path) if final_path.exists() else None,digest(raw_path) if raw_path.exists() else None,digest(final_path) if final_path.exists() else None,details.get('native_width'),details.get('native_height'),details.get('final_width'),details.get('final_height'),json.dumps(details.get('crop_box')) if details else None,latency,telemetry['unique_native_retry_events'],telemetry['request_started_events'],telemetry['physical_attempt_lower_bound'],json.loads((EXEC/'01_authorization/authorization.json').read_text())['profile_safe_hash'],row['prompt_id']))
                update_event(db,row['prompt_id'],'FINAL',{'state':state,'http_status':hs,'telemetry':telemetry});db.commit()
                cumulative=dict(db.execute("SELECT COALESCE(SUM(native_retry_events),0) AS retries,COALESCE(SUM(physical_attempt_lower_bound),0) AS physical,COALESCE(SUM(state='CONTENT_POLICY_REFUSAL_CONFIRMED'),0) AS refusals,COALESCE(SUM(state!='NOT_STARTED'),0) AS logical FROM slots").fetchone())
                print(json.dumps({'prompt_id':row['prompt_id'],'state':state,'http_status':hs,'logical':cumulative['logical'],'retries':cumulative['retries'],'physical':cumulative['physical']},sort_keys=True),flush=True)
                if hs==429: stop='STOPPED_PROVIDER_429'
                elif hs in (401,403) or (hs and 500<=hs<=599): stop=f'STOPPED_PROVIDER_HTTP{hs}'
                elif state=='COMPLETION_UNKNOWN': stop='STOPPED_COMPLETION_UNKNOWN'
                elif state in ('FAILED_CONFIRMED','MECHANICAL_QA_FAILED'): stop='STOPPED_UNCLASSIFIED_PROVIDER_FAILURE' if state=='FAILED_CONFIRMED' else 'STOPPED_MECHANICAL_QA_FAILURE'
                elif cumulative['retries']>=MAX_RETRIES: stop='NATIVE_RETRY_GUARD'
                elif cumulative['physical']>=MAX_PHYSICAL: stop='PHYSICAL_ATTEMPT_GUARD'
                elif cumulative['refusals']>=MAX_REFUSALS: stop='POLICY_REFUSAL_PRESSURE_GUARD'
                elif cumulative['logical']>=MAX_LOGICAL: stop='WINDOW_CAP_REACHED_SUCCESS'
            if not stop: stop='STOPPED_UNEXPECTED_SCHEDULER_STATE'
            atomic_json(CHECK/'global_stop.json',{'global_stop':True,'stop_reason':stop,'stopped_at':utc()})
        finally: db.close()
        summary=terminal(stop);print(json.dumps(summary,sort_keys=True),flush=True)
    finally:
        lock.close()


if __name__ == '__main__':
    ap=argparse.ArgumentParser();ap.add_argument('command',choices=('init','run'));a=ap.parse_args();init() if a.command=='init' else run()
