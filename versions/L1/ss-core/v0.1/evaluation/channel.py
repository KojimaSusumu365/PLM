"""Evaluator-only channel simulator and truth-corrected/disabled controls."""
import copy,math
import numpy as np
from bridge.carrier import validate,frame_book,carrier
from bridge.recovery import recover_masked
from bridge.runtime import signal_sha
from plm_s1_v02.link import simulate_channel,despread_aligned,shifted

CONDITIONS={
 'clean':{'delay_chips':0,'phase_rad':0.,'cfo_hz':0.,'keep_fraction':1.,'noise_std':0.},
 'offset_noise':{'delay_chips':-5,'phase_rad':.73,'cfo_hz':1.061538,'keep_fraction':1.,'noise_std':.08},
 'partial25':{'delay_chips':5,'phase_rad':-.91,'cfo_hz':-1.37,'keep_fraction':.25,'noise_std':.08},
 'partial10':{'delay_chips':3,'phase_rad':.4,'cfo_hz':.71,'keep_fraction':.10,'noise_std':.08},
 'pilot_missing':{'delay_chips':-5,'phase_rad':.73,'cfo_hz':1.061538,'keep_fraction':1.,'noise_std':.08,'erase_pilots':True},
 'cfo_outside':{'delay_chips':-3,'phase_rad':.2,'cfo_hz':3.,'keep_fraction':1.,'noise_std':.02},
 'noise_only':{'delay_chips':0,'phase_rad':0.,'cfo_hz':0.,'keep_fraction':1.,'noise_std':1.},
 'payload_missing':{'delay_chips':0,'phase_rad':0.,'cfo_hz':0.,'keep_fraction':1.,'noise_std':0.},
 'frame_swap':{'delay_chips':0,'phase_rad':0.,'cfo_hz':0.,'keep_fraction':1.,'noise_std':0.},
 'sampling_alias':{'delay_chips':0,'phase_rad':.1,'cfo_hz':8000.1,'keep_fraction':1.,'noise_std':0.},
}

def channel(model,tx,condition,seed):
    link,frames=validate(model,tx,tx['message_id'],tx['mode']);params=CONDITIONS[condition];rx=copy.deepcopy(tx);truth=[]
    for i,(frame,_,norm) in enumerate(frames):
        p=dict(params);p['seed']=seed+97*i
        # Consecutive framed captures with local-time phase appropriate to global elapsed time.
        p['phase_rad']+=2*math.pi*p['cfo_hz']*(i*link.frame_length/link.chip_rate_hz)
        if condition=='noise_only':frame=np.zeros_like(frame)
        if condition=='payload_missing':frame[link.data_indices]=0
        y,m=simulate_channel(frame,link,**p);f=rx['frames'][i];f.update(real=y.real.tolist(),imag=y.imag.tolist(),observed=m.tolist());truth.append(p)
    if condition=='frame_swap':
        for key in ('real','imag','observed','normalization'):rx['frames'][0][key],rx['frames'][1][key]=rx['frames'][1][key],rx['frames'][0][key]
    return rx,truth

def control_receive(model,wire,message_id,method,truth):
    assert method in ('ss_disabled','ss_oracle');link,frames=validate(model,wire,message_id,'spread');values=[];masks=[];audits=[]
    for i,(y,m,norm) in enumerate(frames):
        if method=='ss_oracle':
            p=truth[i];phase=p['phase_rad']+2*math.pi*p['cfo_hz']*np.arange(8480)/8000
            y=shifted(y*np.exp(-1j*phase),-p['delay_chips']);m=shifted(m,-p['delay_chips']);y[~m]=0
        v,vm,d=despread_aligned(y,m,frame_book(model,message_id,i),link,norm);values.append(v);masks.append(vm)
        audits.append({'frame':i,'sync':{'status':'oracle_reference' if method=='ss_oracle' else 'disabled'},'despread':d})
    vector=np.concatenate(values)*carrier(model).conj();mask=np.concatenate(masks)
    base={'frames':audits,'despread_signal_sha256':signal_sha(vector),'observed_components':int(mask.sum()),'eligible_for_inference':False}
    try:
        packet,audit=recover_masked(model,vector,mask)
        return dict(base,status='received',stage='ready',packet=packet,recovery=audit,recovered_signal_sha256=signal_sha(model.vector(packet)))
    except (ValueError,TypeError,OverflowError) as e:return dict(base,status='abstain',stage='meaning_recovery',reason=str(e))

def synchronization_errors(reception,truth):
    aligned=wrong=0
    for f,p in zip(reception.get('frames',[]),truth):
        s=f['sync']
        if s['status']!='aligned':continue
        aligned+=1;phase=abs(np.angle(np.exp(1j*(s['estimated_phase_rad']-p['phase_rad']))))
        wrong+=int(s['estimated_delay_chips']!=p['delay_chips'] or abs(s['estimated_cfo_hz']-p['cfo_hz'])>.025 or phase>.15)
    return {'aligned_frames':aligned,'wrong_aligned_frames':wrong,'total_frames':4}
