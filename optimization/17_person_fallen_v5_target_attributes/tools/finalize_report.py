"""Terminal reporting only, no model calls and no alteration of frozen implementation."""
from contracts import *
from run_target_eval import verify_freeze

def finalize():
 verify_freeze();plan=loads((ROOT/'protocol/execution_plan.json').read_bytes());phases={};status=None
 for phase in PHASES:
  p=ROOT/'eval'/phase
  if (p/'PROTOCOL_INCOMPLETE.json').exists():
   info=loads((p/'PROTOCOL_INCOMPLETE.json').read_bytes());phases[phase]={'status':'PROTOCOL_INCOMPLETE','new_model_requests':info['claimed_requests'],'valid_responses':info['completed_requests'],'gate':'NOT_EVALUATED_PROTOCOL_INCOMPLETE','details':info};status=plan['terminal_statuses']['protocol']
  elif (p/'COMPLETION_LOCK.json').exists():
   lock=loads((p/'COMPLETION_LOCK.json').read_bytes());verify_sha(p/'summary.json',lock['summary_sha256']);phases[phase]={'status':'COMPLETE',**loads((p/'summary.json').read_bytes())}
  else:phases[phase]={'status':'NOT_RUN','gate':'NOT_RUN'}
 if status is None:
  if phases['pilot']['gate']=='FAIL':status=plan['terminal_statuses']['pilot_fail']
  elif phases['regression']['gate']=='FAIL':status=plan['terminal_statuses']['regression_fail']
  elif all(x['gate']=='PASS' for x in phases.values()):status=plan['terminal_statuses']['pass']
  else:raise ValueError('No terminal condition yet; do not invent completion')
 claims=[loads(p.read_bytes()) for p in (ROOT/'eval').glob('*/requests/*/claimed.json')]
 if len(claims)>116 or len({r['request_id'] for r in claims})!=len(claims):raise ValueError('Budget or identity anomaly')
 reqs={phase:sum(r['phase']==phase for r in claims) for phase in PHASES}
 regression=phases['regression']
 if regression['status']=='COMPLETE':
  regression={**regression,'request_count':reqs['regression'],'PFV4_SCREEN_0066_people_count':regression['target_people_count'],'PFV4_SCREEN_0066_person_attribute_decisions':regression['target_person_decisions'],'PFV4_SCREEN_0066_final_decision':regression['target_final']}
 result={'CANDIDATE':CANDIDATE,'EVALUATION_MODE':'NEW_TARGET_ATTRIBUTES_ONLY','GT_TYPE':'PROMPT_DERIVED_SYNTHETIC_GT','HUMAN_SEMANTIC_REVIEW_REQUIRED':False,'PILOT_DEV_115':phases['pilot'],'KNOWN_FAILURE_REGRESSION_1':regression,'TOTAL_NEW_MODEL_REQUESTS':len(claims),'REQUESTS_BY_PHASE':reqs,'CACHED_PRIMARY_USED_FOR_FINAL_DECISION':False,'OBJECT_LOCALIZATION_ACCURACY':'UNVERIFIED','OLD_PRIMARY_REINFERENCE_REQUESTS':0,'DETECTOR_REQUESTS':0,'FULL_DEV_EXTENSION_REQUESTS':0,'OTHER_SCREEN_REQUESTS':0,'VAL_REQUESTS':0,'HOLDOUT_REQUESTS':0,'HOLDOUT_CONSUMED':False,'ROBOT_CONTROL_REQUESTS':0,'CURRENT_WINNER':'NONE','PRODUCTION_INTEGRATION_READY':False,'READY_FOR_FINAL_HOLDOUT':False,'FINAL_STATUS':status,'NEXT_ACTION':'PROPOSE_FULL_DEV_EXTENSION_PLAN_ONLY' if status==plan['terminal_statuses']['pass'] else 'STOP_CURRENT_CANDIDATE','immutable_bindings_final_check':'PASS','freeze_sha256':sha(ROOT/'freeze/EXECUTION_FREEZE.json'),'timestamp':utc()}
 auditpath=ROOT/'reports/independent_audit.json'
 if not auditpath.exists():raise ValueError('Independent offline audit must finish first')
 result['independent_audit_sha256']=sha(auditpath)
 write_json(ROOT/'reports/final_report.json',result)
 lines=['# V5-B0-TARGET-ATTRIBUTES 开发实验终态','',status,'','新推理只用于固定 pilot115 与条件式 known-regression1；未使用主路缓存决定结果。','',f'新增模型请求总数：{len(claims)}。','']
 for name in ['PILOT_DEV_115','KNOWN_FAILURE_REGRESSION_1']:
  lines += ['## '+name,'```json',json.dumps(result[name],ensure_ascii=False,indent=2),'```','']
 lines += ['## 边界与历史','- 115张与单张已知错误均为已消费开发资源，不是独立验证。','- 5张多人DEV仅1个scenario group；不宣称多场景泛化。','- bbox仅作机械合法性/关联，不是人工框GT。OBJECT_LOCALIZATION_ACCURACY=UNVERIFIED。','- hash核验不等于全量像素语义核验；人工逐图审核不是本次合成开发前置条件。','- 已知回归旧crop同时包含跪地者与躺地者，不采用“躺地者完全未进入crop”解释。','- V4-A0 SCREEN_FAIL；REV15仍因15/55坐地误报失败，正确ground ALERT为145/145，不能使用81.18%错误分层；V5-A0为90/230正常负例RECHECK超标失败，未请求该回归图。','- RECHECK不是已确认倒地；coverage不是立即告警召回。','- 未运行完整DEV、其余SCREEN、VAL/Holdout、机器人控制或生产集成。','', 'NEXT_ACTION='+result['NEXT_ACTION']]
 write_bytes(ROOT/'reports/final_report.md',('\n'.join(lines)+'\n').encode())
 import csv,io
 rr=[]
 for phase in PHASES:
  m=phases[phase];rr.append({'phase':phase,'status':m['status'],'requests':reqs[phase],'rows':m.get('rows','NOT_RUN' if m['status']=='NOT_RUN' else 'INCOMPLETE'),'ground_alert_recall':m.get('ground_lying_ALERT_recall','NOT_RUN' if m['status']=='NOT_RUN' else 'NOT_EVALUATED'),'floor_alert':m.get('floor_sitting_ALERT_count','NOT_RUN' if m['status']=='NOT_RUN' else 'NOT_EVALUATED'),'floor_recheck':m.get('floor_sitting_RECHECK_count','NOT_RUN' if m['status']=='NOT_RUN' else 'NOT_EVALUATED'),'gate':m['gate']})
 f=io.StringIO(newline='');w=csv.DictWriter(f,fieldnames=rr[0]);w.writeheader();w.writerows(rr);write_bytes(ROOT/'reports/phase_metrics.csv',f.getvalue().encode())
 print(json.dumps({k:v for k,v in result.items() if k not in ['PILOT_DEV_115','KNOWN_FAILURE_REGRESSION_1']},ensure_ascii=False,indent=2))
if __name__=='__main__':finalize()
