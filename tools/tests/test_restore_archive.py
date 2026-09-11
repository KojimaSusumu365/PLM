import hashlib
import json
import os
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from restore_archive import check_file, restore, restore_original_version, safe_target, select_rows


class RestoreTests(unittest.TestCase):
    def setUp(self):
        temporary_root = str(Path(tempfile.gettempdir()).resolve())
        if os.name == 'nt' and not temporary_root.startswith('\\\\?\\'):
            temporary_root = '\\\\?\\' + temporary_root
        self.temp = tempfile.TemporaryDirectory(dir=temporary_root)
        self.root = Path(self.temp.name)
        self.cache = self.root / 'assets'
        self.cache.mkdir()
        self.output = self.root / 'restored'
        self.payload = b'original bytes\r\n\x00\xff'
        self.sha = hashlib.sha256(self.payload).hexdigest()
        self.member = 'blobs/' + self.sha[:2] + '/' + self.sha
        self.archive = self.cache / 'payload.zip'
        with zipfile.ZipFile(self.archive, 'w') as z:
            z.writestr(self.member, self.payload)
        self.assets = {'payload.zip': {'name': 'payload.zip', 'bytes': self.archive.stat().st_size,
            'sha256': hashlib.sha256(self.archive.read_bytes()).hexdigest()}}
        self.row = dict(scope='outputs', path='PLM-test-v0.1/example.bin', bytes=len(self.payload),
                        sha256=self.sha, asset='payload.zip', member=self.member, version='PLM-test-v0.1')

    def tearDown(self):
        self.temp.cleanup()

    def test_restore_preserves_bytes_and_duplicate_paths(self):
        second = {**self.row, 'scope': 'work'}
        self.assertEqual(restore([self.row, second], self.assets, self.output, self.cache), 2)
        self.assertEqual((self.output / 'work' / self.row['path']).read_bytes(), self.payload)
        self.assertEqual(restore([self.row, second], self.assets, self.output, self.cache), 2)

    def test_conflicting_existing_file_is_not_overwritten(self):
        destination = safe_target(self.output, 'outputs/' + self.row['path'])
        destination.parent.mkdir(parents=True)
        destination.write_bytes(b'user data')
        with self.assertRaises(ValueError):
            restore([self.row], self.assets, self.output, self.cache)
        self.assertEqual(destination.read_bytes(), b'user data')

    def test_corrupt_asset_rejected(self):
        self.archive.write_bytes(b'corrupt')
        with self.assertRaises(ValueError):
            restore([self.row], self.assets, self.output, self.cache)

    def test_wrong_blob_digest_rejected(self):
        with self.assertRaises(ValueError):
            restore([{**self.row, 'sha256': '0' * 64}], self.assets, self.output, self.cache)

    def test_direct_asset(self):
        row = {**self.row, 'member': None, 'bytes': self.assets['payload.zip']['bytes'],
               'sha256': self.assets['payload.zip']['sha256']}
        restore([row], self.assets, self.output, self.cache, version='PLM-test-v0.1')
        check_file(self.output / row['path'], row)

    def test_path_traversal_and_absolute_paths_rejected(self):
        for name in ['../x', '/tmp/x', 'C:/x', 'a/../../b', 'a\\b', '.', 'a//b']:
            with self.subTest(name=name), self.assertRaises(ValueError):
                safe_target(self.output, name)

    def test_missing_scope_and_version_rejected(self):
        self.assertEqual(select_rows([self.row], 'PLM-test-v0.1', None), [self.row])
        with self.assertRaises(ValueError):
            select_rows([self.row], 'missing', None)
        with self.assertRaises(ValueError):
            select_rows([self.row], None, 'inputs')

    def test_missing_asset_rejected(self):
        with self.assertRaises(FileNotFoundError):
            restore([self.row], self.assets, self.output, self.root / 'absent')

    def test_windows_length_independent_restore(self):
        row = {**self.row, 'path': '/'.join(['x' * 60] * 5) + '/example.bin'}
        restore([row], self.assets, self.output, self.cache)
        check_file(safe_target(self.output, 'outputs/' + row['path']), row)

    def test_original_version_zip_fast_path(self):
        with zipfile.ZipFile(self.archive, 'w') as z:
            z.writestr(self.row['path'], self.payload)
        self.assets['payload.zip'].update(bytes=self.archive.stat().st_size,
            sha256=hashlib.sha256(self.archive.read_bytes()).hexdigest())
        manifests = self.root / 'manifests'
        manifests.mkdir()
        (manifests / 'versions.json').write_text(json.dumps([{
            'name': self.row['version'], 'original_zip_asset': 'payload.zip'}]))
        count = restore_original_version(self.root, [self.row], self.assets, self.output,
            self.cache, False, self.row['version'])
        self.assertEqual(count, 1)
        check_file(self.output / self.row['path'], self.row)

    def test_original_version_zip_missing_snapshot_member_falls_back(self):
        manifests = self.root / 'manifests'
        manifests.mkdir()
        (manifests / 'versions.json').write_text(json.dumps([{
            'name': self.row['version'], 'original_zip_asset': 'payload.zip'}]))
        result = restore_original_version(self.root, [self.row], self.assets, self.output,
            self.cache, False, self.row['version'])
        self.assertIsNone(result)


if __name__ == '__main__':
    unittest.main()
