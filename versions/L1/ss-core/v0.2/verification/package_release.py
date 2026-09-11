"""Seal this release, create an exclusive ZIP, validate CRC and extract/compare bytes."""
import argparse
import json
import sys
import zipfile
from pathlib import Path,PurePosixPath

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from evaluation.integrity import sha,write,verify,preserve

def main(destination):
    frozen=verify()
    preservation=preserve()
    assert (ROOT/'verification/VERIFY.json').exists()
    files={p.relative_to(ROOT).as_posix():sha(p) for p in sorted(ROOT.rglob('*')) if p.is_file()}
    assert 'RELEASE_MANIFEST.json' not in files
    assert not any('__pycache__' in p or p.endswith('.pyc') for p in files)
    write(ROOT/'RELEASE_MANIFEST.json',{'files':files,'frozen_digest':frozen,
        'note':'File integrity and primary experimental acceptance do not imply immunity to shared corruption or false teachers.'})
    archive=ROOT.with_name(ROOT.name+'.zip')
    with zipfile.ZipFile(archive,'x',compression=zipfile.ZIP_DEFLATED,compresslevel=9) as z:
        for p in sorted(ROOT.rglob('*')):
            if p.is_file():z.write(p,ROOT.name+'/'+p.relative_to(ROOT).as_posix())
    destination=Path(destination).resolve()
    destination.mkdir(parents=True,exist_ok=False)
    with zipfile.ZipFile(archive) as z:
        assert z.testzip() is None
        names=z.namelist()
        assert len(names)==len(set(names))==len(files)+1
        for name in names:
            parts=PurePosixPath(name).parts
            assert parts[0]==ROOT.name and '..' not in parts and '\\' not in name and ':' not in name
            target=(destination/Path(*parts)).resolve()
            assert target.is_relative_to(destination)
        z.extractall(destination)
    extracted=destination/ROOT.name
    expected={p.relative_to(ROOT).as_posix():sha(p) for p in ROOT.rglob('*') if p.is_file()}
    actual={p.relative_to(extracted).as_posix():sha(p) for p in extracted.rglob('*') if p.is_file()}
    assert expected==actual
    record={'passed':True,'zip':str(archive),'zip_bytes':archive.stat().st_size,'zip_sha256':sha(archive),
        'archive_files':len(expected),'crc_passed':True,'all_extracted_bytes_equal':True,
        'extracted_root':str(extracted),'frozen_digest':frozen,'preservation':preservation}
    write(destination/'PACKAGE.json',record)
    print(json.dumps(record,indent=2),flush=True)

if __name__=='__main__':
    p=argparse.ArgumentParser()
    p.add_argument('--extract-to',required=True)
    main(p.parse_args().extract_to)
