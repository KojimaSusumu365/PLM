"""Read complete text or two explicitly supplied alternative readings; no ambiguity discovery."""
from plm_l1_v09.component.algebra import require
from plm_l1_v09.component.runtime import abstain
from .contract import from_meaning, cell, normalize


def read(model, texts):
    try:
        require(type(texts) is list and len(texts) in (1, 2) and all(type(t) is str for t in texts), 'one_or_two_explicit_readings')
        observations = []
        for text in texts:
            output = model.document.read(text)
            require(output['status'] == 'read', 'complete_reading_failed')
            rec = model.document.recover(output['packet'])
            require(rec['status'] == 'recovered', 'complete_signal_failed')
            observations.append(from_meaning(rec['meaning'], model.codec.candidates))
        observation = observations[0]
        if len(observations) == 2:
            other = observations[1]
            require(observation['count'] == other['count'] and observation['presentation'] == other['presentation'], 'incompatible_readings')
            different = [k for k in observation['cells'] if observation['cells'][k] != other['cells'][k]]
            require(len(different) == 1, 'exactly_one_alternative_field_required')
            key = different[0]
            observation['cells'][key] = cell('ambiguous', observation['cells'][key]['candidates'] + other['cells'][key]['candidates'])
        observation = normalize(observation, model.codec.candidates)
        packet = model.encode(observation)
        rec = model.recover(packet)
        require(rec['status'] == 'recovered' and rec['observation'] == observation, 'partial_readback_failed')
        return {'status': 'read', 'packet': packet, 'pending': rec['pending'],
                'ambiguity_source': 'externally_supplied_readings' if len(texts) == 2 else 'none', 'eligible_for_inference': False}
    except (ValueError, TypeError) as e:
        return abstain(str(e))
