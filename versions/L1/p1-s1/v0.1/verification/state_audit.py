import sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from evaluation.integrity import read,write
rows=[read(ROOT/'results/runs'/n/'RESULT.json') for n in read(ROOT/'results/INDEX.json')['runs']]
received=[r for r in rows if r['query']['status']=='received'];teachers=[r for r in rows if r['teacher_learned']]
assert all(r['result']['received_observation_equal'] for r in received)
assert all(r['teacher_correct'] for r in teachers)
write(ROOT/'verification/SEMANTIC_STATE_AUDIT.json',{'passed':True,'received_queries_exact_observation':len(received),
    'received_teachers_exact_observation':len(teachers),'scope':'Compare complete count, presentation, per-cell state and candidate sets against evaluation-only source; not just final generated meaning.',
    'eligible_for_inference':False})
print({'received_query_states_exact':len(received),'teacher_states_exact':len(teachers)})
