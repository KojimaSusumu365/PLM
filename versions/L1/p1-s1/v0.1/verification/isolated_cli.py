"""Separate-process inference provenance check, not an evaluation data source."""
import contextlib,io,json,runpy,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parent;sys.path.insert(0,str(ROOT))
assert not (ROOT/'data').exists() and not (ROOT/'evaluation').exists()
assert not any(p.name in ('reader.py','training.py','learning.py','feedback.py') for p in ROOT.rglob('*.py'))
sys.argv=['bridge',*sys.argv[1:]];out=io.StringIO();code=0
try:
    with contextlib.redirect_stdout(out):runpy.run_module('bridge',run_name='__main__')
except SystemExit as e:code=e.code
paths={}
for name,m in list(sys.modules.items()):
    if name=='bridge' or name.startswith(('bridge.','ss_','plm_l1_v09','plm_p1','plm_s1')):
        p=Path(m.__file__).resolve();assert p.is_relative_to(ROOT)
        assert not any(part in name.split('.') for part in ('evaluation','reader','training','learning','feedback'))
        paths[name]=str(p.relative_to(ROOT))
print(out.getvalue(),end='');print(json.dumps({'all_project_imports_local':True,'teacher_data_and_dedicated_training_reader_evaluation_modules_absent':True,'paths':paths}),file=sys.stderr)
raise SystemExit(code)
