"""Verify browsing copies, manifest coverage, assets, and optional restored data."""
import argparse
import json
import zipfile
from pathlib import Path

from restore_archive import REPOSITORY, check_file, hash_stream, load_metadata, safe_target


def verify(repository=REPOSITORY, asset_dir=None, all_blobs=False, restored_root=None):
    rows, assets = load_metadata(repository)
    summary = json.loads((repository / 'manifests/summary.json').read_text(encoding='utf-8'))
    assert len(rows) == summary['source_files']
    assert sum(r['bytes'] for r in rows) == summary['source_bytes']
    unique = {r['sha256']: r for r in rows}
    assert len(unique) == summary['unique_blobs']
    assert sum(r['bytes'] for r in unique.values()) == summary['unique_bytes']
    copies = [r for r in rows if 'git_path' in r]
    assert len(copies) == summary['browseable_original_files']
    for row in copies:
        check_file(safe_target(repository, row['git_path']), row)
    versions = json.loads((repository / 'manifests/versions.json').read_text(encoding='utf-8'))
    assert len(versions) == summary['versions']
    assert versions[0]['name'] == 'PLM-C0-v0.1'
    assert versions[-1]['name'] == 'PLM-L1-SS-core-v0.4'
    for v in versions:
        members = [r for r in rows if r.get('version') == v['name']]
        assert len(members) == v['files']
        assert sum(r['bytes'] for r in members) == v['bytes']
        assert assets[v['original_zip_asset']]['sha256'] == v['zip_sha256']
    checked_assets = 0
    checked_blobs = 0
    if all_blobs and not asset_dir:
        raise ValueError('--all-blobs requires --asset-dir')
    if asset_dir:
        for asset in assets.values():
            check_file(safe_target(asset_dir, asset['name']), asset)
            checked_assets += 1
        print(f'Asset hashes verified: {checked_assets}', flush=True)
    if all_blobs:
        grouped = {}
        for sha, row in unique.items():
            grouped.setdefault(row['asset'], []).append(row)
        for name, members in sorted(grouped.items()):
            payload = asset_dir / name
            if members[0].get('member') is None:
                for row in members:
                    check_file(payload, row)
                    checked_blobs += 1
            else:
                with zipfile.ZipFile(payload) as archive:
                    expected = {r['member'] for r in members}
                    assert set(archive.namelist()) == expected, f'Unexpected/missing ZIP members: {name}'
                    assert len(archive.namelist()) == len(expected)
                    for row in members:
                        info = archive.getinfo(row['member'])
                        assert info.file_size == row['bytes']
                        with archive.open(info) as source:
                            assert hash_stream(source) == row['sha256'], row['path']
                        checked_blobs += 1
            print(f'Unique blobs verified: {checked_blobs}/{len(unique)}', flush=True)
        assert checked_blobs == len(unique)
    restored = 0
    if restored_root:
        expected_paths = {r['scope'] + '/' + r['path'] for r in rows}
        actual_paths = {p.relative_to(restored_root).as_posix() for p in restored_root.rglob('*') if p.is_file()}
        assert actual_paths == expected_paths, 'Restored file set differs'
        for row in rows:
            check_file(safe_target(restored_root, row['scope'] + '/' + row['path']), row)
            restored += 1
    return dict(source_paths=len(rows), source_bytes=summary['source_bytes'],
                browseable_copies_verified=len(copies), versions_verified=len(versions),
                assets_verified=checked_assets, unique_blobs_verified=checked_blobs,
                restored_paths_verified=restored, status='passed')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--asset-dir', type=Path)
    parser.add_argument('--all-blobs', action='store_true')
    parser.add_argument('--restored-root', type=Path)
    args = parser.parse_args()
    result = verify(asset_dir=args.asset_dir, all_blobs=args.all_blobs, restored_root=args.restored_root)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
