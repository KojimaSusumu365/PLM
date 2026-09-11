"""Exclusive archive creation and path-safe real extraction of the sealed release."""
import json
import sys
import zipfile
from pathlib import Path
WORK = Path(__file__).resolve().parent
ROOT = WORK.parent / 'outputs/PLM-L1-SS-doc-v0.2'
sys.path.insert(0, str(ROOT))
from evaluation.integrity import read, write, sha, verify


def main():
    frozen = verify()
    assert read(ROOT / 'verification/DOCUMENT_QA.json')['passed']
    archive = ROOT.parent / (ROOT.name + '.zip')
    extracted = WORK / 'ssdoc02-zip-extracted'
    assert not archive.exists() and not extracted.exists()
    source = sorted(p for p in ROOT.rglob('*') if p.is_file())
    assert not any('__pycache__' in p.parts or p.suffix == '.pyc' for p in source)
    assert not (ROOT / 'RELEASE_MANIFEST.json').exists()
    hashes = {p.relative_to(ROOT).as_posix(): sha(p) for p in source}
    write(ROOT / 'RELEASE_MANIFEST.json', {'files': hashes, 'frozen_source_digest': frozen,
          'note': 'All files except this manifest; post-ZIP verification stays outside the archive.', 'eligible_for_inference': False})
    source = sorted(p for p in ROOT.rglob('*') if p.is_file())
    with zipfile.ZipFile(archive, 'x', zipfile.ZIP_DEFLATED, compresslevel=6) as z:
        for path in source: z.write(path, ROOT.name + '/' + path.relative_to(ROOT).as_posix())
    extracted.mkdir()
    with zipfile.ZipFile(archive) as z:
        assert z.testzip() is None
        names = z.namelist(); assert len(names) == len(set(names)) == len(source)
        for name in names:
            assert name.startswith(ROOT.name + '/') and (extracted / name).resolve().is_relative_to(extracted.resolve())
        z.extractall(extracted)
    eroot = extracted / ROOT.name
    actual = {p.relative_to(eroot).as_posix(): sha(p) for p in eroot.rglob('*') if p.is_file()}
    expected = {p.relative_to(ROOT).as_posix(): sha(p) for p in source}
    assert actual == expected
    record = {'passed': True, 'archive': str(archive), 'archive_sha256': sha(archive), 'archive_bytes': archive.stat().st_size,
              'uncompressed_bytes': sum(p.stat().st_size for p in source), 'file_count_including_manifest': len(source),
              'manifest_files': len(hashes), 'manifest_sha256': sha(ROOT / 'RELEASE_MANIFEST.json'), 'crc_ok': True,
              'all_extracted_files_identical': True, 'extracted_root': str(eroot), 'eligible_for_inference': False}
    write(WORK / 'ssdoc02-package.json', record)
    print(json.dumps(record, indent=2), flush=True)


if __name__ == '__main__': main()
