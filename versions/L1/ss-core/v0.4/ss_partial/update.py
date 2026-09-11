"""External, packet-bound, one-cell transactions. No learned truth arbitration."""
import copy
import math
from plm_l1_v09.component.algebra import digest, require
from .contract import cell, normalize, normalize_cell

FIELDS = {'schema', 'packet_sha256', 'target', 'value', 'operation'}


def request(packet, target, value, operation='supply'):
    return {'schema': 'plm-ss-local-update-02', 'packet_sha256': digest(packet),
            'target': target, 'value': value, 'operation': operation}


def apply(model, packet, message):
    try:
        require(type(message) is dict and set(message) == FIELDS, 'update_fields')
        require(message['schema'] == 'plm-ss-local-update-02', 'update_schema')
        require(message['packet_sha256'] == digest(packet), 'stale_or_wrong_document')
        rec = model.recover(packet)
        require(rec['status'] == 'recovered', 'unreadable_source_packet')
        source = rec['observation']
        target, value, operation = message['target'], message['value'], message['operation']
        require(type(target) is str and target in source['cells'], 'update_target')
        require(type(value) is str and value in model.codec.choices[target], 'update_value')
        require(type(operation) is str and operation in ('supply', 'resolve', 'revise'), 'update_operation')
        old = source['cells'][target]
        if operation == 'resolve':
            require(old['state'] == 'conflict' and value in old['candidates'], 'explicit_conflict_resolution_required')
            new = cell('known', [value])
        elif operation == 'revise':
            require(old['state'] == 'known', 'revision_requires_known_value')
            new = cell('known', [value])
        elif old['state'] in ('unobserved', 'unreadable'):
            new = cell('known', [value])
        elif old['state'] == 'ambiguous' and value in old['candidates']:
            new = cell('known', [value])
        elif old['state'] == 'known' and old['candidates'] == [value]:
            new = copy.deepcopy(old)
        else:
            new = cell('conflict', sorted(set(old['candidates'] + [value])))
        new = normalize_cell(new, model.codec.choices[target])
        expected = copy.deepcopy(source)
        expected['cells'][target] = new
        expected = normalize(expected, model.codec.candidates)
        # Operate on the actual received numeric vector, not a fresh full re-encoding.
        delta = (model.codec.cell_vector(target, new) - model.codec.cell_vector(target, old)) / math.sqrt(3.)
        numeric = model.vector(packet) + delta
        output = model.packet(numeric)
        recovered = model.recover(output)
        require(recovered['status'] == 'recovered' and recovered['observation'] == expected, 'transaction_postcondition_failed')
        unchanged = all(recovered['observation']['cells'][k] == v for k, v in source['cells'].items() if k != target)
        require(unchanged, 'unrelated_cell_changed')
        status = 'unchanged' if old == new else 'conflict' if new['state'] == 'conflict' else 'updated'
        return {'status': status, 'packet': output, 'audit': {'target': target, 'operation': operation,
                'old': old, 'new': new, 'source_sha256': digest(packet), 'output_sha256': digest(output),
                'other_cells_unchanged': unchanged, 'local_numeric_delta_only': True}, 'eligible_for_inference': False}
    except (ValueError, TypeError, OverflowError) as e:
        return {'status': 'rejected', 'reason': str(e), 'eligible_for_inference': False}
