import contextlib,io,json,runpy,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parent;sys.path.insert(0,str(ROOT))
assert not (ROOT/'data').exists() and not (ROOT/'evaluation').exists()
assert not any(p.name in ('learning.py','training.py','reader.py','transaction.py') for p in ROOT.rglob('*.py'))
sys.argv=['ss_core_v02',*sys.argv[1:]];out=io.StringIO();code=0
try:
    with contextlib.redirect_stdout(out):runpy.run_module('ss_core_v02',run_name='__main__')
except SystemExit as e:code=e.code
paths={}
for name,m in list(sys.modules.items()):
    if name.startswith(('ss_','bridge','plm_l1_v09','plm_p1','plm_s1')):
        p=Path(m.__file__).resolve();assert p.is_relative_to(ROOT)
        assert not set(name.split('.'))&{'evaluation','learning','training','reader','transaction'}
        paths[name]=p.relative_to(ROOT).as_posix()
print(out.getvalue(),end='')
print(json.dumps({'all_project_imports_local':True,'dedicated_teacher_modules_and_data_absent':True,
                  'shared_modules_may_contain_unused_definitions':True,'paths':paths}),file=sys.stderr)
raise SystemExit(code)
