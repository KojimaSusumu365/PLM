"""Four distributed pilots, same 8480 chips / 256 pilot chips as frozen S1 v0.1."""
from dataclasses import dataclass, asdict
import math
import numpy as np
from plm_p1.core import digest, require, signal_array, observation_mask
from plm_s1.link import _bytes, spreading_codes, spread, shifted, simulate_channel as old_channel


@dataclass(frozen=True)
class Link:
    dimension: int = 2048
    chips_per_component: int = 4
    guard_length: int = 16
    chip_rate_hz: float = 8000.
    max_delay_chips: int = 8
    max_abs_cfo_hz: float = 2.
    acquisition_max_abs_cfo_hz: float = 4.
    spreading_seed: str = "s1-v01-public-codes"
    mode: str = "spread"
    layout: str = "distributed4"

    def validate(self):
        for value, expected in ((self.dimension,2048),(self.chips_per_component,4),(self.guard_length,16)):
            require(type(value) is int and value == expected,"v0.2 uses fixed D=2048, L=4, guard=16")
        require(type(self.chip_rate_hz) in (int,float) and self.chip_rate_hz == 8000.,"v0.2 chip rate is fixed at 8000 Hz")
        require(type(self.max_delay_chips) is int and 0 <= self.max_delay_chips <= 8,"Invalid integer-delay bound")
        for value, expected in ((self.max_abs_cfo_hz,2.),(self.acquisition_max_abs_cfo_hz,4.)):
            require(type(value) in (int,float) and value == expected,"v0.2 CFO bounds are fixed at acceptance 2 / acquisition 4 Hz")
        require(type(self.spreading_seed) is str and self.spreading_seed.strip(),"Public spreading seed required")
        require(type(self.mode) is str and self.mode in {"spread","repeat","direct_sparse"},"Invalid mode")
        require(type(self.layout) is str and self.layout in {"distributed4","edge2"},"Invalid pilot layout")
        return self

    @property
    def payload_length(self): return self.dimension*self.chips_per_component
    @property
    def frame_length(self): return 8480
    @property
    def pilot_length(self): return 64 if self.layout == "distributed4" else 128
    @property
    def pilot_starts(self): return (16,3000,4700,8400) if self.layout == "distributed4" else (16,8336)
    @property
    def pilot_indices(self): return tuple(np.arange(s,s+self.pilot_length) for s in self.pilot_starts)
    @property
    def data_indices(self):
        mask=np.ones(self.frame_length,bool)
        mask[:16]=False
        mask[-16:]=False
        for ix in self.pilot_indices: mask[ix]=False
        return np.flatnonzero(mask)
    @property
    def spec(self): return asdict(self)
    @property
    def fingerprint(self): return digest(self.spec)


def pilots(book,link):
    link.validate()
    labels=("head-pilot","tail-pilot") if link.layout=="edge2" else tuple(f"distributed-pilot-{k}" for k in range(4))
    return tuple(2*(_bytes(book,link,label,link.pilot_length).astype(np.int16)%2)-1 for label in labels)


def transmit(values,book,link=Link(),*,total_energy=57344.):
    link.validate()
    require(type(total_energy) in (int,float) and math.isfinite(total_energy) and total_energy>0,"Invalid energy")
    chips=spread(values,book,link)
    energy=float(np.vdot(chips,chips).real)
    require(math.isfinite(energy) and energy>0,"Nonzero finite payload required")
    amplitude=math.sqrt(total_energy/8448)
    gain=math.sqrt(total_energy*8192/8448/energy)
    frame=np.zeros(link.frame_length,complex)
    frame[link.data_indices]=chips*gain
    for ix,p in zip(link.pilot_indices,pilots(book,link)): frame[ix]=p*amplitude
    require(np.isfinite(frame).all(),"Transmit overflow")
    return frame,{"payload_gain":gain,"pilot_amplitude":amplitude,"total_tx_energy":float(total_energy)}


def simulate_channel(frame,link,*,erase_pilots=False,**parameters):
    # Identical additive-noise/mask RNG and zero-padded capture convention to v0.1.
    require(type(erase_pilots) is bool,"Invalid erasure flag")
    y,m=old_channel(frame,link,erase_pilots=False,**parameters)
    if erase_pilots:
        delay=parameters.get("delay_chips",0)
        for ix in link.pilot_indices:
            ix=ix+delay
            m[ix[(ix>=0)&(ix<link.frame_length)]]=False
        y[~m]=0
    return y,m


def despread_aligned(aligned,mask,book,link,norm):
    values=signal_array(aligned,link.frame_length)
    observed=observation_mask(mask,link.frame_length)
    gain=norm["payload_gain"]
    require(type(gain) in (int,float) and math.isfinite(gain) and gain>0,"Invalid gain")
    codes=spreading_codes(book,link)
    block=values[link.data_indices].reshape(codes.shape)
    m=observed[link.data_indices].reshape(codes.shape)
    denominator=np.sum(m*codes**2,axis=1)
    present=denominator>0
    result=np.zeros(link.dimension,complex)
    result[present]=2*np.sum(block*m*codes,axis=1)[present]/(gain*denominator[present])
    require(np.isfinite(result).all(),"Despread overflow")
    return result,present,{"observed_payload_chips":int(m.sum()),"recovered_coordinate_count":int(present.sum()),
                           "chips_per_coordinate":np.sum(m*(codes!=0),axis=1).tolist(),
                           "variance_note":"Partial-chip noise is heteroscedastic; frozen P1 rules are empirical, not calibrated probabilities"}
