import json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from verify_release import audit
from evaluation.integrity import write,verify_development
data=json.loads((ROOT/'data/CASES.json').read_text(encoding='utf-8'))['development']
result,arrays,checks=audit(ROOT/'verification/development',{(c['seed'],c['size']):c for c in data},80,36352)
assert result['freeze_hash']=='development:'+verify_development()
write(ROOT/'verification/DEVELOPMENT_AUDIT.json',checks);print(json.dumps(checks))
