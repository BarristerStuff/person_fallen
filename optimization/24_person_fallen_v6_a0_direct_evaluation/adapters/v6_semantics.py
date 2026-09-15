"""Direct read-only imports of the immutable stage-20 V6 semantic candidate."""
import importlib.util,hashlib,json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];BASE=ROOT.parent;V6=BASE/'20_person_fallen_v6_target_support_config'
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def load(name,path):
 s=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m
CONTRACTS=load('immutable_v6_contracts_r2',V6/'tools/contracts.py');POLICY=load('immutable_v6_policy_r2',V6/'policy/target_policy.py')
PROMPT=V6/'prompt/target_support_attributes.txt';SCHEMA=V6/'schema/target_attributes.json';DEFINITION=V6/'definition/person_fallen_v4_operational_definition.md'
SEMANTIC_PATHS=[PROMPT,SCHEMA,V6/'policy/target_policy.py',DEFINITION,V6/'tools/contracts.py']
def bindings():return {str(p.resolve()):sha(p) for p in SEMANTIC_PATHS}
def parse(raw):return CONTRACTS.parse(raw)
def evaluate(parsed):return POLICY.evaluate(parsed)
