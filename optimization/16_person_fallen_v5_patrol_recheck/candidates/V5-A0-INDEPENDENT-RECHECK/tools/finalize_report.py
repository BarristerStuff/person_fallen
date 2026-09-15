"""Terminal audit/report only. No model calls or modification of candidate implementation."""
from contracts import *
from run_secondary import verify_freeze

def finalize():
 claims=list((ROOT/'eval').glob('*/requests/*/claimed.json'))
 completed=list((ROOT/'eval').glob('*/requests/*/completed.json'))
 phases={};status=None
 for phase in PHASES:
  p=ROOT/'eval'/phase
  if (p/'PROTOCOL_INCOMPLETE.json').exists():
   phases[phase]={'status':'PROTOCOL_INCOMPLETE','gate':'NOT_EVALUATED','detail':loads((p/'PROTOCOL_INCOMPLETE.json').read_bytes())};status='V5_PROTOCOL_INCOMPLETE_NO_RETRY'
  elif (p/'COMPLETION_LOCK.json').exists():
   lock=loads((p/'COMPLETION_LOCK.json').read_bytes());verify_sha(p/'summary.json',lock['summary_sha256']);phases[phase]=loads((p/'summary.json').read_bytes())
  else:phases[phase]='NOT_RUN'
 if status is None:
  if isinstance(phases['dev'],dict) and phases['dev']['gate']=='FAIL':status='V5_A0_DEV_GATE_FAIL'
  elif isinstance(phases['regression'],dict) and phases['regression']['gate']=='FAIL':status='V5_A0_REGRESSION_GATE_FAIL'
  elif all(isinstance(v,dict) and v['gate']=='PASS' for v in phases.values()):status='V5_A0_DEVELOPMENT_PASS_PENDING_INDEPENDENT_VALIDATION'
  else:raise ValueError('No terminal state; cannot report completion')
 freeze=verify_freeze()
 ids=[loads(p.read_bytes())['request_id'] for p in claims]
 if len(set(ids))!=len(ids) or len(ids)>340:raise ValueError('Budget/identity violation')
 counts={phase:len(list((ROOT/'eval'/phase/'requests').glob('*/claimed.json'))) for phase in PHASES}
 report={'PRIMARY_SOURCE':'FROZEN_V4_CACHE','SECONDARY_CANDIDATE':'V5-A0-INDEPENDENT-RECHECK','EVALUATION_MODE':'CACHED_PRIMARY_PLUS_NEW_SECONDARY','DEV':phases['dev'],'CONSUMED_SCREEN_DEVELOPMENT_REGRESSION':phases['regression'],'TOTAL_NEW_MODEL_REQUESTS':len(claims),'SECONDARY_VALID_RESPONSES':len(completed),'REQUESTS_BY_PHASE':counts,'PRIMARY_NEW_MODEL_REQUESTS':0,'DETECTOR_NEW_REQUESTS':0,'VAL_REQUESTS':0,'HOLDOUT_REQUESTS':0,'HOLDOUT_CONSUMED':False,'ROBOT_REOBSERVATION_VALIDATED':False,'FINAL_STATUS':status,'DEVELOPMENT_CANDIDATE':'V5-A0-INDEPENDENT-RECHECK','CURRENT_WINNER':'NONE','READY_FOR_INDEPENDENT_VALIDATION_PROTOCOL_REVIEW':status=='V5_A0_DEVELOPMENT_PASS_PENDING_INDEPENDENT_VALIDATION','READY_FOR_FINAL_HOLDOUT':False,'PRODUCTION_INTEGRATION_READY':False,'NEXT_ACTION':'REVIEW_INDEPENDENT_VALIDATION_PROTOCOL_AND_EXPOSURE_AUDIT' if status=='V5_A0_DEVELOPMENT_PASS_PENDING_INDEPENDENT_VALIDATION' else 'STOP_CURRENT_CANDIDATE','freeze_sha256':sha(ROOT/'freeze/EXECUTION_FREEZE.json'),'immutable_bindings_final_check':'PASS','completed_timestamp':utc(),'GT_TYPE':'PROMPT_DERIVED_SYNTHETIC_GT','HUMAN_SEMANTIC_REVIEW_REQUIRED_FOR_SYNTHETIC_DEVELOPMENT':False,'MODEL_PREDICTION_USED_AS_GT':False}
 write_json(ROOT/'reports/final_report.json',report)
 compact=[]
 for phase in PHASES:
  m=phases[phase]
  compact.append({'phase':phase,'status':m['status'] if isinstance(m,dict) else m,'gate':m.get('gate','NOT_RUN') if isinstance(m,dict) else 'NOT_RUN','rows':m.get('rows','NOT_RUN') if isinstance(m,dict) else 'NOT_RUN','requests':counts[phase],'ground_lying_alert_recall':m.get('immediate_ALERT_recall','NOT_EVALUATED') if isinstance(m,dict) else 'NOT_RUN','ground_lying_alert_recheck_coverage':m.get('ALERT_RECHECK_coverage','NOT_EVALUATED') if isinstance(m,dict) else 'NOT_RUN','normal_negative_recheck_rate':m.get('determinate_negative_total_RECHECK_rate','NOT_EVALUATED') if isinstance(m,dict) else 'NOT_RUN'})
 write_csv(ROOT/'reports/phase_metrics.csv',compact)
 lines=['# V5-A0 独立场景复核开发终态',f'\n**{status}**','\n主路来源：FROZEN_V4_CACHE；评测方式：CACHED_PRIMARY_PLUS_NEW_SECONDARY。','\n新旁路模型请求：'+str(len(claims))+'；新主路/Detector/VAL/Holdout 请求均为 0。','\n## 分阶段结果']
 for phase in PHASES:
  lines+=['\n### '+phase,'```json',json.dumps(phases[phase],ensure_ascii=False,indent=2),'```']
 lines+=['\n## 解释与暴露边界','- ALERT 集合是历史主路继承；不可写成旁路新增的直接告警能力。','- RECHECK 是待确认状态，不是确认倒地；coverage 不等于立即报警召回。','- DEV 与旧 SCREEN 都是已暴露的开发资源；SCREEN 本次仅为 CONSUMED_SCREEN_DEVELOPMENT_REGRESSION。','- 用户声明提示词与图像相符；机器核验仅证明 hash/行绑定，不声称全量像素语义验证。当前合成开发不要求人工逐图审核。','- auxiliary 和 visual_uncertain 保留独立决策分布，不能隐藏主路继承 ALERT。','- 未验证机器人复拍、新视角、现场相机、视频或端到端性能；报告时延仅为旁路新测量。','\n## 独立验证待办（未执行）','- 审计 DEV、历史 SCREEN、REV15/V5 和其它历史试验的样本/组/媒体暴露；证明拟议独立验证资源未被用于选择候选。','- 在新授权下评审独立验证协议、同一门禁、失败停止规则与缓存/新推理边界；本次不读取或选择 VAL/Holdout 样本。', '\nNEXT_ACTION='+report['NEXT_ACTION']]
 write_bytes(ROOT/'reports/final_report.md',('\n'.join(lines)+'\n').encode())
 print(json.dumps({k:v for k,v in report.items() if k not in ['DEV','CONSUMED_SCREEN_DEVELOPMENT_REGRESSION']},ensure_ascii=False,indent=2))
if __name__=='__main__':finalize()
