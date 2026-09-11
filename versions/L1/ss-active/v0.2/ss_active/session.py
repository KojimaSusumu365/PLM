"""External-teacher acquisition and interleaved background learning. No teacher replay."""
import copy,json
from pathlib import Path
from ss_multicode.algebra import digest,require
from ss_multicode.learning import Learner,teacher
from .selection import normalize_state,select,diagnostics,context_id


def feedback(request,label):
    return {'schema':'plm-ss-active2-feedback','request_id':request['request_id'],'source':'external_teacher','label':label}


def validate_feedback(request,fb):
    require(type(fb) is dict and set(fb)=={'schema','request_id','source','label'},'feedback_schema')
    require(fb['schema']=='plm-ss-active2-feedback' and fb['request_id']==request['request_id'],'feedback_request')
    require(fb['source']=='external_teacher','prediction_is_not_teacher')
    require(type(fb['label']) is str and fb['label'] in list('0123'),'known_teacher_label')


class Session:
    def __init__(self,learner,pool,strategy,seed,config,ledger=None,origin_step=None,background_count=0,history=None):
        require(learner.model.architecture=='concat512','shared_residual_model_required')
        self.learner=learner
        self.selection_state=normalize_state({'schema':'plm-ss-active2-selection-state','pool':pool,'ledger':{} if ledger is None else ledger,
            'strategy':strategy,'seed':seed,'config':config,'current_step':learner.step})
        self.origin_step=learner.step if origin_step is None else origin_step;self.background_count=background_count
        require(type(self.origin_step) is int and self.origin_step>=0 and type(background_count) is int and background_count>=0,'origin_background')
        require(learner.step==self.origin_step+background_count+self.acquired,'teacher_budget_accounting')
        self.history=digest(['empty-active2-history']) if history is None else history
        require(type(self.history) is str and len(self.history)==64,'session_history')
        self.state={'schema':'plm-ss-active2-session','learner_fingerprint':learner.fingerprint,'selection_state':self.selection_state,
                    'origin_step':self.origin_step,'background_count':background_count,'history':self.history,'eligible_for_inference':False}
        self.fingerprint=digest(self.state)

    @property
    def acquired(self):return sum(e['visits'] for e in self.selection_state['ledger'].values())

    def ask(self):
        q={'schema':'plm-ss-active2-request','session_fingerprint':self.fingerprint,'selection':select(self.learner.model,self.selection_state)}
        q['request_id']=digest(q);return q

    def spawn(self,learner,ledger,background_count,request,fb):
        s=self.selection_state
        return Session(learner,s['pool'],s['strategy'],s['seed'],s['config'],ledger,self.origin_step,background_count,digest([self.history,request,fb]))

    def answer(self,request,fb):
        require(type(request) is dict and request.get('session_fingerprint')==self.fingerprint,'stale_request')
        require(request==self.ask(),'tampered_or_unselected_request');validate_feedback(request,fb)
        selected=request['selection'];q=self.learner.question(selected['context'])['request'];learned=self.learner.answer(q,teacher(q,fb['label']))
        ledger=copy.deepcopy(self.selection_state['ledger']);key=selected['selected_id'];visits=ledger.get(key,{}).get('visits',0)+1
        margin=float(diagnostics(learned.model.raw([selected['context']])['readers'])['margin'][0])
        ledger[key]={'visits':visits,'last_step':learned.step,'post_margin':margin}
        return self.spawn(learned,ledger,self.background_count,request,fb)

    def background_question(self,context):
        key=context_id(context);require(key not in {r['id'] for r in self.selection_state['pool']},'pool_requires_acquisition_budget')
        q={'schema':'plm-ss-active2-background-request','session_fingerprint':self.fingerprint,'context':copy.deepcopy(context)}
        q['request_id']=digest(q);return q

    def background_answer(self,request,fb):
        require(type(request) is dict and request.get('session_fingerprint')==self.fingerprint,'stale_background_request')
        require(request==self.background_question(request['context']),'background_request');validate_feedback(request,fb)
        q=self.learner.question(request['context'])['request'];learned=self.learner.answer(q,teacher(q,fb['label']))
        return self.spawn(learned,self.selection_state['ledger'],self.background_count+1,request,fb)

    def save(self,directory):
        p=Path(directory);p.mkdir(parents=True,exist_ok=False);self.learner.save(p/'learner')
        with (p/'session.json').open('x',encoding='utf-8') as f:json.dump({'state':self.state,'fingerprint':self.fingerprint},f,ensure_ascii=False,indent=2,allow_nan=False)

    @classmethod
    def load(cls,directory):
        p=Path(directory);require({r.name for r in p.iterdir()}=={'learner','session.json'},'session_inventory')
        obj=json.loads((p/'session.json').read_text(encoding='utf-8'));s=obj['state'];ss=s['selection_state']
        new=cls(Learner.load(p/'learner'),ss['pool'],ss['strategy'],ss['seed'],ss['config'],ss['ledger'],s['origin_step'],s['background_count'],s['history'])
        require(new.state==s and new.fingerprint==obj['fingerprint'],'session_fingerprint');return new
