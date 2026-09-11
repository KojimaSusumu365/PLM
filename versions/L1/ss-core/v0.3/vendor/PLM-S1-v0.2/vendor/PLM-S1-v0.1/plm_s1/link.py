"""Explicit discrete complex chips, public pilot framing and energy accounting."""
from dataclasses import dataclass, asdict
from hashlib import shake_256
import math
import numpy as np
from plm_p1.core import canonical, digest, require, signal_array, observation_mask

MODES = {"spread", "repeat", "direct_sparse"}


@dataclass(frozen=True)
class Link:
    dimension: int = 2048
    chips_per_component: int = 4
    pilot_length: int = 128
    guard_length: int = 16
    chip_rate_hz: float = 8000.
    max_delay_chips: int = 8
    max_abs_cfo_hz: float = .20
    spreading_seed: str = "s1-v01-public-codes"
    mode: str = "spread"

    def validate(self):
        require(type(self.dimension) is int and 128 <= self.dimension <= 4096 and self.dimension % 64 == 0, "Invalid P1 dimension")
        require(type(self.chips_per_component) is int and self.chips_per_component in {2,4,8}, "Unsupported spreading factor")
        require(type(self.pilot_length) is int and self.pilot_length in {64,128,256}, "Unsupported pilot length")
        require(type(self.guard_length) is int and 0 <= self.guard_length <= 32, "Invalid guard")
        require(type(self.max_delay_chips) is int and 0 <= self.max_delay_chips <= min(self.guard_length,16), "Delay search must fit guard")
        require(type(self.chip_rate_hz) in (int,float) and math.isfinite(self.chip_rate_hz) and self.chip_rate_hz > 0, "Invalid chip rate")
        require(type(self.max_abs_cfo_hz) in (int,float) and math.isfinite(self.max_abs_cfo_hz) and 0 < self.max_abs_cfo_hz <= self.chip_rate_hz / (4*self.pilot_separation), "CFO prior must be well inside two-pilot ambiguity interval")
        require(type(self.spreading_seed) is str and self.spreading_seed.strip(), "Public spreading seed required")
        require(type(self.mode) is str and self.mode in MODES, "Unknown modulation mode")
        return self

    @property
    def payload_length(self): return self.dimension*self.chips_per_component
    @property
    def pilot_separation(self): return self.payload_length+self.pilot_length
    @property
    def payload_start(self): return self.guard_length+self.pilot_length
    @property
    def tail_start(self): return self.payload_start+self.payload_length
    @property
    def frame_length(self): return 2*self.guard_length+2*self.pilot_length+self.payload_length
    @property
    def spec(self): return asdict(self)
    @property
    def fingerprint(self): return digest(self.spec)


def _bytes(book, link, label, size):
    key=canonical(["plm-s1-shake-codes-v1",book.fingerprint,link.spreading_seed,label])
    return np.frombuffer(shake_256(key.encode("utf-8")).digest(size),dtype=np.uint8)


