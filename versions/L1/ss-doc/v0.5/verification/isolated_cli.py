import json,runpy,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parent;sys.path.insert(0,str(ROOT));code=0
try:runpy.run_module('ss_reconfirm',run_name='__main__')
except SystemExit as e:code=e.code or 0
loaded={}
for name,module in sorted(sys.modules.items()):
    if any(name==p or name.startswith(p+'.') for p in ('ss_reconfirm','ss_revision','ss_retention','ss_partial','ss_document','plm_l1_v09')):
        path=Path(module.__file__).resolve();assert path.is_relative_to(ROOT)
        assert path.name not in ('reader.py','training.py','learning.py');loaded[name]=path.relative_to(ROOT).as_posix()
assert not any(n=='evaluation' or n.startswith('evaluation.') for n in sys.modules)
print(json.dumps({'verified_paths':loaded,'teacher_learning_reader_evaluator_absent':True}),file=sys.stderr)
raise SystemExit(code)
