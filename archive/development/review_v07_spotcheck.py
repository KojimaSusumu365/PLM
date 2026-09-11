"""Read-only spot checks of received review claims against the released artifacts.

Does not execute attached scripts, retrain saved models in place, or edit releases.
Only writes its new diagnostic JSON under work/.
"""
import hashlib
import json
from pathlib import Path
import sys
import zipfile
import numpy as np

WORK = Path(__file__).resolve().parent
OUTPUTS = WORK.parent / 'outputs'
V07 = OUTPUTS / 'PLM-L1-v0.7'
V08 = OUTPUTS / 'PLM-L1-v0.8'
sys.path.insert(0, str(V07))
sys.path.append(str(V08))
from plm_l1_v06.training import fit
from plm_l1_v06.features import observations
from plm_l1_v06.projection import dependency_leaves
from plm_l1_v06.algebra import canonical
from plm_l1_v06.banked import FreshBook, key_code, fit_banked
from plm_l1_v06.runtime import Model
from plm_l1_v07.runtime import EventModel
from plm_l1_v08.runtime import TemporalModel
from evaluation_support import data, interpret, text_goal


def sha(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


report = {'scope': 'Targeted checks only; not a rerun of all reviewer experiments or a cross-platform test.',
          'python': sys.version, 'numpy': np.__version__}
archives = {}
for root in (V07, V08):
    archive = root.with_suffix('.zip')
    # Version names contain dots, so replacing suffix is not appropriate.
    archive = OUTPUTS / (root.name + '.zip')
    with zipfile.ZipFile(archive) as z:
        prefix = root.name + '/'
        files = json.loads(z.read(prefix + 'RELEASE_MANIFEST.json'))['files']
        actual = {p.filename[len(prefix):]: hashlib.sha256(z.read(p)).hexdigest()
                  for p in z.infolist() if p.filename.startswith(prefix) and not p.is_dir()
                  and p.filename != prefix + 'RELEASE_MANIFEST.json'}
        current_component = [n for n in actual if n.startswith('plm_l1_v06/') and n.endswith('.py')]
        archives[root.name] = {'sha256': sha(archive), 'archive_files': len(z.namelist()),
                              'manifest_files': len(files), 'manifest_all_equal': actual == files,
                              'root_component_python_files': len(current_component),
                              'crc_valid': z.testzip() is None}
report['archives'] = archives
print(json.dumps({'archives': archives}), flush=True)

train, lex, ev = data('folds/object_negative/train'), data('lexicon'), data('evaluation')
saved = Model.load(V07 / 'results/model/component')
table = {name: dependency_leaves(rows, True) for name, rows in observations(train, lex).items()}
report['associations'] = {'counts': {n: len(rows) for n, rows in table.items()},
                          'total': sum(map(len, table.values())),
                          'canonical_table_bytes': len(canonical(table).encode('utf-8')),
                          'phase_block_bytes': sum(len(b.blob) for m in saved.memories.values() for b in m.blocks),
                          'budget_comparison_limit': 'Serialized table versus phase blocks, not full runtime RAM or latency.'}
bytext = {p['text']: p for p in train}
six_texts = ['太郎が花子を助けた。', '花子を太郎が助けた。', '太郎が花子を助けなかった。',
             'もし太郎が花子を助けたら。', 'もし花子を太郎が助けたら。', 'もし太郎が花子を助けなかったら。']
six = [bytext[text] for text in six_texts]
small = fit(six, lex, seed='banked-evaluation-0')
correct_read = correct_generate = 0
for row in ev:
    read = small.read(row['text'])
    correct_read += int(read['status'] == 'read' and small.recover(read['packet'])['meaning'] == row['meaning'])
    for goal in ('subject', 'object'):
        out = small.generate(small.encode(row['meaning']), goal)
        correct_generate += int(out['status'] == 'generated' and interpret(out['text']) == row['meaning'] and text_goal(out['text']) == goal)
report['six_examples'] = {'pairs': len(six), 'initial_lexicon_retained': True,
                          'read_exact': correct_read, 'read_requests': len(ev),
                          'generate_exact': correct_generate, 'generate_requests': 2 * len(ev),
                          'associations': sum(r['projected_contexts'] for r in small.meta['statistics'].values()),
                          'same_phase_blocks_as_432_pairs': all([b.blob for b in small.memories[n].blocks] == [b.blob for b in m.blocks] for n, m in saved.memories.items()),
                          'not_a_proof_that_six_is_the_minimum': True}
print(json.dumps({'six_examples': report['six_examples']}), flush=True)

models = [('v0.7', EventModel.load(V07 / 'results/model'), '太郎が花子を助けた。花子が健太を褒めた。'),
          ('v0.8', TemporalModel.load(V08 / 'results/model'), '太郎が花子を助けた。その後、花子が健太を褒めた。')]
checks = {}
for name, model, text in models:
    read = model.read(text)
    assert read['status'] == 'read'
    packet = read['packet']
    negative = dict(packet, real=[-v for v in packet['real']], imag=[-v for v in packet['imag']])
    recovered = model.recover(negative)
    same = model.read(text.replace('太郎が花子を', '太郎が太郎を'))
    checks[name] = {'negative_signal_status': recovered['status'], 'negative_signal_reason': recovered.get('reason'),
                    'same_entity_runtime_read': same['status']}
try:
    repeated = {'text': '太郎が太郎を助けた。', 'meaning': {'subject': 'entity:太郎', 'object': 'entity:太郎',
                'predicate': 'predicate:help', 'polarity': 'polarity:positive', 'modality': 'modality:asserted'}}
    fit([repeated] + six, lex)
    report['same_entity_training'] = 'accepted'
except ValueError as e:
    report['same_entity_training'] = str(e)
report['runtime_checks'] = checks

memory, _ = fit_banked([({'a': 'A', 'b': 'B'}, 'yes')], 8192, 'review-key-check', partial=False, mode='single')
try:
    report['missing_key_field_api'] = memory.recall({'a': 'A'})
except ValueError as e:
    report['missing_key_field_api'] = str(e)
book = FreshBook(8192, 'review-key-check')
complete = key_code(book, {'a': 'A', 'b': 'B'})
partial = key_code(book, {'a': 'A'})
report['partial_key_not_automatically_close'] = float(np.vdot(complete, partial).real / 8192)
report['no_released_source_or_model_writes'] = True
with (WORK / 'review_v07_spotcheck.json').open('x', encoding='utf-8') as stream:
    stream.write(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
print(json.dumps(report, ensure_ascii=False, indent=2))
