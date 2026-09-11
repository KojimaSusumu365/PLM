"""Launch only the extracted generator code; report loaded local-module provenance."""
import json
import runpy
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
runpy.run_module('ss_document', run_name='__main__')
loaded = {}
for name, module in sorted(sys.modules.items()):
    if name == 'ss_document' or name.startswith('ss_document.') or name == 'plm_l1_v09' or name.startswith('plm_l1_v09.'):
        path = Path(module.__file__).resolve()
        assert path.is_relative_to(ROOT)
        assert path.name not in ('reader.py', 'training.py')
        loaded[name] = path.relative_to(ROOT).as_posix()
assert not any(n == 'evaluation' or n.startswith('evaluation.') for n in sys.modules)
print(json.dumps({'local_modules': loaded, 'paths_within_generator_directory': True}), file=sys.stderr)
