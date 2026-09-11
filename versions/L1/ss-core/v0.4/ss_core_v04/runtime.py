"""No semantic dictionaries or role-name dispatch between numeric WM and output.

Static schema, opcode interpreter, readiness gates, and terminal codebook remain.
"""
import hashlib,json
from pathlib import Path
import numpy as np
from plm_l1_v09.component.algebra import require
from ss_core_v03.waveform import Engine
from .signal import Association,SignalProgram,Terminal,winner
from .memory import WorkingMemory

class Schema:
    def __init__(self,meta,arrays):
        self.width=meta['width'];self.source_fingerprint=meta['source_fingerprint']
        self.fingerprint=hashlib.sha256(json.dumps(meta,sort_keys=True).encode()).hexdigest()
        for name in ('values','addresses','states','arities','events','roles','header','known_status','allowed','global_addresses'):
            setattr(self,name,arrays[name])

class Core:
    def __init__(self,meta,arrays,engine):
        self.engine,self.schema=engine,Schema(meta,arrays)
        self.goal_signals,self.order_signals=arrays['goal_signals'],arrays['order_signals']
        self.operations=arrays['operations']
        self.maps={name:Association(arrays[name+'_weights'],arrays[name+'_refs'],engine,name) for name in
                   ('polarity','modality','presentation','lexical','temporal','sentence_op','sentence_operand','document_op','document_operand')}
        self.sentence=SignalProgram(arrays['sentence_weights'],arrays['sentence_actions'],arrays['sentence_states'],engine,'sentence')
        self.document=SignalProgram(arrays['document_weights'],arrays['document_actions'],arrays['document_states'],engine,'document')
        self.terminal=Terminal(meta['surfaces'],arrays['surfaces'],engine)

    def opcode(self,signal):
        return winner(self.engine.correlate(signal,self.operations,'opcode04')[0])

    def generate(self,wm,order_signal,goal_signals):
        start=len(self.engine.trace)
        try:
            require(wm.schema.fingerprint==self.schema.fingerprint and wm.engine is self.engine,'core_contract')
            require(isinstance(order_signal,np.ndarray) and order_signal.shape==(self.schema.width,) and np.isfinite(order_signal).all(),'order_signal')
            require(isinstance(goal_signals,np.ndarray) and goal_signals.shape==(2,self.schema.width) and np.isfinite(goal_signals).all(),'goal_signals')
            wm.validate(require_complete=True)
            presentation=wm.value(self.schema.global_addresses[1])
            context=self.maps['presentation'].query(presentation)*order_signal
            state=self.document.start();parts=[];seen=np.zeros(self.schema.width,complex);first=None;actions=0
            for _ in range(4):
                action,state=self.document.step(context,state);actions+=1
                op=self.opcode(self.maps['document_op'].query(action))
                if op==2:
                    require(len(parts)==2,'incomplete_document')
                    return {'status':'generated','text':''.join(parts),'actions':actions,'cost':self.engine.stats(start)}
                require(op==0 and len(parts)<2,'document_opcode')
                event=self.maps['document_operand'].query(action)
                repeated=self.engine.correlate(seen,event[None,:],'seen_event04')[0,0]
                require(repeated<.5,'duplicate_event')
                marker=''
                if first is not None:
                    relation=wm.value(self.schema.global_addresses[0])
                    marker=self.terminal.emit(self.maps['temporal'].query(relation*first))
                text,count=self.sentence_text(wm,event,goal_signals[len(parts)])
                actions+=count;parts.append(marker+text);seen+=event
                if first is None:first=event.copy()
            raise ValueError('document_stop_missing')
        except (ValueError,TypeError) as e:
            return {'status':'held','text':None,'reason':str(e),'cost':self.engine.stats(start)}

    def revise_and_generate(self,wm,address,teacher_signal,order_signal,goal_signals):
        """Fail closed for this request: a rejected correction never emits old text.

        The caller must still honor the returned status; no persistent pending
        workflow or teacher-authentication policy is claimed by this API.
        """
        start=len(self.engine.trace)
        updated,receipt=wm.update(address,teacher_signal)
        if receipt['status']!='updated':
            return wm,{'status':'held','text':None,'reason':'update_not_committed','update':receipt,'cost':self.engine.stats(start)}
        result=self.generate(updated,order_signal,goal_signals)
        result['update']=receipt;result['cost']=self.engine.stats(start)
        return updated,result

    def sentence_text(self,wm,event,goal_signal):
        # These two fixed context ports are architectural, not a decoded meaning.
        polarity=wm.value(event*self.schema.roles[3]);modality=wm.value(event*self.schema.roles[4])
        context=self.maps['polarity'].query(polarity)*self.maps['modality'].query(modality)*goal_signal
        state=self.sentence.start();tokens=[];seen=np.zeros(self.schema.width,complex);lexical_count=0
        for step in range(12):
            action,state=self.sentence.step(context,state)
            op=self.opcode(self.maps['sentence_op'].query(action))
            if op==2:
                require(lexical_count==3 and len(tokens)<=9,'incomplete_sentence')
                return ''.join(tokens),step+1
            operand=self.maps['sentence_operand'].query(action)
            if op==0:
                require(self.engine.correlate(seen,operand[None,:],'seen_role04')[0,0]<.5,'duplicate_role')
                value=wm.value(event*operand)
                surface=self.maps['lexical'].query(value)
                tokens.append(self.terminal.emit(surface));seen+=operand;lexical_count+=1
            elif op==1:tokens.append(self.terminal.emit(operand))
            else:raise ValueError('sentence_opcode')
        raise ValueError('sentence_stop_missing')

def load(root,engine=None):
    root=Path(root);path=root/'bundle04';engine=engine or Engine()
    meta=json.loads((path/'bundle.json').read_text(encoding='utf-8'))
    require(meta['schema']=='signal-working-bundle04','bundle_schema')
    with np.load(path/'signals.npz',allow_pickle=False) as f:
        require(set(f.files)==set(meta['array_hashes']),'bundle_arrays')
        arrays={k:f[k] for k in f.files}
    require(all(np.isfinite(a).all() and hashlib.sha256(a.astype('<c16').tobytes()).hexdigest()==meta['array_hashes'][k] for k,a in arrays.items()),'bundle_hash')
    return Core(meta,arrays,engine)
