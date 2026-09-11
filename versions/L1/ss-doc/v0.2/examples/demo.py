"""Two explicitly supplied readings -> numeric ambiguity -> external value -> text."""
import json
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from ss_partial.runtime import PartialModel
from ss_partial.reader import read
from ss_partial.update import request, apply


def demo():
    model = PartialModel.load(ROOT / 'model')
    texts = [
        '太郎が花子を助けた。その後、花子が健太を褒めた。その後、健太が美咲を訪ねた。',
        '太郎が花子を助けた。その後、由紀が健太を褒めた。その後、健太が美咲を訪ねた。']
    initial = read(model, texts)
    assert initial['status'] == 'read'
    packet = initial['packet']
    before = model.generate(packet)
    teacher = request(packet, 'event:1/subject', 'entity:由紀')
    update = apply(model, packet, teacher)
    assert update['status'] == 'updated'
    after = model.generate(update['packet'])
    reverse = model.generate(update['packet'], 'reverse')
    # An unmarked disagreement becomes a conflict, not a second automatic answer.
    contradiction = apply(model, update['packet'], request(update['packet'], 'event:1/subject', 'entity:花子'))
    assert contradiction['status'] == 'conflict'
    after_conflict = model.generate(contradiction['packet'])
    resolved = apply(model, contradiction['packet'], request(contradiction['packet'], 'event:1/subject', 'entity:由紀', 'resolve'))
    assert resolved['status'] == 'updated'
    record = {'explicit_readings': texts, 'ambiguity_source': 'externally_supplied_not_discovered',
              'before': before, 'teacher': teacher, 'update_audit': update['audit'],
              'after': {k: v for k, v in after.items() if k != 'link_audit'},
              'reverse': {k: v for k, v in reverse.items() if k != 'link_audit'},
              'after_conflict': after_conflict,
              'after_explicit_resolution': {k: v for k, v in model.generate(resolved['packet']).items() if k != 'link_audit'},
              'is_independent_primary_sample': False, 'persistent_learning': False}
    return record, {'pending': packet, 'corrected': update['packet'], 'conflict': contradiction['packet'], 'resolved': resolved['packet']}


if __name__ == '__main__':
    print(json.dumps(demo()[0], ensure_ascii=False, indent=2))
