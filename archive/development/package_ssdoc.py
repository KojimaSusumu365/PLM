"""Seal, archive, safely extract, and verify this release; never overwrite outputs."""
import json
import sys
import zipfile
from pathlib import Path

WORK = Path(__file__).resolve().parent
ROOT = WORK.parent / 'outputs/PLM-L1-SS-doc-v0.1'
sys.path.insert(0, str(ROOT))
from evaluation.integrity import sha, read, write, verify


def main():
    digest = verify()
    assert read(ROOT / 'verification/DOCUMENT_QA.json')['passed']
    archive = ROOT.parent / (ROOT.name + '.zip')
    extracted = WORK / 'ssdoc-zip-extracted'
    assert not archive.exists() and not extracted.exists()
    allfiles = sorted(p for p in ROOT.rglob('*') if p.is_file())
    assert not any('__pycache__' in p.parts or p.suffix == '.pyc' for p in allfiles)
    assert not (ROOT / 'RELEASE_MANIFEST.json').exists()
    files = {p.relative_to(ROOT).as_posix(): sha(p) for p in allfiles}
    write(ROOT / 'RELEASE_MANIFEST.json', {
        'schema': 'plm-ssdoc-release-manifest-v1', 'files': files,
        'frozen_source_digest': digest, 'eligible_for_inference': False,
        'note': 'Every release file except this manifest. ZIP hash and post-extraction checks recorded outside the release.'})
    allfiles = sorted(p for p in ROOT.rglob('*') if p.is_file())
    with zipfile.ZipFile(archive, 'x', zipfile.ZIP_DEFLATED, compresslevel=6) as z:
        for p in allfiles:
            z.write(p, ROOT.name + '/' + p.relative_to(ROOT).as_posix())
    extracted.mkdir()
    with zipfile.ZipFile(archive) as z:
        assert z.testzip() is None
        names = z.namelist()
        assert len(names) == len(set(names)) == len(allfiles)
        for item in z.infolist():
            target = (extracted / item.filename).resolve()
            assert target.is_relative_to(extracted.resolve())
            assert not item.is_dir() and item.filename.startswith(ROOT.name + '/')
        z.extractall(extracted)
    eroot = extracted / ROOT.name
    exact = {p.relative_to(eroot).as_posix(): sha(p) for p in eroot.rglob('*') if p.is_file()}
    wanted = {p.relative_to(ROOT).as_posix(): sha(p) for p in allfiles}
    assert exact == wanted
    manifest = read(eroot / 'RELEASE_MANIFEST.json')
    assert {k: v for k, v in exact.items() if k != 'RELEASE_MANIFEST.json'} == manifest['files']
    summary = {'passed': True, 'archive': str(archive), 'sha256': sha(archive),
               'archive_bytes': archive.stat().st_size, 'file_count_including_manifest': len(allfiles),
               'manifest_file_count': len(files), 'uncompressed_bytes': sum(p.stat().st_size for p in allfiles),
               'crc_ok': True, 'extracted_root': str(eroot), 'all_extracted_files_byte_identical': True,
               'manifest_sha256': sha(ROOT / 'RELEASE_MANIFEST.json'), 'eligible_for_inference': False}
    write(WORK / 'ssdoc-package.json', summary)
    print(json.dumps(summary, indent=2))


if __name__ == '__main__':
    main()
