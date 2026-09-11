"""Isolated CLI entry with local-module provenance reporting, no task answers."""
import json
import runpy
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
runpy.run_module('ss_partial', run_name='__main__')
modules = {}
for name, module in sorted(sys.modules.items()):
    if any(name == p or name.startswith(p + '.') for p in ('ss_partial', 'ss_document', 'plm_l1_v09')):
        path = Path(module.__file__).resolve()
        assert path.is_relative_to(ROOT)
        assert path.name not in ('reader.py', 'training.py')
        modules[name] = path.relative_to(ROOT).as_posix()
assert not any(name == 'evaluation' or name.startswith('evaluation.') for name in sys.modules)
print(json.dumps({'local_modules': modules, 'all_local_paths_verified': True}), file=sys.stderr)
