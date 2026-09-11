"""Separate-process inference, with teacher/evaluation modules physically omitted."""
import contextlib
import io
import json
import runpy
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT))
assert not (ROOT/'data').exists() and not (ROOT/'evaluation').exists()
assert not any(p.name in ('reader.py','learning.py','training.py','feedback.py') for p in ROOT.rglob('*.py'))
sys.argv = ['ss_core',*sys.argv[1:]]
out = io.StringIO()
code = 0
try:
    with contextlib.redirect_stdout(out):
        runpy.run_module('ss_core',run_name='__main__')
except SystemExit as e:
    code = e.code
paths = {}
for name,module in list(sys.modules.items()):
    if name.startswith(('ss_core','bridge','ss_','plm_l1_v09','plm_p1','plm_s1')):
        p = Path(module.__file__).resolve()
        assert p.is_relative_to(ROOT), (name,str(p))
        assert not set(name.split('.'))&{'evaluation','reader','learning','training','feedback'}
        paths[name] = p.relative_to(ROOT).as_posix()
print(out.getvalue(),end='')
print(json.dumps({'all_project_imports_local':True,'dedicated_teacher_and_evaluation_modules_absent':True,
                  'shared_module_unused_definitions_may_remain':True,'paths':paths}),file=sys.stderr)
raise SystemExit(code)
