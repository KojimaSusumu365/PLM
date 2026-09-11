"""Paired core arithmetic experiment with repeated, changing external teachers."""
import copy
import numpy as np
from plm_l1_v09.component.algebra import digest
from ss_retention.memory import CorrectionMemory
from ss_retention.learning import learn as batch_learn
from ss_core.learning import learn
from ss_core.clock import read_scores
from ss_core.memory import WaveCorrectionView

def difference(a,b):
    return max(float(np.max(abs(a.parts[n].weights-b.parts[n].weights))) for n in a.parts)

def run(candidates, seeds):
    rows = []
    for seed in seeds:
        batch = CorrectionMemory(candidates,seed='core-arithmetic-'+str(seed))
        one, chunks = copy.deepcopy(batch), copy.deepcopy(batch)
        for i in range(24):
            key = digest('repeated-key/'+str(i%8))
            domain,value = batch.labels[((i%8)+2*(i//8))%23]
            t = {'key':key,'domain':domain,'value':value,'protect':i%5!=4}
            reference_before = batch.parts['main'].scores(key)
            before,_ = read_scores(one.parts['main'],key,'arithmetic')
            batch_learn(batch,t)
            a,b = learn(one,t),learn(chunks,t,chunk=37)
            assert a['status'] == b['status'] == 'learned'
            rows.append({'seed':seed,'update':i,'key':key,'teacher':t,
                         'preupdate_score_max_abs_difference':float(np.max(abs(reference_before-before))),
                         'coefficient_max_abs_difference':difference(batch,one),
                         'stream_chunk_fingerprint_equal':one.fingerprint==chunks.fingerprint,
                         'registry_and_update_counts_equal':all(one.parts[n].registry==batch.parts[n].registry and
                             one.parts[n].updates==batch.parts[n].updates for n in one.parts),
                         'postupdate_target_score':WaveCorrectionView(one).recall(key,domain)})
    return {'updates':rows,'maximum_coefficient_difference':max(r['coefficient_max_abs_difference'] for r in rows),
            'maximum_score_difference':max(r['preupdate_score_max_abs_difference'] for r in rows),
            'all_chunk_fingerprints_equal':all(r['stream_chunk_fingerprint_equal'] for r in rows),
            'all_metadata_equal':all(r['registry_and_update_counts_equal'] for r in rows)}
