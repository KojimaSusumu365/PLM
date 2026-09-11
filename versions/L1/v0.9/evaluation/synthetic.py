"""Matched-mask symbolic and SS selection; separate selection from storage errors."""
import time
import numpy as np
from plm_l1_v09.selection import select, grouped, unique_rows
from plm_l1_v09.component.algebra import canonical
from plm_l1_v09.component.banked import fit_banked
from plm_l1_v09.thresholds import MIN_SCORE, MIN_MARGIN

def symbolic_predict(leaves,context):
    accepted=set()
    for mask in sorted({tuple(sorted(c)) for c,_ in leaves}):
        key=canonical({f:context[f] for f in mask})
        for c,counts in grouped(leaves,mask) if all(set(c)==set(mask) for c,_ in leaves) else grouped([r for r in leaves if set(r[0])==set(mask)],mask):
            if canonical(c)!=key: continue
            scores=sorted(((n/sum(counts.values()),label) for label,n in counts.items()),reverse=True)
            top,label=scores[0]; runner=scores[1][0] if len(scores)>1 else 0.
            if top>=MIN_SCORE and top-runner>=MIN_MARGIN: accepted.add(label)
    return next(iter(accepted)) if len(accepted)==1 else None

def counts(predictions,gold):
    return {'requests':len(gold),'correct':sum(p==g for p,g in zip(predictions,gold)),
            'wrong':sum(p is not None and p!=g for p,g in zip(predictions,gold)),
            'abstained':sum(p is None for p in predictions)}

def run(task,method,dimension,seed,enabled=True):
    rows=[(r['context'],r['label']) for r in task['train']]
    started=time.perf_counter()
    leaves,audit=select(rows,method=method,dimension=dimension,seed=seed,enabled=enabled)
    selection_seconds=time.perf_counter()-started
    started=time.perf_counter()
    memory,stats=fit_banked(rows,dimension,'dependency-store/'+seed,selected_leaves=leaves,cache_slots=0)
    compilation_seconds=time.perf_counter()-started
    symbolic=[symbolic_predict(leaves,r['context']) for r in task['test']]
    started=time.perf_counter()
    phase=[memory.recall(r['context'])['value'] for r in task['test']]
    phase_seconds=time.perf_counter()-started
    unknown=[memory.recall(r['context'])['value'] for r in task['unregistered']]
    heap=stats.pop('owned_heap_bytes'); audit.pop('wall_seconds')
    masks=[list(x) for x in audit['selected_masks']]
    row={'task_id':task['id'],'family':task['family'],'train_count':task['train_count'],'flipped_labels':task['flipped_labels'],
         'method':method,'dimension':dimension,'seed':seed,'selection_enabled':enabled,
         'selected_masks':masks,'true_dependencies':task['true_dependencies'],
         'fallback_full_context':audit['fallback_full_context'],
         'symbolic_projection':counts(symbolic,[r['label'] for r in task['test']]),
         'phase_retrieval':counts(phase,[r['label'] for r in task['test']]),
         'unregistered_requests':len(unknown),'unregistered_accepted':sum(v is not None for v in unknown),
         'storage':stats,'symbolic_leaf_serialization_bytes':len(canonical(leaves).encode('utf-8')),
         'selection':audit}
    perf={'task_id':task['id'],'method':method,'dimension':dimension,'seed':seed,'selection_enabled':enabled,
          'selection_seconds':selection_seconds,'compile_seconds':compilation_seconds,'phase_query_seconds':phase_seconds,
          'owned_heap_bytes':heap,'heap_scope':'memory owned objects, excludes Python/NumPy runtime and temporary training matrices'}
    return row,perf
