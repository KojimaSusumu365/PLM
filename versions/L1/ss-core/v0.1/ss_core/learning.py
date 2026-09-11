"""External-teacher error read/write windows, staged before an atomic software commit.

Write acknowledgements are local simulation events, not hardware read-back guarantees.
No legacy batch scorer or batch updater is used by the numerical update below.
"""
import copy
import numpy as np
from plm_l1_v09.component.algebra import require
from ss_retention.context import domain
from ss_revision.context import address, hexadecimal
from ss_revision.learning import PREPARED, begin, request, prepare
from bridge.runtime import receive
from .clock import ExactPort, read_scores


class WriteWindow:
    def __init__(self, part):
        self.staged = np.empty_like(part.weights)
        self.next_tick = 0
        self.failure = None
        self.closed = False

    def push(self, tick, column, acknowledged):
        if self.failure:
            return
        if self.closed or type(tick) is not int or tick != self.next_tick or tick >= self.staged.shape[1]:
            self.failure = 'write_order_or_length'
            return
        if type(acknowledged) is not bool or not acknowledged:
            self.failure = 'write_not_acknowledged'
            return
        col = np.asarray(column)
        if col.shape != (4,) or col.dtype.kind not in 'fc' or not np.isfinite(col).all():
            self.failure = 'write_nonfinite_or_shape'
            return
        self.staged[:,tick] = col
        self.next_tick += 1

    def finish(self):
        if self.closed or self.next_tick != self.staged.shape[1]:
            self.failure = self.failure or 'incomplete_write'
        self.closed = True
        audit = {'status':'held' if self.failure else 'ready', 'reason':self.failure,
                 'written_ticks':self.next_tick, 'expected_ticks':self.staged.shape[1]}
        return (None if self.failure else self.staged), audit


def acknowledge(part_name, tick):
    return True


def learn(memory, teacher, port_factory=ExactPort, chunk=1, ack=acknowledge, before_commit=None):
    require(memory.method == 'split_pair', 'split_pair_only')
    require(type(teacher) is dict and set(teacher) == {'key','domain','value','protect'}, 'teacher_record')
    label = (teacher['domain'], teacher['value'])
    require(label in memory.labels and type(teacher['protect']) is bool, 'teacher_label')
    index, initial = memory.labels.index(label), memory.fingerprint
    staged, audits = [], {}
    for name, part in memory.parts.items():
        if name == 'protected' and not teacher['protect']:
            continue
        nonce = 'learn/'+name+'/'+str(part.updates)
        scores, read_audit = read_scores(part, teacher['key'], nonce, True, port_factory, chunk)
        audits[name] = {'read':read_audit}
        if scores is None:
            return {'status':'held', 'reason':'read_window', 'windows':audits, 'eligible_for_inference':False}
        error = -scores.mean(axis=0)
        error[index] += 1.
        context = part.context(teacher['key'])
        writer = WriteWindow(part)
        for tick in range(part.dimension):
            delta = np.zeros(4, complex)
            for candidate in range(len(part.labels)):
                delta += error[candidate] * part.values[:,candidate,tick] * context[:,tick]
            writer.push(tick, part.weights[:,tick] + delta, ack(name, tick))
            if writer.failure:
                break
        weights, write_audit = writer.finish()
        audits[name]['write'] = write_audit
        audits[name]['teacher_error_l2'] = float(np.linalg.norm(error))
        if weights is None:
            return {'status':'held', 'reason':'write_window', 'windows':audits, 'eligible_for_inference':False}
        staged.append((part, weights))
    if before_commit is not None:
        before_commit()
    if memory.fingerprint != initial:
        return {'status':'held', 'reason':'stale_memory', 'windows':audits, 'eligible_for_inference':False}
    for part, weights in staged:
        part.weights = weights
        part.registry.add(teacher['key'])
        part.updates += 1
    return {'status':'learned', 'updated_parts':len(staged), 'windows':audits, 'eligible_for_inference':False}


def learn_revision(memory, teacher, **options):
    require(type(teacher) is dict and set(teacher) == PREPARED, 'prepared_fields')
    root, target = teacher['root'], teacher['target']
    require(hexadecimal(root) and root in memory.roots and target in memory.roots[root]['versions'], 'prepared_scope')
    state = memory.roots[root]
    base, revision = teacher['base_revision'], teacher['revision']
    require(type(base) is int and type(revision) is int and base == state['versions'][target]
            and revision == base+1 and revision <= 1000000, 'stale_or_out_of_order_confirmation')
    require(hexadecimal(teacher['legacy_key']), 'legacy_key_contract')
    key = address(memory.policy, root, target, revision, prepared_legacy=teacher['legacy_key'])
    result = learn(memory.ss, {'key':key, 'domain':domain(target), 'value':teacher['value'], 'protect':state['protect']}, **options)
    if result['status'] == 'learned':
        state['versions'][target] = revision
    return {'status':'confirmed' if result['status']=='learned' else 'held', 'target':target,
            'revision':state['versions'][target], 'memory_update':result, 'eligible_for_inference':False}


def learn_packet(model, memory, scope, packet, protect=True, **options):
    """All targets commit together; a held second target returns the original memory."""
    rec = model.recover(packet)
    require(rec['status'] == 'recovered' and not rec['pending'], 'teacher_must_be_complete')
    require(rec['observation']['count'] == 2 and len(scope['mutable']) == 2, 'two_events_two_targets')
    before = memory.fingerprint
    staged = copy.deepcopy(memory)
    root = begin(model, staged, scope, packet, protect)
    current, receipts = packet, []
    for target in scope['mutable']:
        value = rec['observation']['cells'][target]['candidates'][0]
        message = request(model, staged, scope, current, target, value)
        teacher, local = prepare(model, staged, scope, current, message)
        receipt = learn_revision(staged, teacher, **options)
        receipts.append(receipt)
        if receipt['status'] != 'confirmed':
            return memory, {'status':'held', 'stage':'memory_transaction', 'receipts':receipts,
                            'before_memory':before, 'after_memory':memory.fingerprint, 'eligible_for_inference':False}
        current = local['packet']
    require(memory.fingerprint == before, 'original_memory_changed')
    return staged, {'status':'learned', 'root':root, 'receipts':receipts,
                    'received_observation':rec['observation'], 'before_memory':before,
                    'after_memory':staged.fingerprint, 'eligible_for_inference':False}


def learn_received(model, memory, scope, wire, message_id, mode='spread', protect=True, **options):
    reception = receive(model, wire, message_id, mode)
    if reception['status'] != 'received':
        return memory, reception
    try:
        updated, result = learn_packet(model, memory, scope, reception['packet'], protect, **options)
        return updated, {**result, 'reception':{k:v for k,v in reception.items() if k != 'packet'}}
    except (ValueError, TypeError, OverflowError) as e:
        return memory, {'status':'rejected', 'stage':'teacher_contract', 'reason':str(e), 'eligible_for_inference':False}
