"""Make a fresh release ZIP; refuses overwrite and validates extraction targets."""
import argparse
import hashlib
import json
from pathlib import Path
import zipfile

ROOT = Path(__file__).resolve().parents[1]

def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()

def run(archive, extraction, record):
    archive, extraction, record = map(Path, (archive, extraction, record))
    assert not archive.exists() and not extraction.exists() and not record.exists()
    files = sorted(p for p in ROOT.rglob('*') if p.is_file())
    assert not any('__pycache__' in p.parts or p.suffix == '.pyc' for p in files)
    manifest = {p.relative_to(ROOT).as_posix(): sha(p) for p in files}
    with (ROOT/'verification/MANIFEST.json').open('x', encoding='utf-8') as f:
        f.write(json.dumps(manifest, ensure_ascii=False, sort_keys=True)+'\n')
    files = sorted(p for p in ROOT.rglob('*') if p.is_file())
    with zipfile.ZipFile(archive, 'x', compression=zipfile.ZIP_DEFLATED, compresslevel=6) as z:
        for p in files:
            z.write(p, ROOT.name+'/'+p.relative_to(ROOT).as_posix())
    with zipfile.ZipFile(archive) as z:
        assert z.testzip() is None
        extraction.mkdir(parents=True, exist_ok=False)
        destination = extraction.resolve()
        for name in z.namelist():
            assert (destination/name).resolve().is_relative_to(destination)
        z.extractall(extraction)
    extracted = extraction/ROOT.name
    original = {p.relative_to(ROOT).as_posix(): sha(p) for p in files}
    unpacked = {p.relative_to(extracted).as_posix(): sha(p) for p in extracted.rglob('*') if p.is_file()}
    assert original == unpacked
    result = {'zip': str(archive.resolve()), 'bytes': archive.stat().st_size, 'sha256': sha(archive),
              'files': len(files), 'crc_passed': True, 'all_extracted_bytes_identical': True,
              'extracted_release': str(extracted.resolve())}
    with record.open('x', encoding='utf-8') as f:
        f.write(json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2)+'\n')
    print(json.dumps(result, ensure_ascii=False))

if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('--archive', required=True)
    p.add_argument('--extraction', required=True)
    p.add_argument('--record', required=True)
    a = p.parse_args()
    run(a.archive, a.extraction, a.record)
