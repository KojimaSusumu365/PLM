import hashlib,json,sys
from pathlib import Path
root=Path(__file__).resolve().parents[1]/'outputs'/'PLM-L1-v0.9'
sys.path.insert(0,str(root))
from evaluation.support import data,six_pairs
from evaluation.integrity import sha,verify_freeze
from plm_l1_v09.component.training import fit
from plm_l1_v09.component.runtime import Model
from plm_l1_v09.runtime import TemporalModel
from plm_l1_v09.portability import compare
sys.path.insert(0,str(root/'tests'))
from test_v09 import changed

def write(name,value):
    with (root/'verification'/name).open('x',encoding='utf-8') as f: f.write(json.dumps(value,ensure_ascii=False,indent=2)+'\n')

saved=TemporalModel.load(root/'results/model')
variants={n:fit(six_pairs() if n=='six' else data('component_train'),data('lexicon'),selector='symbolic' if n=='symbolic' else 'id3' if n=='id3' else 'ss',seed='banked-evaluation-0',selection_seed='selection-evaluation-0') for n in ('six','symbolic','id3')}
def blocks(m): return {n:[b.blob for b in memory.blocks] for n,memory in m.memories.items()}
sys.path.insert(0,str(root.parent/'PLM-L1-v0.8'))
from plm_l1_v06.runtime import Model as OldModel
old=OldModel.load(root.parent/'PLM-L1-v0.8/results/model/component')
write('WEIGHT_COMPARISONS.json',{'ss_six_vs_432_blocks_exact':blocks(variants['six'])==blocks(saved.component),
                               'ss_vs_matched_symbolic_blocks_exact':blocks(variants['symbolic'])==blocks(saved.component),
                               'v09_id3_vs_v08_component_blocks_exact':blocks(variants['id3'])==blocks(old),
                               'metadata_and_model_fingerprints_not_required_equal_for_these_cross_recipe_comparisons':True})
probe=['太郎が花子を助けた。その後、花子が健太を褒めた。','太郎が花子を助けた。花子が健太を褒めた。','']
tiny=changed(saved,'ulp'); big=changed(saved,.01)
write('PORTABILITY_CONTROLS.json',{'one_ulp':compare(saved,tiny,probe),'large_change':compare(saved,big,probe),
                                 'old_packet_on_changed_model':tiny.recover(saved.encode(data('evaluation')[0]['meaning']))['status'],
                                 'linux_execution_performed':False,'linux_reason':'WSL executable exists but WSL is not installed; no Linux runtime available.',
                                 'scope':'Local controlled perturbations, not a Linux reproduction.'})
same=[]
for rel in ('EVALUATION.json','model/model.json','model/weights.npz','model/component/model.json','model/component/weights.npz'):
    a=root/'results'/rel; b=root.parents[1]/'work/v09-repeat'/rel
    same.append({'file':rel,'sha256':sha(a),'repeat_sha256':sha(b),'equal':sha(a)==sha(b)})
assert all(r['equal'] for r in same)
write('REPEATABILITY.json',{'two_full_v09_numeric_runs':True,'files':same,'same_source_freeze':verify_freeze(),
                           'excluded_from_deterministic_comparison':['PERFORMANCE.json wall times and environment'],
                           'old_v08_full_numeric_evaluation_repeated':False})
expected=json.loads((root/'verification/PRESERVED_BASELINE.json').read_text(encoding='utf-8'))
bad=[name for name,value in expected.items() if not (root.parent/name).is_file() or sha(root.parent/name)!=value]
assert not bad,bad
write('PRESERVATION_CHECK.json',{'previous_files_checked':len(expected),'changed':bad,'all_preserved':True,
                                'excluded_shared_history_document':'PLM-SS-LANGUAGE-DIRECTION.md (append-only planned)',
                                'vendor_v08_sha256':sha(root/'vendor/PLM-L1-v0.8.zip')})
write('REVIEW_PROVENANCE.json',{p.name:sha(p) for p in sorted((root/'reviews').iterdir()) if p.is_file()})
print('extra evidence saved; baseline files',len(expected),flush=True)
