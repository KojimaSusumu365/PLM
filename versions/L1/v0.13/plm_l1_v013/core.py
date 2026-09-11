"""Runtime only. Unknown cells represent unlearned functions, not negative facts."""
import hashlib
import itertools
import json
from pathlib import Path
import numpy as np
from .algebra import Book, canonical, digest, require

MAX_FIELDS = 6
MAX_ORDER = 3
MAX_CANDIDATES = 41
SUPPORT_THRESHOLD = .5


def key(context, fields):
    return canonical([context[f] for f in fields])


class Model:
    def __init__(self, config, members, training):
        self.config = config
        self.members = members
        self.training = training
        self.book = Book(config['dimension'], 'v013-witness/' + config['seed'])
        self.refresh()

    def refresh(self):
        self.meta = {'schema': 'plm-dependency-memory-v013', 'config': self.config, 'training': self.training,
                     'members': [{k: v for k, v in m.items() if k != 'weights'} for m in self.members],
                     'eligible_for_inference': False}
        self.fingerprint = digest([self.meta, [hashlib.sha256(m['weights'].astype('<c16').tobytes()).hexdigest() for m in self.members]])

    def validate(self, context, complete=False):
        require(type(context) is dict and set(context) <= set(self.config['fields']), 'unknown_context_fields')
        require(all(type(v) is str and v in self.config['vocabulary'][f] for f, v in context.items()), 'unknown_field_value')
        require(not complete or set(context) == set(self.config['fields']), 'complete_context_required')

    def _recalls(self):
        # Transient batch memo, obtained from fresh memory correlations. Never saved.
        recalls = []
        labels = self.config['labels']
        for member in self.members:
            fields = member['mask']
            contexts = [dict(zip(fields, vs)) for vs in itertools.product(*(self.config['vocabulary'][f] for f in fields))]
            if self.config['backend'] == 'ss':
                vectors = np.array([self.book.vector(c, fields, 'product')[0] for c in contexts])
                scores = (vectors @ member['weights'].conj().T).real / self.config['dimension']
            else:
                scores = np.array([member['entries'].get(key(c, fields), [0] * len(labels)) for c in contexts], dtype=float)
            table = {}
            for c, row in zip(contexts, scores):
                hits = [y for y, s in zip(labels, row) if s >= SUPPORT_THRESHOLD]
                table[key(c, fields)] = {'value': hits[0] if len(hits) == 1 else None, 'hits': hits,
                                        'scores': [float(s) for s in row]}
            recalls.append(table)
        return recalls

    def _predict(self, context, recalls):
        self.validate(context)
        labels = self.config['labels']
        possible = set()
        unknown_cells = set()
        conflicting_cells = set()
        known_by_candidate = [set() for _ in self.members]
        disagreement = False
        missing = [f for f in self.config['fields'] if f not in context]
        if not self.members:
            return {'status': 'abstain', 'value': None, 'possible_labels': labels, 'reason': 'hypothesis_family_exhausted',
                    'input_insufficient': False, 'learning_insufficient': True, 'candidate_count': 0,
                    'unknown_cells': 0, 'conflicting_cells': 0, 'dependency_disagreement': False,
                    'completion_count': 0, 'eligible_for_inference': False}
        count = 0
        for vs in itertools.product(*(self.config['vocabulary'][f] for f in missing)):
            completed = dict(context, **dict(zip(missing, vs)))
            values = []
            for i, (member, table) in enumerate(zip(self.members, recalls)):
                k = key(completed, member['mask'])
                recalled = table[k]
                value = recalled['value']
                values.append(value)
                if value is None:
                    unknown_cells.add((i, k))
                    if len(recalled['hits']) > 1:
                        conflicting_cells.add((i, k))
                else:
                    known_by_candidate[i].add(value)
            known = {v for v in values if v is not None}
            disagreement |= len(known) > 1
            possible.update(labels if None in values else known)
            count += 1
        learning = bool(unknown_cells) or disagreement
        input_missing = bool(missing) and any(len(s) > 1 for s in known_by_candidate)
        accepted = not learning and len(possible) == 1
        reason = 'accepted' if accepted else 'input_and_learning_insufficient' if learning and input_missing else 'learning_insufficient' if learning else 'input_insufficient'
        return {'status': 'accepted' if accepted else 'abstain', 'value': next(iter(possible)) if accepted else None,
                'possible_labels': sorted(possible), 'reason': reason, 'input_insufficient': input_missing,
                'learning_insufficient': learning, 'candidate_count': len(self.members), 'unknown_cells': len(unknown_cells),
                'conflicting_cells': len(conflicting_cells), 'dependency_disagreement': disagreement,
                'completion_count': count, 'eligible_for_inference': False}

    def predict_many(self, contexts):
        recalls = self._recalls()
        return [self._predict(c, recalls) for c in contexts]

    def predict(self, context):
        return self.predict_many([context])[0]

    def rank_pool(self, pool, strategy='active', seed='acquisition-0'):
        require(strategy in ('active', 'random') and type(seed) is str and 0 < len(seed) <= 80, 'invalid_acquisition_settings')
        require(type(pool) is list and len(pool) <= 4096, 'invalid_pool')
        ids = set()
        contexts = set()
        for row in pool:
            require(type(row) is dict and set(row) == {'id', 'context'}, 'pool_must_be_unlabeled')
            require(type(row['id']) is str and 0 < len(row['id']) <= 128 and row['id'] not in ids, 'invalid_pool_id')
            self.validate(row['context'], complete=True)
            k = canonical(row['context'])
            require(k not in contexts, 'duplicate_pool_context')
            ids.add(row['id'])
            contexts.add(k)
        if not self.members or not pool:
            return []
        recalls = self._recalls() if strategy == 'active' else None
        rankings = []
        for row in pool:
            if strategy == 'active':
                votes = np.zeros(len(self.config['labels']))
                unknown = 0
                known = set()
                for member, table in zip(self.members, recalls):
                    answer = table[key(row['context'], member['mask'])]['value']
                    if answer is None:
                        votes += 1. / len(votes)
                        unknown += 1
                    else:
                        votes[self.config['labels'].index(answer)] += 1.
                        known.add(answer)
                votes /= len(self.members)
                score = round(1. - float(votes @ votes), 12)
                fraction = round(unknown / len(self.members), 12)
            else:
                score = fraction = 0.
                known = set()
            rankings.append({'id': row['id'], 'context': row['context'], 'score': score,
                             'unknown_fraction': fraction, 'known_labels': sorted(known),
                             'tie': digest(['v013-acquisition', seed, row['id']])})
        rankings.sort(key=lambda r: (-r['score'], -r['unknown_fraction'], r['tie']))
        return rankings

    def select(self, pool, strategy='active', seed='acquisition-0'):
        ranked = self.rank_pool(pool, strategy, seed)
        if not ranked:
            return {'status': 'no_request', 'reason': 'hypothesis_family_exhausted' if not self.members else 'pool_exhausted', 'eligible_for_inference': False}
        first = ranked[0]
        return {'schema': 'plm-teacher-request-v013', 'model_fingerprint': self.fingerprint,
                'id': first['id'], 'context': first['context'], 'strategy': strategy, 'seed': seed,
                'diagnostics': {'score': first['score'], 'unknown_fraction': first['unknown_fraction'],
                                'known_labels': first['known_labels'], 'candidate_count': len(self.members),
                                'pool_size': len(pool), 'score_is_probability': False}, 'eligible_for_inference': False}

    def storage(self):
        return {'candidate_count': len(self.members), 'complex_weight_bytes': sum(m['weights'].nbytes for m in self.members),
                'integer_entries': sum(sum(len(v) for v in m['entries'].values()) for m in self.members),
                'metadata_utf8_bytes': len(canonical(self.meta).encode('utf-8')),
                'warm_atom_bytes': sum(v.nbytes for v in self.book.cache.values()),
                'scope': 'Owned arrays and serialized metadata; not total process RAM, transient recalls or energy.'}

    def save(self, directory):
        p = Path(directory)
        p.mkdir(parents=True, exist_ok=False)
        with (p / 'model.json').open('x', encoding='utf-8') as f:
            f.write(json.dumps({'metadata': self.meta, 'fingerprint': self.fingerprint}, ensure_ascii=False, indent=2) + '\n')
        np.savez(p / 'weights.npz', **{f'm{i}': m['weights'] for i, m in enumerate(self.members)})

    @classmethod
    def load(cls, directory):
        p = Path(directory)
        require({f.name for f in p.iterdir()} == {'model.json', 'weights.npz'}, 'invalid_model_inventory')
        obj = json.loads((p / 'model.json').read_text(encoding='utf-8'))
        require(type(obj) is dict and set(obj) == {'metadata', 'fingerprint'}, 'invalid_model_envelope')
        meta = obj['metadata']
        require(meta['schema'] == 'plm-dependency-memory-v013' and meta['eligible_for_inference'] is False, 'invalid_model_contract')
        config = meta['config']
        require(1 <= len(config['fields']) <= MAX_FIELDS and config['fields'] == sorted(set(config['fields'])) and
                set(config['vocabulary']) == set(config['fields']) and all(1 <= len(v) <= 2 for v in config['vocabulary'].values()), 'invalid_vocabulary')
        require(config['backend'] in ('ss', 'exact') and config['retention'] in ('all', 'minimal') and
                type(config['max_order']) is int and 1 <= config['max_order'] <= MAX_ORDER and
                config['support_threshold'] == SUPPORT_THRESHOLD and len(meta['members']) <= MAX_CANDIDATES, 'invalid_model_settings')
        require(2 <= len(config['labels']) <= 16 and config['labels'] == sorted(set(config['labels'])), 'invalid_labels')
        require(type(config['dimension']) is int and (128 <= config['dimension'] <= 4096 and config['dimension'] % 128 == 0 if config['backend'] == 'ss' else config['dimension'] == 0), 'invalid_dimension')
        members = []
        with np.load(p / 'weights.npz', allow_pickle=False) as arrays:
            require(set(arrays.files) == {f'm{i}' for i in range(len(meta['members']))}, 'invalid_weight_inventory')
            seen = set()
            for i, member in enumerate(meta['members']):
                mask = member['mask']
                require(mask == sorted(set(mask)) and 1 <= len(mask) <= config['max_order'] and set(mask) <= set(config['fields']) and tuple(mask) not in seen, 'invalid_candidate_mask')
                seen.add(tuple(mask))
                require(type(member['entries']) is dict and (config['backend'] != 'ss' or not member['entries']), 'ss_must_not_store_key_table')
                w = arrays[f'm{i}']
                shape = (len(config['labels']), config['dimension']) if config['backend'] == 'ss' else (0, 0)
                require(w.shape == shape and w.dtype == np.complex128 and np.isfinite(w).all(), 'invalid_weights')
                members.append(dict(member, weights=w.copy()))
        model = cls(config, members, meta['training'])
        require(model.meta == meta and model.fingerprint == obj['fingerprint'], 'model_fingerprint_mismatch')
        return model
