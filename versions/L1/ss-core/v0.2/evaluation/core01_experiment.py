import copy
from plm_l1_v09.component.algebra import digest
from ss_partial.contract import from_meaning
from ss_revision.learning import begin,request,teach
from ss_revision.memory import RevisionMemory
from bridge.carrier import encode
from bridge.runtime import receive
from ss_core.learning import learn_packet
from ss_core.memory import WaveRevisionView
from .ports import factory
from .channel import channel,synchronization_errors
from .prior_experiment import finish,compact
from .integrity import write

MODES = {'batch':(None,1), 'stream1':('exact',1), 'stream37':('exact',37), 'stream_phase':('phase',37)}

def inputs(model, cases, split):
    """Channel is paired across memories: receive each teacher/query once and share it."""
    records, packets = [], {}
    for i,case in enumerate(cases):
        # Teaching content is read from the external bounded-language text first.
        readback = model.document.read(case['text'])
        assert readback['status']=='read'
        meaning = model.document.recover(readback['packet'])['meaning']
        observation = from_meaning(meaning,model.codec.candidates)
        assert observation==case['known']
        for kind in (('teacher','query') if case['kind']=='focal' else ('teacher',)):
            mid = 'ss-core01/'+case['id']+'/'+kind
            packet = model.encode(observation if kind=='teacher' else case['query'])
            seed = 41000+i*97+(10000 if kind=='query' else 0)
            wire,truth = channel(model,encode(model,packet,mid),'partial25',seed)
            reception = receive(model,wire,mid)
            packets[(case['id'],kind)] = reception
            actual = model.recover(reception['packet'])['observation'] if reception['status']=='received' else None
            records.append({'case_id':case['id'],'kind':kind,'message_id':mid,'channel_seed':seed,
                            'wire_sha256':digest(wire),'reception':compact(reception),
                            'received_observation_equal':actual==(observation if kind=='teacher' else case['query']) if actual is not None else None,
                            'sync':synchronization_errors(reception,truth)})
        print({'input_ready':case['id']},flush=True)
    return packets,records

def baseline_learn(model,memory,case,packet):
    rec = model.recover(packet)
    assert rec['status']=='recovered' and not rec['pending']
    staged = copy.deepcopy(memory)
    begin(model,staged,case['scope'],packet,case['kind']=='focal')
    current,receipts = packet,[]
    for target in case['scope']['mutable']:
        msg = request(model,staged,case['scope'],current,target,rec['observation']['cells'][target]['candidates'][0])
        result = teach(model,staged,case['scope'],current,msg)
        current = result['packet']
        receipts.append(compact(result))
    return staged, {'status':'learned','receipts':receipts,'received_observation':rec['observation'],
                    'before_memory':memory.fingerprint,'after_memory':staged.fingerprint}

def train(model,cases,packets,seed,mode,out):
    memory = RevisionMemory(model.codec.candidates,'versioned_pair','ss-core-main-'+str(seed))
    condition,chunk = MODES[mode]
    receipts = []
    for case in cases:
        reception = packets[(case['id'],'teacher')]
        if reception['status']!='received':
            receipts.append({'case_id':case['id'],'kind':case['kind'],'receipt':{
                'status':'held','stage':'outer_reception','reception':compact(reception),
                'before_memory':memory.fingerprint,'after_memory':memory.fingerprint}})
            continue
        packet = reception['packet']
        if mode=='batch':
            memory,receipt = baseline_learn(model,memory,case,packet)
        else:
            memory,receipt = learn_packet(model,memory,case['scope'],packet,case['kind']=='focal',
                                          port_factory=factory(condition,seed),chunk=chunk)
        receipts.append({'case_id':case['id'],'kind':case['kind'],'receipt':receipt})
    memory.save(out/'memory')
    write(out/'TEACHERS.json',receipts)
    cold = RevisionMemory.load(out/'memory',model.codec.candidates)
    assert cold.fingerprint==memory.fingerprint
    return cold,receipts

def query(model,memory,case,reception,mode,seed,condition=None):
    internal,chunk = MODES[mode]
    if condition is not None:
        internal = condition
    view = memory if internal is None else WaveRevisionView(memory,factory(internal,seed),chunk)
    result = finish(model,view,case['scope'],reception,case)
    return {'case_id':case['id'],'mode':mode,'seed':seed,'condition':condition or 'main',
            'result':result,'memory_fingerprint':memory.fingerprint,
            'memory_windows':view.ss.traces if isinstance(view,WaveRevisionView) else [],
            'eligible_for_inference':False}

def update_faults(model,memory,case,packet,seed):
    rows = []
    for condition in ('drop25','drop50','tail_drift','pilot_missing','truncate','reorder','write_interrupt','payload_noise'):
        before = memory.fingerprint
        options = {'port_factory':factory(condition,seed)} if condition!='write_interrupt' else {
            'ack':lambda name,tick:not(name=='protected' and tick==600)}
        updated,r = learn_packet(model,memory,case['scope'],packet,True,**options)
        rows.append({'condition':condition,'seed':seed,'status':r['status'], 'expected_hold':condition!='payload_noise',
                     'original_unchanged':memory.fingerprint==before,'returned_unchanged':updated.fingerprint==before,
                     'receipt':r})
    return rows
