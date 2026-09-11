"""Pinned frame contract. No source text, assignments or channel truth on receive."""
import math
import numpy as np
from plm_p1.core import PhaseCodebook,digest,require,signal_array,observation_mask
from plm_s1_v02.link import Link,transmit,despread_aligned
from plm_s1_v02.receiver import synchronize

DIMENSION=8192
FRAME_COUNT=4
ENERGY_PER_FRAME=57344.
SCHEMA='plm-l1-p1-s1-chips-01'

def profile(model):
    require(model.codec.dimension==DIMENSION,'bridge_requires_8192_components')
    return {'schema':'l1-p1-s1-profile-01','model_fingerprint':model.fingerprint,
            'dimension':DIMENSION,'frames':FRAME_COUNT,'carrier_seed':'l1-p1-carrier-01',
            's1_link':Link().spec,'frame_energy':ENERGY_PER_FRAME}

def identity(value):require(type(value) is str and 1<=len(value)<=96,'message_id');return value

def carrier(model):
    p=profile(model)
    return PhaseCodebook(DIMENSION,p['carrier_seed']).code('role','l1-partial-signal')

def frame_book(model,message_id,index):
    identity(message_id);require(type(index) is int and 0<=index<FRAME_COUNT,'frame_index')
    return PhaseCodebook(2048,'l1-s1-frame/'+digest([profile(model),message_id,index]))

def make_wire(model,message_id,mode,frames):
    return {'schema':SCHEMA,'model_fingerprint':model.fingerprint,'profile_fingerprint':digest(profile(model)),
            'message_id':identity(message_id),'mode':mode,'frames':frames,'eligible_for_inference':False}

def encode(model,packet,message_id,mode='spread'):
    require(mode in ('spread','repeat'),'bridge_mode')
    vector=model.vector(packet)*carrier(model);link=Link(mode=mode);frames=[]
    for i in range(FRAME_COUNT):
        values=vector[2048*i:2048*(i+1)];chips,norm=transmit(values,frame_book(model,message_id,i),link,total_energy=ENERGY_PER_FRAME)
        frames.append({'index':i,'real':chips.real.tolist(),'imag':chips.imag.tolist(),
                       'observed':[True]*link.frame_length,'normalization':norm})
    return make_wire(model,message_id,mode,frames)

def validate(model,packet,expected_id,mode='spread'):
    fields={'schema','model_fingerprint','profile_fingerprint','message_id','mode','frames','eligible_for_inference'}
    require(type(packet) is dict and set(packet)==fields,'wire_fields')
    require(packet['schema']==SCHEMA and packet['model_fingerprint']==model.fingerprint and
            packet['profile_fingerprint']==digest(profile(model)),'wire_profile')
    require(packet['message_id']==identity(expected_id) and packet['eligible_for_inference'] is False,'wire_identity')
    require(mode in ('spread','repeat') and packet['mode']==mode,'wire_mode')
    require(type(packet['frames']) is list and len(packet['frames'])==FRAME_COUNT,'four_ordered_frames')
    link=Link(mode=mode);out=[]
    for i,f in enumerate(packet['frames']):
        require(type(f) is dict and set(f)=={'index','real','imag','observed','normalization'},'frame_fields')
        require(type(f['index']) is int and f['index']==i,'ordered_frame_index')
        for name in ('real','imag'):
            require(type(f[name]) is list and len(f[name])==8480 and all(type(v) in (int,float) for v in f[name]),'numeric_chips_only')
        require(type(f['observed']) is list and len(f['observed'])==8480 and all(type(v) is bool for v in f['observed']),'chip_mask')
        y=np.asarray(f['real'],float)+1j*np.asarray(f['imag'],float);m=np.asarray(f['observed'],bool)
        require(np.isfinite(y).all() and np.max(np.abs(y))<=128 and np.all(y[~m]==0),'finite_bounded_masked_chips')
        norm=f['normalization'];require(type(norm) is dict and set(norm)=={'payload_gain','pilot_amplitude','total_tx_energy'},'public_normalization')
        require(all(type(x) in (int,float) and math.isfinite(x) and x>0 for x in norm.values()),'finite_positive_normalization')
        require(norm['total_tx_energy']==ENERGY_PER_FRAME and abs(norm['pilot_amplitude']-math.sqrt(ENERGY_PER_FRAME/8448))<1e-12 and
                1e-6<=norm['payload_gain']<=1e6,'normalization_contract')
        out.append((y,m,norm))
    return link,out

def demodulate(model,wire,expected_id,mode='spread'):
    """Only estimated synchronization; oracle and disabled paths live in evaluation."""
    link,frames=validate(model,wire,expected_id,mode);values=[];masks=[];audits=[]
    for i,(y,m,norm) in enumerate(frames):
        book=frame_book(model,expected_id,i);a,am,sync=synchronize(y,m,book,link,norm)
        v,vm,despread=despread_aligned(a,am,book,link,norm)
        values.append(v);masks.append(vm);audits.append({'frame':i,'sync':sync,'despread':despread})
    raw=np.concatenate(values)*carrier(model).conj();mask=np.concatenate(masks)
    return raw,mask,audits

def budget():
    return {'complex_components':8192,'frames':4,'payload_chips':32768,'pilot_chips':1024,'guard_chips':128,
            'total_chips':33920,'chip_rate_hz':8000,'nominal_serial_seconds':4.24,'total_energy':229376.,
            'per_teacher_plus_query_chips':67840,'per_teacher_plus_query_energy':458752.,
            'json_header_and_float_serialization_cost_excluded':True,
            'frame_boundaries_and_public_gain_are_external_contracts':True}