def spreading_codes(book, link):
    link.validate()
    require(book.dimension==link.dimension,"Codebook/link dimension mismatch")
    d,l=link.dimension,link.chips_per_component
    if link.mode=="direct_sparse":
        codes=np.zeros((d,l))
        codes[:,0]=math.sqrt(l)
        return codes
    if link.mode=="repeat": return np.ones((d,l))
    # Exactly balanced signs in every component, deterministic stable tie-breaking.
    order=np.argsort(_bytes(book,link,"payload",d*l).reshape(d,l),axis=1,kind="stable")
    codes=-np.ones((d,l))
    np.put_along_axis(codes,order[:,:l//2],1.,axis=1)
    return codes


def pilots(book,link):
    return tuple(2*(_bytes(book,link,label,link.pilot_length).astype(np.int16)%2)-1 for label in ("head-pilot","tail-pilot"))


def spread(values,book,link):
    values=signal_array(values,link.dimension)
    return (values[:,None]*spreading_codes(book,link)/math.sqrt(link.chips_per_component)).reshape(-1)


def transmit(values,book,link=Link(),*,total_energy=57344.):
    link.validate()
    require(type(total_energy) in (int,float) and math.isfinite(total_energy) and total_energy>0,"Invalid energy budget")
    chips=spread(values,book,link)
    energy=float(np.vdot(chips,chips).real)
    require(math.isfinite(energy) and energy>0,"Empty/nonfinite payload")
    active_slots=link.payload_length+2*link.pilot_length
    pilot_amplitude=math.sqrt(total_energy/active_slots)
    payload_energy=total_energy*link.payload_length/active_slots
    gain=math.sqrt(payload_energy/energy)
    frame=np.zeros(link.frame_length,complex)
    head,tail=pilots(book,link)
    frame[link.guard_length:link.payload_start]=head*pilot_amplitude
    frame[link.payload_start:link.tail_start]=chips*gain
    frame[link.tail_start:link.tail_start+link.pilot_length]=tail*pilot_amplitude
    require(np.isfinite(frame).all(),"Transmit overflow")
    return frame,{"payload_gain":gain,"pilot_amplitude":pilot_amplitude,"total_tx_energy":float(total_energy)}


def shifted(values,delay):
    require(type(delay) is int and abs(delay)<len(values),"Invalid integer shift")
    result=np.zeros_like(values)
    if delay>=0: result[delay:]=values[:len(values)-delay]
    else: result[:delay]=values[-delay:]
    return result


def simulate_channel(frame,link,*,seed,delay_chips=0,phase_rad=0.,cfo_hz=0.,keep_fraction=1.,noise_std=0.,jitter_std=0.,tone_rms=0.,tone_hz=0.,erase_pilots=False):
    """Evaluator/transmitter-side simulator only. Truth fields NEVER enter a receiver packet."""
    link.validate()
    require(type(seed) is int and seed>=0,"Invalid channel seed")
    require(type(erase_pilots) is bool,"Invalid erasure switch")
    for value in (phase_rad,cfo_hz,keep_fraction,noise_std,jitter_std,tone_rms,tone_hz):
        require(type(value) in (int,float) and math.isfinite(value),"Invalid channel parameter")
    require(0<=keep_fraction<=1 and noise_std>=0 and jitter_std>=0 and tone_rms>=0,"Invalid channel range")
    y=shifted(signal_array(frame,link.frame_length),delay_chips)
    rng=np.random.Generator(np.random.PCG64(seed))
    mask=np.zeros(link.frame_length,bool)
    mask[rng.permutation(link.frame_length)[:round(link.frame_length*keep_fraction)]]=True
    time=np.arange(link.frame_length)/link.chip_rate_hz
    y*=np.exp(1j*(phase_rad+2*np.pi*cfo_hz*time+rng.normal(0,jitter_std,link.frame_length)))
    y+=noise_std/math.sqrt(2)*(rng.normal(size=link.frame_length)+1j*rng.normal(size=link.frame_length))
    y+=tone_rms*np.exp(1j*(2*np.pi*tone_hz*time+.31))
    if erase_pilots:
        for start in (link.guard_length,link.tail_start):
            indexes=np.arange(start,start+link.pilot_length)+delay_chips
            indexes=indexes[(indexes>=0)&(indexes<link.frame_length)]
            mask[indexes]=False
    y[~mask]=0
    require(np.isfinite(y).all(),"Channel overflow")
    return y,mask


def despread_aligned(aligned,mask,book,link,normalization):
    """Aligned-frame primitive; caller supplies a signal, NOT true offsets or assignments."""
    values=signal_array(aligned,link.frame_length)
    observed=observation_mask(mask,link.frame_length)
    gain=normalization["payload_gain"]
    require(type(gain) in (int,float) and math.isfinite(gain) and gain>0,"Invalid public gain")
    codes=spreading_codes(book,link)
    block=values[link.payload_start:link.tail_start].reshape(link.dimension,link.chips_per_component)
    m=observed[link.payload_start:link.tail_start].reshape(block.shape)
    # Weighted least-squares amplitude for erasures; zero-valued observed chips remain observations.
    denominator=np.sum((codes**2)*m,axis=1)
    present=denominator>0
    recovered=np.zeros(link.dimension,complex)
    recovered[present]=math.sqrt(link.chips_per_component)*np.sum(block*m*codes,axis=1)[present]/(gain*denominator[present])
    require(np.isfinite(recovered).all(),"Despread overflow")
    return recovered,present,{"observed_payload_chips":int(m.sum()),"observed_data_bearing_chips":int(np.count_nonzero(m&(codes!=0))),
                              "recovered_coordinate_count":int(present.sum()),"chips_per_coordinate":np.sum(m&(codes!=0),axis=1).tolist(),
                              "variance_note":"Partial-chip averaging is heteroscedastic; P1 thresholds are unchanged and empirically evaluated, not calibrated probabilities"}
