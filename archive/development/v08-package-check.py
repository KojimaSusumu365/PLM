"""Verify actual archive extraction, full release checks and ordinary CLI."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import zipfile

WORK = Path(__file__).resolve().parent
OUTPUTS = WORK.parent / 'outputs'
SOURCE = OUTPUTS / 'PLM-L1-v0.8'
ARCHIVE = OUTPUTS / 'PLM-L1-v0.8.zip'
# Keep extraction short: recursively preserved historical releases approach MAX_PATH.
EXTRACT = WORK / 'v8x'
VERIFY = WORK / 'v08-package-verification'
CLI = WORK / 'v08-package-cli'


def sha(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def snapshot(folder):
    return {p.relative_to(folder).as_posix(): sha(p) for p in folder.rglob('*') if p.is_file()}


def write(path, value):
    with path.open('x', encoding='utf-8') as stream:
        stream.write(json.dumps(value, ensure_ascii=False, indent=2) + '\n')


assert not EXTRACT.exists() and not VERIFY.exists() and not CLI.exists()
assert EXTRACT.resolve().is_relative_to(WORK.resolve())
expected = snapshot(SOURCE)
archive_hash = sha(ARCHIVE)
EXTRACT.mkdir()
with zipfile.ZipFile(ARCHIVE) as archive:
    names = [member.filename for member in archive.infolist()]
    assert len(set(names)) == len(names) == len(expected)
    assert set(names) == {SOURCE.name + '/' + name for name in expected}
    for name in names:
        assert (EXTRACT / name).resolve().is_relative_to(EXTRACT.resolve())
    assert archive.testzip() is None
    archive.extractall(EXTRACT)
extracted = EXTRACT / SOURCE.name
assert snapshot(extracted) == expected
env = dict(os.environ, OPENBLAS_NUM_THREADS='1', PYTHONIOENCODING='utf-8',
           PYTHONDONTWRITEBYTECODE='1', PYTHONNOUSERSITE='1')
env.pop('PYTHONPATH', None)
execution = subprocess.run([sys.executable, '-B', 'verify_release.py', '--out', str(VERIFY)],
                           cwd=extracted, env=env, capture_output=True, text=True,
                           encoding='utf-8', timeout=1200)
with (WORK / 'v08-package-verification.log').open('x', encoding='utf-8') as stream:
    stream.write(execution.stdout + execution.stderr)
if execution.returncode:
    raise ValueError('ZIP verification failed: ' + execution.stdout + execution.stderr)
print('Actual ZIP: all tests, fixed acceptance checks and isolation checks passed.', flush=True)
CLI.mkdir()
commands = []


def cli(arguments, expected_code=0):
    r = subprocess.run([sys.executable, '-B', '-m', 'plm_l1_v08', *arguments],
                       cwd=extracted, env=env, capture_output=True, text=True,
                       encoding='utf-8', timeout=60)
    assert r.returncode == expected_code, r.stdout + r.stderr
    out = json.loads(r.stdout)
    assert out['eligible_for_inference'] is False
    commands.append({'arguments': arguments, 'exit_code': r.returncode, 'output': out})
    return out


model = str(extracted / 'results' / 'model')
packet = str(CLI / 'read-packet.json')
text = '太郎が花子を助けた。その後、花子が健太を褒めた。'
assert cli(['read', '--model', model, '--text', text, '--out', packet])['status'] == 'read'
meaning = cli(['recover', '--model', model, '--packet', packet])['meaning']
assert meaning['temporal'] == {'kind': 'before', 'source': 'event:0', 'target': 'event:1'}
assert cli(['generate', '--model', model, '--packet', packet, '--order', 'reverse',
            '--goals', 'subject', 'subject'])['text'] == '花子が健太を褒めた。その前に、太郎が花子を助けた。'
assert cli(['generate', '--model', model, '--packet', packet, '--order', 'reverse',
            '--goals', 'object', 'subject'])['text'] == '健太を花子が褒めた。その前に、太郎が花子を助けた。'
direct = str(CLI / 'direct-packet.json')
assert cli(['encode', '--model', model, '--meaning', str(extracted / 'examples' / 'MEANING.json'),
            '--out', direct])['status'] == 'encoded'
assert cli(['generate', '--model', model, '--packet', direct, '--order', 'reverse',
            '--goals', 'subject', 'object'])['text'] == '花子が健太を褒めた。その前に、花子を太郎が助けた。'
unknown = str(CLI / 'unknown-packet.json')
assert cli(['read', '--model', model, '--text', '太郎が花子を助けた。花子が健太を褒めた。',
            '--out', unknown])['status'] == 'read'
assert cli(['generate', '--model', model, '--packet', unknown, '--order', 'reverse'])['text'] == '花子が健太を褒めた。太郎が花子を助けた。'
unsupported = CLI / 'unsupported-must-not-exist.json'
assert cli(['read', '--model', model, '--text', '太郎が花子を助けた。だから、花子が健太を褒めた。',
            '--out', str(unsupported)], expected_code=2)['status'] == 'abstain'
assert not unsupported.exists()
packet_hash_before_duplicate = sha(Path(packet))
assert cli(['read', '--model', model, '--text', text, '--out', packet], expected_code=2)['status'] == 'abstain'
assert sha(Path(packet)) == packet_hash_before_duplicate
check = subprocess.run([sys.executable, '-B', '-c', 'from evaluate import verify_freeze; print(verify_freeze())'],
                       cwd=extracted, env=env, capture_output=True, text=True,
                       encoding='utf-8', timeout=60)
assert check.returncode == 0, check.stderr
assert snapshot(extracted) == expected and snapshot(SOURCE) == expected
assert sha(ARCHIVE) == archive_hash
write(CLI / 'CLI_VERIFICATION.json', {'status': 'passed', 'commands': commands})
record = json.loads((VERIFY / 'VERIFICATION.json').read_text(encoding='utf-8'))
assert sum(record['test_counts'].values()) == 441 and record['acceptance_checks'] == 456
assert record['release_manifest_checked'] and not record['preflight_boundary_only']
record.update(archive=ARCHIVE.name, archive_sha256=archive_hash, archive_bytes=ARCHIVE.stat().st_size,
              archive_files=len(expected), extracted_bytes_equal=True, source_and_archive_unchanged=True,
              temporal_read_reverse_generate_cli_passed=True, temporal_direct_encode_generate_cli_passed=True,
              unknown_relation_not_invented=True, unsupported_connective_abstained=True,
              no_overwrite_cli_passed=True, source_freeze_checked_after_cli=True,
              cli_verification={'status': 'passed', 'commands': commands})
write(OUTPUTS / 'PLM-L1-v0.8-VERIFICATION.json', record)
md = f'''# PLM-L1 v0.8 配布ZIPの実展開検証

実際の `PLM-L1-v0.8.zip` を新しい短いディレクトリへ展開して検証し、全項目を通過した。

- ファイル数：{len(expected)}。ZIP CRC・ファイル一覧・展開後の全バイトが配布元と一致。
- テスト：441件（v0.8の60件＋v0.7以前の381件）。固定受入：456/456。
- 本体・同梱過去版のソース凍結と全配布マニフェストを照合。
- 432一文対＋216時間関係対から、読解器・評価oracle・旧重みなしでモデルを再学習し一致。
- 新旧読解器・学習入口・訓練コーパスのない生成環境で、数値パケットだけを渡す6往復が一致。
- 通常CLIで読解・意味回復・提示順反転生成・直接意味符号化・文内語順変更を確認。
- 関係不明から時間関係を創作せず、未対応の「だから、」は保留。既存出力の上書きも拒否。
- CLI実行後も配布元・展開物・ZIPの全バイトが変わらないことを確認。

全数値評価は配布前に同じ凍結条件で2回実行し、結果JSON・報告・モデル情報・全重み配列が一致した。ZIP実展開検証では保存結果を再採点し、全テストと隔離境界・CLIを実行したもので、3回目の全数値評価ではない。

ZIP：{ARCHIVE.stat().st_size:,} bytes。SHA-256：

`{archive_hash}`

詳細は `PLM-L1-v0.8-VERIFICATION.json`。六つずつの関係対応を学ぶ限定実証であり、自由な時間表現・全SS学習・P1/S1接続・R1推論を達成したという意味ではない。
'''
with (OUTPUTS / 'PLM-L1-v0.8-VERIFICATION.md').open('x', encoding='utf-8') as stream:
    stream.write(md)
print(json.dumps({k: record[k] for k in ('status', 'archive', 'archive_sha256', 'archive_bytes',
                                       'archive_files', 'acceptance_checks', 'test_counts')}, indent=2))
