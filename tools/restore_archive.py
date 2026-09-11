"""Restore immutable PLM files from verified release assets. Standard library only."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import urllib.request
import zipfile
from collections import defaultdict
from pathlib import Path, PurePosixPath

REPOSITORY = Path(__file__).resolve().parents[1]
RELEASE_BASE = 'https://github.com/KojimaSusumu365/PLM/releases/download/'


def sha256(path: Path) -> str:
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest() if hasattr(hashlib, 'file_digest') else hash_stream(stream)


def hash_stream(stream) -> str:
    digest = hashlib.sha256()
    while block := stream.read(1024**2):
        digest.update(block)
    return digest.hexdigest()


def relative_path(name: str) -> PurePosixPath:
    if not isinstance(name, str) or not name or '\\' in name or ':' in name or '\x00' in name:
        raise ValueError(f'Invalid relative path: {name!r}')
    parts = name.split('/')
    if any(part in ('', '.', '..') for part in parts):
        raise ValueError(f'Unsafe relative path: {name!r}')
    path = PurePosixPath(name)
    if path.is_absolute():
        raise ValueError(f'Absolute path forbidden: {name!r}')
    return path


def safe_target(root: Path, name: str) -> Path:
    rel = relative_path(name)
    root = root.resolve()
    target = root.joinpath(*rel.parts)
    if not target.resolve().is_relative_to(root):
        raise ValueError(f'Path escapes destination: {name!r}')
    if os.name == 'nt' and not str(target).startswith('\\\\?\\'):
        target = Path('\\\\?\\' + str(target))
    return target


def load_metadata(repository: Path = REPOSITORY):
    folder = repository / 'manifests'
    rows = [json.loads(line) for line in (folder / 'source-files.jsonl').read_text(encoding='utf-8').splitlines()]
    document = json.loads((folder / 'assets.json').read_text(encoding='utf-8'))
    assets = {}
    for asset in document['assets']:
        name = asset['name']
        if len(relative_path(name).parts) != 1 or name in assets:
            raise ValueError('Duplicate or invalid asset name')
        if not re.fullmatch('[0-9a-f]{64}', asset['sha256']) or asset['bytes'] < 0:
            raise ValueError('Invalid asset fingerprint')
        if asset['url'] != RELEASE_BASE + document['tag'] + '/' + name:
            raise ValueError('Unexpected asset download URL')
        assets[name] = asset
    seen = set()
    for row in rows:
        if row['scope'] not in ('outputs', 'work', 'inputs'):
            raise ValueError('Unexpected source scope')
        relative_path(row['path'])
        key = row['scope'], row['path']
        if key in seen:
            raise ValueError(f'Duplicate original path: {key}')
        seen.add(key)
        if not re.fullmatch('[0-9a-f]{64}', row['sha256']) or row['bytes'] < 0:
            raise ValueError('Invalid source fingerprint')
        if row['asset'] not in assets:
            raise ValueError('Missing source asset')
        if row.get('member') is not None:
            if row['member'] != 'blobs/' + row['sha256'][:2] + '/' + row['sha256']:
                raise ValueError('Unexpected content-addressed member path')
        if 'git_path' in row:
            relative_path(row['git_path'])
    return rows, assets


def check_file(path: Path, record: dict) -> None:
    if not path.is_file() or path.stat().st_size != record['bytes'] or sha256(path) != record['sha256']:
        raise ValueError(f'Content mismatch or missing file: {path}')


def acquire_asset(asset: dict, cache: Path, download: bool) -> Path:
    path = safe_target(cache, asset['name'])
    if path.exists():
        check_file(path, asset)
        return path
    if not download:
        raise FileNotFoundError(f'Missing {path}; obtain the release assets or use --download')
    path.parent.mkdir(parents=True, exist_ok=True)
    partial = path.with_name(path.name + '.partial')
    if partial.exists():
        raise FileExistsError(f'Incomplete previous download exists: {partial}; inspect or move it before retrying')
    print(f'Downloading {asset["name"]} ({asset["bytes"]:,} bytes)', flush=True)
    request = urllib.request.Request(asset['url'], headers={'User-Agent': 'PLM-archive-restore/1.0'})
    with urllib.request.urlopen(request, timeout=60) as response, partial.open('xb') as output:
        shutil.copyfileobj(response, output, length=1024**2)
    check_file(partial, asset)
    # Fail rather than silently replace a file created concurrently.
    if path.exists():
        raise FileExistsError(path)
    partial.rename(path)
    return path


def select_rows(rows: list[dict], version: str | None, scope: str | None):
    selected = [row for row in rows if (not version or row.get('version') == version)
                and (not scope or row['scope'] == scope)]
    if not selected:
        raise ValueError('No source files match the requested version/scope')
    return selected


def output_name(row: dict, version: str | None) -> str:
    if version:
        if not row['path'].startswith(version + '/'):
            raise ValueError('Version/source path mismatch')
        return row['path']
    return row['scope'] + '/' + row['path']


def restore(rows, assets, destination: Path, cache: Path, download=False, version=None):
    destination.mkdir(parents=True, exist_ok=True)
    by_asset = defaultdict(list)
    for row in rows:
        by_asset[row['asset']].append(row)
    restored = 0
    for name, records in sorted(by_asset.items()):
        path = acquire_asset(assets[name], cache, download)
        archive = zipfile.ZipFile(path) if any(r.get('member') for r in records) else None
        try:
            if archive:
                names = archive.namelist()
                if len(names) != len(set(names)):
                    raise ValueError(f'Duplicate ZIP member: {name}')
            for row in records:
                target = safe_target(destination, output_name(row, version))
                if target.exists():
                    check_file(target, row)
                else:
                    target.parent.mkdir(parents=True, exist_ok=True)
                    # Re-check after creating parents (do not follow escaping symlinks).
                    target = safe_target(destination, output_name(row, version))
                    source = archive.open(row['member']) if archive else path.open('rb')
                    with source, target.open('xb') as output:
                        shutil.copyfileobj(source, output, length=1024**2)
                    check_file(target, row)
                    if 'mtime_ns' in row:
                        os.utime(target, ns=(row['mtime_ns'], row['mtime_ns']))
                restored += 1
        finally:
            if archive:
                archive.close()
        print(f'Verified/restored {restored:,}/{len(rows):,} files', flush=True)
    return restored


def restore_directories(repository, destination, version, scope):
    directories = json.loads((repository / 'manifests/source-directories.json').read_text(encoding='utf-8'))
    for record in directories:
        if scope and record['scope'] != scope:
            continue
        if version:
            if record['path'] != version and not record['path'].startswith(version + '/'):
                continue
            if version == 'PLM-C0-v0.1' and record['scope'] != 'work':
                continue
            if version != 'PLM-C0-v0.1' and record['scope'] != 'outputs':
                continue
            name = record['path']
        else:
            name = record['scope'] + '/' + record['path']
        safe_target(destination, name).mkdir(parents=True, exist_ok=True)


def restore_original_version(repository, rows, assets, destination, cache, download, version):
    """Use the compact original ZIP when it covers the full snapshot exactly."""
    versions = json.loads((repository / 'manifests/versions.json').read_text(encoding='utf-8'))
    item = next(v for v in versions if v['name'] == version)
    asset = assets[item['original_zip_asset']]
    path = acquire_asset(asset, cache, download)
    with zipfile.ZipFile(path) as archive:
        names = archive.namelist()
        if len(names) != len(set(names)):
            raise ValueError('Duplicate ZIP member in original release')
        required = {row['path'] for row in rows}
        if not required.issubset(names):
            print('Original ZIP differs from the retained snapshot layout; using preservation assets.', flush=True)
            return None
        for row in rows:
            target = safe_target(destination, row['path'])
            if target.exists():
                check_file(target, row)
                continue
            info = archive.getinfo(row['path'])
            if info.file_size != row['bytes']:
                raise ValueError(f'Original ZIP member size mismatch: {row["path"]}')
            target.parent.mkdir(parents=True, exist_ok=True)
            target = safe_target(destination, row['path'])
            with archive.open(info) as source, target.open('xb') as output:
                shutil.copyfileobj(source, output, length=1024**2)
            check_file(target, row)
            if 'mtime_ns' in row:
                os.utime(target, ns=(row['mtime_ns'], row['mtime_ns']))
    return len(rows)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group()
    group.add_argument('--version', help='Exact version name, e.g. PLM-L1-SS-core-v0.4')
    group.add_argument('--scope', choices=['outputs', 'work', 'inputs'])
    parser.add_argument('--dest', type=Path, required=True)
    parser.add_argument('--asset-dir', type=Path, default=REPOSITORY / '.plm-assets')
    parser.add_argument('--download', action='store_true', help='Download missing assets from this public GitHub release')
    args = parser.parse_args()
    rows, assets = load_metadata()
    selected = select_rows(rows, args.version, args.scope)
    count = None
    if args.version:
        count = restore_original_version(REPOSITORY, selected, assets, args.dest, args.asset_dir, args.download, args.version)
    if count is None:
        count = restore(selected, assets, args.dest, args.asset_dir, args.download, args.version)
    restore_directories(REPOSITORY, args.dest, args.version, args.scope)
    print(json.dumps({'verified_files': count, 'bytes': sum(r['bytes'] for r in selected),
                      'destination': str(args.dest.resolve())}, ensure_ascii=False))


if __name__ == '__main__':
    main()
