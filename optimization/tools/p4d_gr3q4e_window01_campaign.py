#!/usr/bin/env python3
"""Authorized, fail-closed P4D GR3Q4E Window01 image-generation campaign.

The runner owns only its new revision.  It never alters the preceding
zero-request freeze, the formal dataset, shared splits, or production code.
There is one durable STARTED record before every provider call; a timeout or
interrupted STARTED record is completion-unknown and is never resent here.
"""
from __future__ import annotations

import argparse
import csv
import fcntl
import hashlib
import json
import os
import re
import sqlite3
import subprocess
import sys
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from PIL import Image

ROOT = Path("/home/yanbo/net_vlm_person_fallen_v2_optimization")
P4D = ROOT / "08_p4d_new_hard_negative_dev_revision"
GR3 = P4D / "02_generation/gr3_fullregen"
PARENT = GR3 / "06_execution/quota_campaign_window_20260828_03"
ZERO = GR3 / "06_execution/quota_campaign_window_01_execution_20260830_01"
EXEC = GR3 / "06_execution/quota_campaign_window_01_authorized_20260830_05"
MANIFEST = GR3 / "03_fullregen_plan/full_regen_prompt_manifest.csv"
PLAN = PARENT / "02_order/first_window_68_plan.csv"
PARENT_FREEZE = PARENT / "freeze/p4d_gr3q4_terminal_freeze.json"
ZERO_FREEZE = ZERO / "freeze/p4d_gr3q4e_window01_terminal_freeze.json"
VALIDATOR = Path("/home/yanbo/net_vlm_xunjian_dataset/tools/validate_dataset.py")
ANNOTATIONS = Path("/home/yanbo/net_vlm_xunjian_dataset/01_annotations")
CLI = Path("/home/yanbo/.codex/skills/gpt-image-2-skill/scripts/gpt_image_2_skill.cjs")
BINARY = Path("/home/yanbo/.cache/gpt-image-2-skill/0.7.3/x86_64-unknown-linux-gnu/gpt-image-2-skill")

EXPECTED = {
    "manifest": "5f7afbc010a0028497ec0210e75dc28cc79212fbc114cbf4741ee0bc4ce361c4",
    "plan": "2d1c22a111325be77cc35949563884800925a7ce7e99272d4910e15022fd8bfd",
    "parent_freeze": "8d0d6b6ee61bde4da3bc283997f1d6311e1cd558dd6d687b148f51e87716e5c2",
    "zero_freeze": "86406cff4dc2409401d015ee9a1b117a9e3dd8be6211ed1fd3bc871a9cebba15",
    "wrapper": "f01c85e448a078c508d015e2c0ac5208b12a9f126ce83e47da11fce542b440fe",
    "binary": "1ac830fed5349f1c1a1c2fd1a4280b487a2d75962d22d9fbd4e4b2451ab208ba",
    "profile_a": "ab7f2704e5b70b62ccfd48b241b649716e6ddd6cb9a1bfe14d992df646dcaffe",
    "profile_b": "d80e86e6d2324b14d5b7a37821b1f42684b62f80c69e03350c9b0c3ae0f7c190",
}
WINDOW_CAP, PHYSICAL_CAP, RETRY_CAP = 68, 80, 5
MODEL, PROVIDER, NATIVE_SIZE, QUALITY, FINAL_SIZE = "gpt-5.4", "codex", "1536x1024", "medium", (1920, 1080)
AUTH_TEXT = "P4D_GR3Q4E Window01 explicit authorization supplied by user on 2026-08-30; preserve 102, process frozen 338 outstanding, execute frozen first 68 only, concurrency=1, outer_retry=false, native max_retries=3 accepted, stop on unsafe completion or caps; no ingest/C3/P2/P3/P4/VAL/HOLDOUT/production."

PRE, AUTH, LEDGER, RAW, CHECK, QA, FREEZE = (EXEC / "00_preflight", EXEC / "01_authorization", EXEC / "03_ledger", EXEC / "04_raw_responses", EXEC / "05_checkpoints", EXEC / "06_partial_qa", EXEC / "freeze")
RAW_OUT, FINAL_OUT, STAGE = EXEC / "07_generated_raw", EXEC / "08_final", EXEC / "_staging"
DB, LEDGER_CSV, REQUEST_LOG, RAW_LOG = LEDGER / "window01.sqlite3", LEDGER / "window01_ledger.csv", EXEC / "request_log.jsonl", EXEC / "raw_responses.jsonl"
STOP, SUMMARY, LOCK = CHECK / "global_stop.json", CHECK / "terminal_summary.json", EXEC / ".runner.lock"

def now() -> str: return datetime.now(timezone.utc).isoformat()
def digest(path: Path) -> str | None:
    if not path.is_file(): return None
    h = hashlib.sha256()
    with path.open("rb") as f:
        for b in iter(lambda: f.read(1024 * 1024), b""): h.update(b)
    return h.hexdigest()
