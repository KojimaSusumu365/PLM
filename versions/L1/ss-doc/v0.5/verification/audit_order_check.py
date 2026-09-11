import copy,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from evaluation.integrity import read,write,sha,verify
from evaluation.reconfirm_cases import audit_datasets
old=read(ROOT/'verification/DATA_AUDIT_PREFILE_ORDER.json');new=read(ROOT/'verification/DATA_AUDIT.json')
ordered=copy.deepcopy(old);ordered['rows']=sorted(ordered['rows'],key=lambda r:r['split'])
assert ordered==new==read(ROOT/'results/DATA_AUDIT.json')
assert new==audit_datasets(read(ROOT/'data/RECONFIRM_DATASETS.json'),read(ROOT/'data/SPLIT_EXCLUSIONS.json'))
write(ROOT/'verification/AUDIT_ORDER_REPAIR.json',{'passed':True,
  'first_verifier_attempt':'verify_release.py line28 AssertionError: audit_datasets(data,exclude) == verification/DATA_AUDIT.json',
  'cause':'Audit was first generated in in-memory construction order development,300,301. Canonical JSON sorts split keys, so reloaded data audits in300,301,development order.',
  'repair':'Only the non-frozen verification audit row order was normalized to reloaded-dataset order; original audit preserved.',
  'no_row_value_changed':True,'source_model_protocol_and_data_unchanged':True,'evaluation_results_unchanged':True,
  'old_audit_sha256':sha(ROOT/'verification/DATA_AUDIT_PREFILE_ORDER.json'),'new_audit_sha256':sha(ROOT/'verification/DATA_AUDIT.json'),
  'frozen_digest':verify(),'eligible_for_inference':False})
print({'passed':True,'only_row_order_changed':True,'frozen':verify()})
