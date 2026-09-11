from pathlib import Path
from ss_core_v04.compile import compile_bundle
root=Path(__file__).resolve().parent
print(compile_bundle(root,root/'bundle04'))