def obj_digest(x: Any) -> str: return hashlib.sha256(json.dumps(x, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode()).hexdigest()
def read_json(path: Path, default: Any = None) -> Any:
    try: return json.loads(path.read_text(encoding="utf-8"))
    except Exception: return default
def rows(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as f: return list(csv.DictReader(f))
def write_json(path: Path, x: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True); path.write_text(json.dumps(x, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
def write_csv(path: Path, fields: list[str], xs: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields, lineterminator="\n", extrasaction="ignore"); w.writeheader(); w.writerows(xs); f.flush(); os.fsync(f.fileno())
def append_jsonl(path: Path, x: Any) -> None:
    with path.open("a", encoding="utf-8") as f: f.write(json.dumps(x, ensure_ascii=False, sort_keys=True)+"\n"); f.flush(); os.fsync(f.fileno())
def redact(s: str) -> str:
    return re.sub(r"(?i)(authorization\s*:\s*bearer\s+)[^\s\"']+", r"\1<REDACTED>", s)
def parse_json(text: str) -> dict[str, Any]:
    try:
        x=json.loads(text); return x if isinstance(x,dict) else {"ok":False,"error":{"code":"invalid_provider_output"}}
    except Exception:
        # wrapper stdout is expected to be one JSON object; do not trust fragments.
        return {"ok":False,"error":{"code":"invalid_provider_output","message":"stdout was not one JSON object"}}
def nested(x: Any, keys: set[str]) -> list[Any]:
    out=[]
    if isinstance(x,dict):
        for k,v in x.items():
            if k in keys: out.append(v)
            out.extend(nested(v,keys))
    elif isinstance(x,list):
        for v in x: out.extend(nested(v,keys))
    return out
def http_status(payload: dict[str,Any], rc: int | None) -> str:
    for v in nested(payload,{"http_status","status","status_code"}):
        s=str(v)
        if re.fullmatch(r"[1-5]\d\d",s): return s
    code=str(((payload.get("error") or {}).get("code") or ""))
    m=re.search(r"\b(401|403|429|5\d\d)\b",code)
    if m:return m.group(1)
    return "200" if rc == 0 and payload.get("ok") is True else "UNKNOWN"
def error_info(payload:dict[str,Any])->tuple[str,str]:
    e=payload.get("error") or {}; return str(e.get("code") or ""),redact(str(e.get("message") or ""))
def request_id(payload:dict[str,Any])->str|None:
    vals=nested(payload,{"request_id","id","response_id"})
    return next((str(x) for x in vals if isinstance(x,(str,int)) and str(x)),None)
def retries(stderr:str)->int:return len(re.findall(r'"type"\s*:\s*"retry_scheduled"',stderr))
def image_ok(p:Path)->tuple[bool,tuple[int,int]|None,str]:
    try:
        with Image.open(p) as im: im.verify()
        with Image.open(p) as im: im.load(); return True,im.size,""
    except Exception as e:return False,None,redact(str(e))
def convert(raw:Path, final:Path)->dict[str,Any]:
    ok,size,err=image_ok(raw)
    if not ok or not size: raise ValueError(f"raw_image_invalid:{err}")
    with Image.open(raw) as im:
        rgb=im.convert("RGB"); w,h=rgb.size; target=FINAL_SIZE[0]/FINAL_SIZE[1]
        if w/h > target:
            cw=round(h*target); left=(w-cw)//2; box=(left,0,left+cw,h)
        elif w/h < target:
            ch=round(w/target); top=(h-ch)//2; box=(0,top,w,top+ch)
        else: box=(0,0,w,h)
        resampling=getattr(getattr(Image,"Resampling",Image),"LANCZOS")
        rgb.crop(box).resize(FINAL_SIZE,resampling).save(final,format="PNG")
    ok2,size2,err2=image_ok(final)
    if not ok2 or size2 != FINAL_SIZE: raise ValueError(f"final_image_invalid:{err2}:{size2}")
    return {"native_width":w,"native_height":h,"final_width":1920,"final_height":1080,"crop_box":list(box),"resize_method":"Pillow_LANCZOS"}

def validator(label:str)->dict[str,Any]:
    p=subprocess.run(["python3",str(VALIDATOR),"--json"],capture_output=True,text=True,timeout=300,check=False)
    x=parse_json(p.stdout); result={"captured_at":now(),"label":label,"returncode":p.returncode,"validator":x,"status":x.get("status"),"error_count":x.get("error_count"),"warning_count":x.get("warning_count"),"full_hash_check":x.get("full_hash_check")}
    write_json(PRE/f"dataset_validator_{label}.json",result); return result
def annotations()->dict[str,Any]:
    hs={n:digest(ANNOTATIONS/n) for n in ("media.csv","labels.csv","batches.csv","splits.csv")}
    counts={n:max(0,len((ANNOTATIONS/n).read_text(encoding="utf-8").splitlines())-1) for n in hs}
    return {"sha256":hs,"counts":counts}
def cli_audit(label:str,args:list[str])->dict[str,Any]:
    p=subprocess.run(["node",str(CLI),"--json","--provider","codex",*args],capture_output=True,text=True,timeout=180,check=False)
    x=parse_json(p.stdout); r={"captured_at":now(),"label":label,"command":["node","<gpt-image-2-skill>","--json","--provider","codex",*args],"returncode":p.returncode,"payload":x,"stderr_redacted":redact(p.stderr),"provider_requests":0}
    write_json(PRE/f"{label}.json",r); return x
def runtime()->dict[str,Any]:
    config=cli_audit("config_inspect",["config","inspect"]); doctor=cli_audit("doctor",["doctor"]); auth=cli_audit("auth_inspect",["auth","inspect"])
    defaults=doctor.get("defaults") or {}; sel=doctor.get("provider_selection") or {}; codex=(doctor.get("providers") or {}).get("codex") or {}; endpoint=codex.get("endpoint") or {}; ca=(auth.get("providers") or {}).get("codex") or {}
    # auth inspect uses these stable, non-secret identity keys; never persist them.
    account=str(ca.get("account_id") or ""); user=str(ca.get("chatgpt_user_id") or ""); profile=hashlib.sha256(f"account={account}|user={user}".encode()).hexdigest() if account or user else None
    stratum="PROFILE_A_RESTORED" if profile==EXPECTED["profile_a"] else "PROFILE_B_EXISTING_LINEAGE_POLICY" if profile==EXPECTED["profile_b"] else "UNRECOGNIZED"
    r={"captured_at":now(),"provider":sel.get("resolved"),"request_model":defaults.get("codex_model"),"generation_backend":"image_generation","runtime_version":doctor.get("version"),"wrapper_sha256":digest(CLI),"binary_sha256":digest(BINARY),"native_max_retries":(doctor.get("retry_policy") or {}).get("max_retries"),"outer_retry":False,"auth_ready":bool(ca.get("ready")),"endpoint_reachable":bool(endpoint.get("reachable")),"tls_ok":bool(endpoint.get("tls_ok")),"session_ready":bool(ca.get("ready") and endpoint.get("reachable") and endpoint.get("tls_ok")),"profile_fingerprint_safe_hash":profile,"active_profile_stratum":stratum,"profile_policy":"known_profile_A_or_B_only","raw_profile_values_persisted":False,"default_provider_note":(config.get("config") or {}).get("default_provider")}
    checks={"provider":r["provider"]==PROVIDER,"model":r["request_model"]==MODEL,"runtime":r["runtime_version"]=="0.7.3","wrapper":r["wrapper_sha256"]==EXPECTED["wrapper"],"binary":r["binary_sha256"]==EXPECTED["binary"],"known_profile_lineage_policy":r["profile_fingerprint_safe_hash"] in (EXPECTED["profile_a"],EXPECTED["profile_b"]),"retries":r["native_max_retries"]==3,"outer_retry":r["outer_retry"] is False,"session":r["session_ready"] is True}
    r["checks"],r["all_pass"]=checks,all(checks.values()); write_json(PRE/"provider_runtime_audit.json",r); return r

def init() -> None:
    if EXEC.exists(): raise RuntimeError(f"refusing existing revision:{EXEC}")
    for p in (PRE,AUTH,LEDGER,RAW,CHECK,QA,FREEZE,RAW_OUT,FINAL_OUT,STAGE/"raw",STAGE/"final"):p.mkdir(parents=True,exist_ok=False)
    before=validator("before"); snap=annotations(); manifest=rows(MANIFEST); plan=rows(PLAN)
    parent_sidecar=read_json(PARENT_FREEZE,{}) or {}; zero_sidecar=read_json(ZERO_FREEZE,{}) or {}
    checks={"parent_freeze":digest(PARENT_FREEZE)==EXPECTED["parent_freeze"],"parent_freeze_status":parent_sidecar.get("status")=="WAITING_FOR_PROVIDER_QUOTA_RESET","zero_freeze":digest(ZERO_FREEZE)==EXPECTED["zero_freeze"],"zero_freeze_status":zero_sidecar.get("status")=="AWAITING_CAMPAIGN_AUTHORIZATION" and zero_sidecar.get("starting_verified_success")==102 and zero_sidecar.get("starting_outstanding")==338 and zero_sidecar.get("provider_requests")==0,"manifest":digest(MANIFEST)==EXPECTED["manifest"],"plan":digest(PLAN)==EXPECTED["plan"],"manifest_rows":len(manifest)==440,"plan_rows":len(plan)==68,"first_slot":plan[0].get("prompt_id")=="PF_P4D_HN_KNEEL_G009_V03","unique_plan":len({x.get("prompt_id") for x in plan})==68,"validator":before.get("status")=="valid" and before.get("error_count")==0 and before.get("full_hash_check") is True}
    m={x["prompt_id"]:x for x in manifest}
    for x in plan:
        q=m.get(x["prompt_id"]); checks[f"prompt_{x['window_planned_order']}"]=bool(q and digest(Path(q["original_prompt_path"]))==q["prompt_sha256"])
    rt=runtime(); checks["runtime"]=rt["all_pass"]
    att={"stage":"P4D_GR3Q4E_WINDOW01","authorized":True,"authorization_text_sha256":hashlib.sha256(AUTH_TEXT.encode()).hexdigest(),"scope":{"preserve_verified_generation_lineage":102,"outstanding_frozen_slots":338,"window_01_slots":68,"first_slot":"PF_P4D_HN_KNEEL_G009_V03","concurrency":1,"outer_retry":False,"native_max_retries":3,"physical_lower_bound_cap":80,"native_retry_event_cap":5,"no_formal_ingest":True,"no_c3":True,"no_val":True,"no_holdout":True,"no_production":True}}
    write_json(AUTH/"campaign_authorization_attestation.json",att); write_json(PRE/"preflight_gate.json",{"captured_at":now(),"checks":checks,"all_pass":all(checks.values()),"provider_requests":0})
    if not all(checks.values()): raise RuntimeError(f"preflight_failed:{[k for k,v in checks.items() if not v]}")
    (EXEC/"02_plan").mkdir(); (EXEC/"02_plan/first_window_68_plan.csv").write_bytes(PLAN.read_bytes())
    con=db();
    try:
        con.execute("CREATE TABLE slots(prompt_id TEXT PRIMARY KEY, ord INTEGER UNIQUE NOT NULL, group_id TEXT NOT NULL, variant_id TEXT NOT NULL, role TEXT NOT NULL, taxonomy TEXT NOT NULL, planned_split TEXT NOT NULL, prompt_path TEXT NOT NULL, prompt_sha256 TEXT NOT NULL, parent_state TEXT NOT NULL, state TEXT NOT NULL, invocation_count INTEGER NOT NULL DEFAULT 0, request_id TEXT, provider_request_id TEXT, started_at TEXT, finished_at TEXT, http_status TEXT, error_code TEXT, raw_path TEXT, final_path TEXT, raw_sha256 TEXT, final_sha256 TEXT, latency_seconds REAL, native_retry_count INTEGER, response_path TEXT, qa_json TEXT)")
        con.execute("CREATE TABLE events(event_id INTEGER PRIMARY KEY AUTOINCREMENT,prompt_id TEXT,event_type TEXT NOT NULL,payload_json TEXT NOT NULL,captured_at TEXT NOT NULL)")
        ledger=[]
        for x in plan:
            q=m[x["prompt_id"]]; record={**x,"prompt_path":q["original_prompt_path"],"prompt_sha256":q["prompt_sha256"],"state":"NOT_STARTED","invocation_count":0}
            ledger.append(record); con.execute("INSERT INTO slots(prompt_id,ord,group_id,variant_id,role,taxonomy,planned_split,prompt_path,prompt_sha256,parent_state,state) VALUES(?,?,?,?,?,?,?,?,?,?,?)",(x["prompt_id"],int(x["window_planned_order"]),x["group_id"],x["variant_id"],x["role"],x["taxonomy"],x["planned_split"],q["original_prompt_path"],q["prompt_sha256"],x["parent_state"],"NOT_STARTED"))
        con.execute("INSERT INTO events(prompt_id,event_type,payload_json,captured_at) VALUES(NULL,?,?,?)",("INITIALIZED_AUTHORIZED",json.dumps({"provider_requests":0,"window_cap":68,"authorization_sha256":att["authorization_text_sha256"]},sort_keys=True),now())); con.commit()
        fields=["window_planned_order","prompt_id","group_id","variant_id","role","taxonomy","planned_split","parent_state","prompt_path","prompt_sha256","state","invocation_count"]
        write_csv(LEDGER_CSV,fields,ledger)
    finally: con.close()
    config={"stage":"P4D_GR3Q4E_WINDOW01","revision_id":EXEC.name,"authorization":att,"parent_freeze_sha256":EXPECTED["parent_freeze"],"previous_zero_request_freeze_sha256":EXPECTED["zero_freeze"],"manifest_sha256":EXPECTED["manifest"],"first_window_plan_sha256":EXPECTED["plan"],"runtime":rt,"provider":PROVIDER,"model":MODEL,"native_size":NATIVE_SIZE,"quality":QUALITY,"format":"png","final_size":[1920,1080],"concurrency":1,"outer_retry":False,"native_max_retries":3,"window_logical_cap":68,"physical_attempt_lower_bound_cap":80,"native_retry_event_cap":5,"formal_ingest":False,"c3":False,"new_val":0,"holdout_requests":0}
    write_json(EXEC/"run_config.json",config); write_json(CHECK/"dataset_boundary_before.json",{"validator":before,"annotations":snap}); REQUEST_LOG.touch(); RAW_LOG.touch()
    print(json.dumps({"status":"READY","revision":str(EXEC),"first_slot":plan[0]["prompt_id"],"runtime_profile":rt["active_profile_stratum"]},ensure_ascii=False),flush=True)

def db()->sqlite3.Connection:
    c=sqlite3.connect(DB);c.row_factory=sqlite3.Row;c.execute("PRAGMA journal_mode=WAL");c.execute("PRAGMA synchronous=FULL");return c
def counts(c:sqlite3.Connection)->dict[str,int]:
    r={str(x["state"]):int(x["n"]) for x in c.execute("SELECT state,COUNT(*) n FROM slots GROUP BY state")}; r["TOTAL"]=sum(r.values());r["SUCCESS"]=r.get("SUCCESS",0);r["NOT_STARTED"]=r.get("NOT_STARTED",0);r["COMPLETION_UNKNOWN"]=r.get("COMPLETION_UNKNOWN",0);r["FAILED"]=r.get("FAILED",0);r["PROVIDER_REQUESTS"]=c.execute("SELECT COUNT(*) FROM slots WHERE invocation_count>0").fetchone()[0];r["RETRY_EVENTS"]=c.execute("SELECT COALESCE(SUM(native_retry_count),0) FROM slots WHERE invocation_count>0").fetchone()[0];r["PHYSICAL_LOWER_BOUND"]=r["PROVIDER_REQUESTS"]+r["RETRY_EVENTS"];return r
def stop(c:sqlite3.Connection,reason:str,row:sqlite3.Row|None=None,extra:dict[str,Any]|None=None)->None:
    x={"captured_at":now(),"status":"GLOBAL_STOP","reason":reason,"counts":counts(c),"prompt_id":row["prompt_id"] if row else None};x.update(extra or {});write_json(STOP,x);c.execute("INSERT INTO events(prompt_id,event_type,payload_json,captured_at) VALUES(?,?,?,?)",(row["prompt_id"] if row else None,"GLOBAL_STOP",json.dumps(x,sort_keys=True),now()));c.commit()
def checkpoint(c:sqlite3.Connection,status:str,last:dict[str,Any]|None=None)->None: write_json(CHECK/"latest_checkpoint.json",{"captured_at":now(),"status":status,"counts":counts(c),"last":last,"global_stop":STOP.exists(),"formal_ingest":False,"c3":False,"holdout_requests":0})
def ensure_safe(c:sqlite3.Connection)->None:
    unresolved=c.execute("SELECT * FROM slots WHERE state='STARTED'").fetchall()
    if unresolved:
        for r in unresolved:c.execute("UPDATE slots SET state='COMPLETION_UNKNOWN',error_code='completion_unknown_after_restart',finished_at=? WHERE prompt_id=?",(now(),r["prompt_id"]))
        c.commit();stop(c,"COMPLETION_UNKNOWN",unresolved[0],{"prompt_ids":[r["prompt_id"] for r in unresolved]});raise RuntimeError("durable STARTED slots were found; no resend")
    if STOP.exists():raise RuntimeError("terminal global-stop exists; no resume")

def invoke(c:sqlite3.Connection,r:sqlite3.Row)->dict[str,Any]:
    prompt=Path(r["prompt_path"])
    if digest(prompt)!=r["prompt_sha256"]:raise RuntimeError("prompt_hash_changed")
    raw,final=RAW_OUT/f"{r['prompt_id']}.png",FINAL_OUT/f"{r['prompt_id']}.png"
    if raw.exists() or final.exists() or raw.is_symlink() or final.is_symlink():raise RuntimeError("target_collision")
    rid=f"P4D_GR3Q4E_WINDOW01_{r['ord']:03d}_{r['prompt_id']}";rtmp=STAGE/"raw"/f".{rid}.png";ftmp=STAGE/"final"/f".{rid}.png";started=now();mono=time.monotonic()
    c.execute("UPDATE slots SET state='STARTED',invocation_count=1,request_id=?,started_at=?,native_retry_count=0 WHERE prompt_id=?",(rid,started,r["prompt_id"]));c.execute("INSERT INTO events(prompt_id,event_type,payload_json,captured_at) VALUES(?,?,?,?)",(r["prompt_id"],"STARTED_DURABLE",json.dumps({"request_id":rid,"outer_retry":False},sort_keys=True),now()));c.commit()
    command=["node",str(CLI),"--json","--json-events","--provider",PROVIDER,"images","generate","--model",MODEL,"--prompt",prompt.read_text(encoding="utf-8").rstrip("\n"),"--out",str(rtmp),"--format","png","--size",NATIVE_SIZE,"--quality",QUALITY]
    rc=None;stdout=stderr="";timed=False
    try:
        p=subprocess.run(command,capture_output=True,text=True,timeout=1800,check=False);rc=p.returncode;stdout,stderr=p.stdout,p.stderr;payload=parse_json(stdout)
    except subprocess.TimeoutExpired as e:
        timed=True;stdout=e.stdout if isinstance(e.stdout,str) else "";stderr=e.stderr if isinstance(e.stderr,str) else "";payload={"ok":False,"error":{"code":"timeout","message":"provider completion cannot be confirmed"}}
    except Exception as e:payload={"ok":False,"error":{"code":"connection_or_runner_error","message":redact(str(e))}}
    elapsed=time.monotonic()-mono;finished=now();hs=http_status(payload,rc);ec,em=error_info(payload);nr=retries(stderr);state="FAILED";qa={};raw_sha=final_sha=None
    if timed:state="COMPLETION_UNKNOWN";ec="timeout"
    elif rc==0 and payload.get("ok") is True and rtmp.is_file() and rtmp.stat().st_size>0:
        try:
            qa=convert(rtmp,ftmp);os.replace(rtmp,raw);os.replace(ftmp,final);raw_sha,final_sha=digest(raw),digest(final);state="SUCCESS";ec=em=""
        except Exception as e:ec="invalid_provider_output_or_mechanical_qa";em=redact(str(e))
    elif not ec:ec,em="invalid_provider_output","provider did not return a valid output file"
    response={"request_id":rid,"provider_request_id":request_id(payload),"prompt_id":r["prompt_id"],"ord":r["ord"],"provider":PROVIDER,"model":MODEL,"profile_stratum":"PROFILE_A_RESTORED","prompt_sha256":r["prompt_sha256"],"request_payload_config":{"native_size":NATIVE_SIZE,"quality":QUALITY,"format":"png","outer_retry":False,"native_max_retries":3},"command_redacted":["node","<gpt-image-2-skill>","--json","--json-events","--provider","codex","images","generate","--model",MODEL,"--prompt_sha256",r["prompt_sha256"],"--out",str(raw),"--format","png","--size",NATIVE_SIZE,"--quality",QUALITY],"started_at":started,"finished_at":finished,"returncode":rc,"http_status":hs,"outer_json":payload,"stdout_redacted":redact(stdout),"stderr_redacted":redact(stderr),"native_retry_count":nr,"latency_seconds":elapsed,"state":state,"error_code":ec,"error_message_safe":em,"raw_path":str(raw) if state=="SUCCESS" else None,"final_path":str(final) if state=="SUCCESS" else None,"raw_staging_path":str(rtmp) if rtmp.exists() else None,"final_staging_path":str(ftmp) if ftmp.exists() else None,"raw_sha256":raw_sha,"final_sha256":final_sha,"mechanical_qa":qa}
    rp=RAW/f"{rid}.json";write_json(rp,response);append_jsonl(RAW_LOG,{"request_id":rid,"prompt_id":r["prompt_id"],"response_path":str(rp),"state":state,"http_status":hs,"error_code":ec});append_jsonl(REQUEST_LOG,response)
    c.execute("UPDATE slots SET state=?,provider_request_id=?,finished_at=?,http_status=?,error_code=?,raw_path=?,final_path=?,raw_sha256=?,final_sha256=?,latency_seconds=?,native_retry_count=?,response_path=?,qa_json=? WHERE prompt_id=?",(state,response["provider_request_id"],finished,hs,ec,response["raw_path"],response["final_path"],raw_sha,final_sha,elapsed,nr,str(rp),json.dumps(qa,sort_keys=True),r["prompt_id"]));c.execute("INSERT INTO events(prompt_id,event_type,payload_json,captured_at) VALUES(?,?,?,?)",(r["prompt_id"],state,json.dumps({"http_status":hs,"error_code":ec,"native_retry_count":nr,"latency_seconds":elapsed},sort_keys=True),now()));c.commit()
    return {"prompt_id":r["prompt_id"],"state":state,"http_status":hs,"error_code":ec,"native_retry_count":nr,"latency_seconds":elapsed}

def partial_qa(c:sqlite3.Connection)->dict[str,Any]:
    xs=[];seen=set();dups=[]
    for r in c.execute("SELECT * FROM slots WHERE state='SUCCESS' ORDER BY ord"):
        raw,final=Path(r["raw_path"]),Path(r["final_path"]);rok,rs,re=image_ok(raw);fok,fs,fe=image_ok(final);rh,fh=digest(raw),digest(final)
        if rh in seen:dups.append(r["prompt_id"])
        seen.add(rh);xs.append({"prompt_id":r["prompt_id"],"raw_path":str(raw),"final_path":str(final),"raw_sha256":rh,"final_sha256":fh,"raw_pillow_ok":rok,"raw_size":list(rs) if rs else None,"final_pillow_ok":fok,"final_size":list(fs) if fs else None,"raw_error":re,"final_error":fe})
    q={"captured_at":now(),"new_raw_count":len(xs),"new_final_count":len(xs),"images":xs,"pillow_failures":sum(not x["raw_pillow_ok"] or not x["final_pillow_ok"] for x in xs),"dimension_failures":sum(x["final_size"]!=[1920,1080] for x in xs),"exact_duplicate_hits":len(dups),"duplicate_prompt_ids":dups,"semantic_filtering":False,"human_semantic_acceptance":"NOT_STARTED","P4D_IMAGES_ACCEPTED":0,"full_440_qa":"NOT_REACHED"}
    write_json(QA/"partial_mechanical_qa.json",q);return q
def reports(summary:dict[str,Any],q:dict[str,Any],after:dict[str,Any])->list[Path]:
    paths=[]
    items=[("86_p4d_gr3q4e_window01_execution.md",f"# P4D GR3Q4E Window01 execution\n\n```text\nSTATUS={summary['terminal_status']}\nSTOP_REASON={summary.get('stop_reason')}\nLOGICAL_INVOCATIONS={summary['counts']['PROVIDER_REQUESTS']}\nSUCCESS={summary['counts']['SUCCESS']}\nFAILED={summary['counts']['FAILED']}\nCOMPLETION_UNKNOWN={summary['counts']['COMPLETION_UNKNOWN']}\nRETRY_EVENTS={summary['counts']['RETRY_EVENTS']}\nPHYSICAL_ATTEMPT_LOWER_BOUND={summary['counts']['PHYSICAL_LOWER_BOUND']}\nFORMAL_INGEST=false\nC3=false\nHOLDOUT_REQUESTS=0\n```\n\n所有请求按冻结 first-window order 单并发执行。任何非成功或 completion-unknown 已触发全局停止；没有 outer recovery。\n"),("87_p4d_gr3q4e_window01_partial_qa.md",f"# P4D GR3Q4E Window01 partial mechanical QA\n\n```text\nNEW_RAW_COUNT={q['new_raw_count']}\nNEW_FINAL_COUNT={q['new_final_count']}\nPILLOW_FAILURES={q['pillow_failures']}\nDIMENSION_FAILURES={q['dimension_failures']}\nEXACT_DUPLICATE_HITS={q['exact_duplicate_hits']}\nP4D_IMAGES_ACCEPTED=0\nHUMAN_SEMANTIC_ACCEPTANCE=NOT_STARTED\n```\n\n这里只验证文件、SHA、Pillow 和尺寸；未使用 Codex 视觉判断、C3 或模型预测筛除图片。\n"),("88_p4d_gr3q4e_window01_final.md",f"# P4D GR3Q4E Window01 final\n\n## 已确认事实\n\n```text\nTERMINAL_STATUS={summary['terminal_status']}\nSTOP_REASON={summary.get('stop_reason')}\nCURRENT_VERIFIED_GENERATION_LINEAGE={102+summary['counts']['SUCCESS']}\nOUTSTANDING_AFTER_WINDOW={338-summary['counts']['PROVIDER_REQUESTS']+summary['counts']['FAILED']+summary['counts']['COMPLETION_UNKNOWN']}\nDATASET_VALIDATOR_AFTER={after.get('status')}\nDATASET_ERRORS_AFTER={after.get('error_count')}\nHOLDOUT_CONSUMED=false\n```\n\n## 实验判断\n\n此报告仅陈述 generation 与机械完整性结果；生成成功不表示人类语义接受或 Ground Truth。\n\n## 风险与限制\n\n没有 formal ingest、C3、VAL、HOLDOUT 或生产集成。后续 window 必须取得新的独立人工授权，不会自动启动。\n")]
    for name,text in items:
        p=ROOT/"reports"/name
        if p.exists():raise RuntimeError(f"refusing report overwrite:{p}")
        p.write_text(text,encoding="utf-8");paths.append(p)
    return paths
def seal(c:sqlite3.Connection)->dict[str,Any]:
    co=counts(c);marker=read_json(STOP,{}) or {};complete=co["PROVIDER_REQUESTS"]==68 and co["SUCCESS"]==68
    if not complete and marker.get("status")!="GLOBAL_STOP":raise RuntimeError("cannot seal without complete window or global stop")
    q=partial_qa(c);after=validator("after");boundary={"before":read_json(CHECK/"dataset_boundary_before.json",{}),"after_validator":after,"after_annotations":annotations(),"formal_ingest":False,"holdout_requests":0,"holdout_consumed":False};write_json(CHECK/"dataset_boundary_after.json",boundary)
    status="COMPLETE_WINDOW01_PENDING_HUMAN_SEMANTIC_REVIEW" if complete else "STOPPED_BY_FAILURE_POLICY";summary={"stage":"P4D_GR3Q4E_WINDOW01","revision_id":EXEC.name,"terminal_status":status,"stop_reason":marker.get("reason") if marker else "WINDOW_LOGICAL_CAP_REACHED","captured_at":now(),"counts":co,"provider_requests":co["PROVIDER_REQUESTS"],"new_success":co["SUCCESS"],"P4D_IMAGES_ACCEPTED":0,"formal_ingest":False,"c3":False,"new_val":0,"holdout_requests":0,"holdout_consumed":False,"partial_mechanical_qa":q,"dataset_boundary":boundary};write_json(SUMMARY,summary)
    reps=reports(summary,q,after)
    # Make the SQLite main file stable before binding it into the terminal freeze.
    c.commit(); c.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    static=[PARENT_FREEZE,ZERO_FREEZE,MANIFEST,PLAN,AUTH/"campaign_authorization_attestation.json",EXEC/"run_config.json",DB,LEDGER_CSV,REQUEST_LOG,RAW_LOG,SUMMARY,QA/"partial_mechanical_qa.json",CHECK/"dataset_boundary_before.json",CHECK/"dataset_boundary_after.json",Path(__file__),CLI,BINARY,*sorted(RAW.glob("*.json")),*reps]
    freeze={"stage":"P4D_GR3Q4E_WINDOW01","revision_id":EXEC.name,"status":status,"terminal":summary,"artifact_sha256":{str(p):digest(p) for p in static},"raw_response_files":len(list(RAW.glob("*.json"))),"created_at":now()};fp=FREEZE/"p4d_gr3q4e_window01_terminal_freeze.json";write_json(fp,freeze);dh=digest(fp);(Path(str(fp)+".sha256")).write_text(f"{dh}  {fp.name}\n",encoding="utf-8")
    return {"freeze":str(fp),"freeze_sha256":dh,"summary":summary}

def run()->int:
    c=db();lock=LOCK.open("a+")
    try:
        fcntl.flock(lock.fileno(),fcntl.LOCK_EX|fcntl.LOCK_NB);ensure_safe(c)
        rt=runtime();gate={"captured_at":now(),"runtime":rt,"all_pass":rt["all_pass"],"provider_requests":0};write_json(CHECK/"pre_request_runtime_gate.json",gate)
        if not gate["all_pass"]:stop(c,"PRE_REQUEST_RUNTIME_GATE_FAILED",None,{"checks":rt["checks"]});out=seal(c);print(json.dumps(out,ensure_ascii=False),flush=True);return 2
        for r in c.execute("SELECT * FROM slots WHERE state='NOT_STARTED' ORDER BY ord").fetchall():
            co=counts(c)
            if co["PROVIDER_REQUESTS"]>=WINDOW_CAP:stop(c,"WINDOW_LOGICAL_CAP_REACHED");break
            result=invoke(c,r);co=counts(c);checkpoint(c,"RUNNING" if result["state"]=="SUCCESS" else "STOPPED",result);print(json.dumps({"result":result,"counts":co},ensure_ascii=False),flush=True)
            if result["state"]!="SUCCESS":stop(c,"COMPLETION_UNKNOWN" if result["state"]=="COMPLETION_UNKNOWN" else (f"HTTP_{result['http_status']}" if result["http_status"]!="UNKNOWN" else result["error_code"]),r,{"result":result});break
            if co["PHYSICAL_LOWER_BOUND"]>=PHYSICAL_CAP:stop(c,"PHYSICAL_ATTEMPT_LOWER_BOUND_CAP_REACHED",r);break
            if co["RETRY_EVENTS"]>=RETRY_CAP:stop(c,"NATIVE_RETRY_EVENT_CAP_REACHED",r);break
        if counts(c)["PROVIDER_REQUESTS"]==WINDOW_CAP and not STOP.exists():stop(c,"WINDOW_LOGICAL_CAP_REACHED")
        out=seal(c);print(json.dumps({"status":out["summary"]["terminal_status"],"freeze":out["freeze"],"freeze_sha256":out["freeze_sha256"],"counts":out["summary"]["counts"]},ensure_ascii=False),flush=True);return 0
    except Exception as e:
        for r in c.execute("SELECT * FROM slots WHERE state='STARTED'").fetchall():
            c.execute("UPDATE slots SET state='COMPLETION_UNKNOWN',error_code='runner_exception_after_durable_start',finished_at=? WHERE prompt_id=?",(now(),r["prompt_id"]))
        c.commit()
        if not STOP.exists():stop(c,"RUNNER_EXCEPTION",None,{"error_safe":redact(str(e))})
        out=seal(c);print(json.dumps({"status":"STOPPED_BY_RUNNER_EXCEPTION","error_safe":redact(str(e)),"freeze":out["freeze"]},ensure_ascii=False),flush=True);return 2
    finally:
        try: fcntl.flock(lock.fileno(),fcntl.LOCK_UN)
        finally:lock.close();c.close()
def status()->int:
    c=db()
    try:print(json.dumps({"counts":counts(c),"stop":read_json(STOP,None),"summary":read_json(SUMMARY,None)},ensure_ascii=False,indent=2));return 0
    finally:c.close()
def main()->int:
    p=argparse.ArgumentParser();p.add_argument("command",choices=("init","run","status"));a=p.parse_args();return init() or 0 if a.command=="init" else run() if a.command=="run" else status()
if __name__=="__main__":
    try:raise SystemExit(main())
    except Exception as e:print(json.dumps({"ok":False,"error_safe":redact(str(e))},ensure_ascii=False),file=sys.stderr);raise SystemExit(2)
