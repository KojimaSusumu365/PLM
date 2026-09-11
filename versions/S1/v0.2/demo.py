"""Inspectable chip arrays, received packet, and algebraic/spectral budget controls."""
from dataclasses import replace
from pathlib import Path
import numpy as np
import plm_s1_v02
from plm_p1.core import PhaseCodebook,encode,digest
from plm_p1.__main__ import write_json
from plm_p1_v02.fixtures import make_frames,public_catalogue,entity_candidates,DOC
from plm_s1_v02.link import Link,transmit,simulate_channel,spreading_codes
from plm_s1_v02.packet import to_packet
from plm_s1_v02.receiver import Session

ROOT=Path(__file__).resolve().parent


def main():
    out=ROOT/"examples"
    out.mkdir(exist_ok=True)
    book=PhaseCodebook(2048,"s1-v02-demo")
    link=Link()
    frames=make_frames(4)
    values=encode(frames,book)
    frame,norm=transmit(values,book,link)
    truth={"seed":64101,"delay_chips":-5,"phase_rad":1.8,"cfo_hz":1.0615384615384615,"keep_fraction":.25,"noise_std":.25,"jitter_std":.03}
    y,m=simulate_channel(frame,link,**truth)
    packet=to_packet(y,m,book,link,norm,source_digest=digest(frames))
    query={"document_id":DOC,"event_id":"event-000","role":"subject","candidates":entity_candidates()}
    catalogue=public_catalogue()
    session=Session(packet,catalogue,expected_book=book,expected_link=link)
    result=session.query(query)
    controls=[]
    for mode in ("direct_sparse","repeat","spread"):
        cfg=replace(link,mode=mode)
        tx,n=transmit(values,book,cfg)
        payload=tx[cfg.data_indices]
        spectrum=np.abs(np.fft.fft(payload))**2
        outside=abs(np.fft.fftfreq(len(payload)))>1/(2*cfg.chips_per_component)
        codes=spreading_codes(book,cfg)
        weights=np.sqrt(cfg.chips_per_component)*codes/(n["payload_gain"]*np.sum(codes**2,axis=1)[:,None])
        variance=np.sum(abs(weights)**2,axis=1)
        controls.append({"mode":mode,"frame_chips":len(tx),"duration_seconds":len(tx)/cfg.chip_rate_hz,
                         "total_energy":float(np.vdot(tx,tx).real),"pilot_energy":256*n["pilot_amplitude"]**2,
                         "payload_dft_energy_fraction_above_symbol_nyquist":float(spectrum[outside].sum()/spectrum.sum()),
                         "discrete_cutoff_cycles_per_chip":1/(2*cfg.chips_per_component),
                         "full_observation_noise_variance_multiplier_min":float(variance.min()),"full_observation_noise_variance_multiplier_max":float(variance.max())})
    items={"INPUT_FRAMES":frames,"CODEBOOK":book.spec,"LINK":link.spec,"QUERY":query,"PUBLIC_CATALOGUE":catalogue,
           "RECEIVED_CHIP_PACKET":packet,"RECOVERY_RESULT":result,
           "TX_CHIPS":{"scope":"transmitter/evaluator only, not provided to receiver","link":link.spec,"normalization":norm,"real":frame.real.tolist(),"imag":frame.imag.tolist()},
           "DESPREAD_VALUES":{"real":session.values.real.tolist(),"imag":session.values.imag.tolist(),"observed_mask":session.mask.tolist(),"chips_per_coordinate":session.despreading["chips_per_coordinate"]},
           "EVALUATOR_CHANNEL_TRUTH":{"warning":"audit only; never embedded into the receiver packet",**truth},
           "BUDGET_AND_SPECTRUM_CONTROLS":{"scope":"one deterministic noiseless numerical example, not a physical RF spectrum measurement","controls":controls}}
    for name,value in items.items(): write_json(out/(name+".json"),value)
    (out/"DEMO_REPORT.md").write_text("# S1チップ列デモ\n\nTX_CHIPS.jsonに8480個の明示的な複素チップを保存。RECEIVED_CHIP_PACKET.jsonはその25%を観測した信号だけで、真の遅延・位相・周波数や元のslot割当てを含みません。\n\nDESPREAD_VALUES.jsonに逆拡散後の2048成分と観測マスクを保存しています。チャネル真値は別の評価者用ファイルです。\n\nBUDGET_AND_SPECTRUM_CONTROLS.jsonは総エネルギー・時間・離散DFTの帯域外成分比・全チップ観測時の雑音分散倍率を比較します。実RF帯域や処理利得の測定ではありません。\n",encoding="utf-8")
    print("demo",result["status"],result["selected"],session.synchronization)
    print("numerical controls",controls)


if __name__=="__main__": main()


