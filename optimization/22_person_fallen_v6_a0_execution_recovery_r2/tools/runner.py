import argparse,json,subprocess,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'tools'));from engine import *
def runtime():
 d={}
 for s in ['tags','version','ps']:
  raw=subprocess.run(['curl','--noproxy','*','-fsS','--max-time','10',MODEL['endpoint']+'/api/'+s],capture_output=True,check=True).stdout;d[s]=json.loads(raw);d[s+'_raw']=raw.decode()
 ms=[m for m in d['tags']['models'] if m.get('name')==MODEL['name']]
 if len(ms)!=1 or ms[0].get('digest')!=MODEL['digest'] or d['version'].get('version')!=MODEL['ollama_version']:raise ValueError('Ollama preflight')
 return d
def main():
 p=argparse.ArgumentParser();p.add_argument('phase',choices=['pilot','regression','full_remaining']);a=p.parse_args();f=verify_real_freeze();snap=runtime();write_exclusive(ROOT/'reports'/f'ollama_preflight_{a.phase}.json',snap)
 s=run_stage(a.phase,ROOT/'eval',f,lambda data,row: call_real(data),snap)
 if a.phase=='full_remaining':s=aggregate_full(ROOT/'eval')
 print(json.dumps(s,ensure_ascii=False))
if __name__=='__main__':
 try:main()
 except Exception as e:print(json.dumps({'status':'FAILED','error':repr(e)}),file=sys.stderr);sys.exit(2)
