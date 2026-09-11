"""Explicit one-teacher transactions; bounded ordinary replay lives outside H."""
import copy
import json
from pathlib import Path
import numpy as np
from .algebra import canonical,digest,require
from .model import Model,decisions

METHODS=('accumulate','delta','delta5','replay32','exact')


class Learner:
    def __init__(self,model,method,seed='replay-0',step=0,updates=0,history=None,buffer=None):
        require(method in METHODS and (method=='exact')==(model.config['backend']=='exact'),'invalid_method_backend')
        require(type(seed) is str and type(step) is int and type(updates) is int and step>=0 and updates>=0,'invalid_state')
        self.model=model;self.method=method;self.seed=seed;self.step=step;self.updates=updates
        self.history=history or digest(['empty-online-history'])
        self.buffer=copy.deepcopy(buffer or [])
        require(type(self.history) is str and len(self.history)==64 and len(self.buffer)<=32,'invalid_history_buffer')
        require(method=='replay32' or not self.buffer,'buffer_only_for_replay')
        for r in self.buffer:
            require(type(r) is dict and set(r)=={'context','label','observed_step'} and r['label'] in model.config['labels'] and type(r['observed_step']) is int and 1<=r['observed_step']<=step,'invalid_buffer_entry')
            model.validate(r['context'])
        self.refresh()

    @classmethod
    def start(cls,method='delta',dimension=128,seed='phase-0',replay_seed='replay-0'):
        fields=['f0','f1','f2','f3']
        config={'backend':'exact' if method=='exact' else 'ss','dimension':0 if method=='exact' else dimension,
                'seed':'exact' if method=='exact' else seed,'fields':fields,'vocabulary':{f:list(map(str,range(8))) for f in fields},'labels':list('0123')}
        return cls(Model(config),method,replay_seed)

    def refresh(self):
        self.state={'schema':'plm-ss-online-learner-01','method':self.method,'seed':self.seed,'step':self.step,'updates':self.updates,
                    'history':self.history,'buffer':self.buffer,'model_fingerprint':self.model.fingerprint,
                    'learning_rate':.5,'replay_capacity':32 if self.method=='replay32' else 0,'eligible_for_inference':False}
        self.fingerprint=digest(self.state)

    def question(self,context):
        self.model.validate(context)
        request={'schema':'plm-ss-online-request-01','state_fingerprint':self.fingerprint,'context':copy.deepcopy(context)}
        request['request_id']=digest(request)
        return {'request':request,'prediction':self.model.predict([context])[0]}

    def _delta(self,context,label):
        b=self.model.vector(context)
        target=np.array([int(y==label) for y in self.model.config['labels']],dtype=float)
        error=target-self.model.score_vector(b)
        self.model.weights += .5*error[:,None]*b[None,:]
        self.updates+=1

    def answer(self,request,feedback):
        require(type(request) is dict and set(request)=={'schema','state_fingerprint','context','request_id'},'request_schema')
        require(request['schema']=='plm-ss-online-request-01' and request['state_fingerprint']==self.fingerprint,'stale_request')
        require(request==self.question(request['context'])['request'],'tampered_request')
        require(type(feedback) is dict and set(feedback)=={'schema','request_id','source','label'},'feedback_schema')
        require(feedback['schema']=='plm-ss-online-feedback-01' and feedback['request_id']==request['request_id'],'feedback_request_mismatch')
        require(feedback['source']=='external_teacher','prediction_is_not_teacher')
        label=feedback['label'];require(type(label) is str and label in self.model.config['labels'],'new_label_requires_scope_review')
        context=request['context'];target=np.array([int(y==label) for y in self.model.config['labels']],dtype=float)
        before=self.model.predict([context])[0]
        model=Model(self.model.config,self.model.weights,self.model.entries)
        model.book=self.model.book # immutable phase definitions; cache not learned state.
        new=Learner(model,self.method,self.seed,self.step,self.updates,self.history,self.buffer)
        next_step=self.step+1
        replay_ids=[]
        if self.method=='exact':
            new.model.entries[canonical(context)]=label;new.updates+=1
        elif self.method=='accumulate':
            new.model.weights[self.model.config['labels'].index(label)]+=new.model.vector(context);new.updates+=1
        else:
            # A fresh external answer supersedes old replay labels for this same key.
            for r in new.buffer:
                if r['context']==context:r['label']=label;r['observed_step']=next_step
            new._delta(context,label)
            if self.method=='delta5':
                for _ in range(4):new._delta(context,label)
            elif self.method=='replay32' and new.buffer:
                for j in range(4):
                    idx=int(digest(['replay',new.seed,next_step,j])[:16],16)%len(new.buffer)
                    r=new.buffer[idx];new._delta(r['context'],r['label']);replay_ids.append(idx)
        if self.method=='replay32':
            item={'context':copy.deepcopy(context),'label':label,'observed_step':next_step}
            if len(new.buffer)<32:new.buffer.append(item)
            else:
                slot=int(digest(['reservoir',new.seed,next_step])[:16],16)%next_step
                if slot<32:new.buffer[slot]=item
        new.step=next_step
        new.history=digest([self.history,request['request_id'],feedback])
        new.model.refresh();new.refresh()
        after=new.model.predict([context])[0]
        audit={'step':new.step,'teacher_presentations':1,'new_unique_teacher_labels_claimed':False,
               'updates_this_answer':new.updates-self.updates,'replay_updates':len(replay_ids),
               'replayed_buffer_indices':replay_ids,'before':before,'after':after,
               'teacher_mse_before':float(np.mean((np.array(before['scores'])-target)**2)),
               'teacher_mse_after':float(np.mean((np.array(after['scores'])-target)**2)),
               'prior_state_fingerprint':self.fingerprint,'next_state_fingerprint':new.fingerprint,
               'feedback_source_is_an_api_declaration_not_authentication':True}
        return new,audit

    def storage(self):
        return self.model.storage()|{'learner_state_utf8_bytes':len(canonical(self.state).encode('utf-8')),
                                    'replay_entries':len(self.buffer),'replay_unique_contexts':len({canonical(r['context']) for r in self.buffer}),
                                    'replay_utf8_bytes':len(canonical(self.buffer).encode('utf-8')),
                                    'teacher_presentations':self.step,'numerical_or_exact_updates':self.updates}

    def save(self,directory):
        p=Path(directory);p.mkdir(parents=True,exist_ok=False);self.model.save(p/'model')
        with (p/'learner.json').open('x',encoding='utf-8') as f:json.dump({'state':self.state,'fingerprint':self.fingerprint},f,ensure_ascii=False,indent=2)

    @classmethod
    def load(cls,directory):
        p=Path(directory);require({x.name for x in p.iterdir()}=={'model','learner.json'},'learner_inventory')
        obj=json.loads((p/'learner.json').read_text(encoding='utf-8'));s=obj['state']
        require(s['schema']=='plm-ss-online-learner-01' and s['eligible_for_inference'] is False and digest(s)==obj['fingerprint'],'learner_fingerprint_mismatch')
        model=Model.load(p/'model');require(model.fingerprint==s['model_fingerprint'],'learner_model_mismatch')
        learner=cls(model,s['method'],s['seed'],s['step'],s['updates'],s['history'],s['buffer'])
        require(learner.state==s and learner.fingerprint==obj['fingerprint'],'learner_state_mismatch')
        return learner
