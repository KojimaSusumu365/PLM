import hashlib
import json
from pathlib import Path

root = Path(__file__).resolve().parent.parent
archive = root/'outputs/PLM-L1-SS-core-v0.3.zip'
zip_record = json.loads((root/'outputs/PLM-L1-SS-core-v0.3-ZIP.json').read_text(encoding='utf-8'))
verified = json.loads((root/'work/sscore03-zip-verifier/VERIFY.json').read_text(encoding='utf-8'))
tests = json.loads((root/'work/sscore03-zip-verifier/TESTS.json').read_text(encoding='utf-8'))
actual = hashlib.sha256(archive.read_bytes()).hexdigest()
assert verified['passed'] and tests['returncode'] == 0 and actual == zip_record['sha256']
record = {'archive': zip_record, 'extracted_verification': verified,
          'extracted_tests': tests, 'final_zip_hash_rechecked': actual}
with (root/'outputs/PLM-L1-SS-core-v0.3-POSTZIP.json').open('x', encoding='utf-8') as f:
    f.write(json.dumps(record, ensure_ascii=False, sort_keys=True, indent=2)+'\n')
print(json.dumps({'passed': True, 'sha256': actual, 'files': zip_record['files'], 'manifest': verified['manifest_files']}, ensure_ascii=False))
