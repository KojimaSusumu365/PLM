"""Generate artificial fixtures before calibration/freeze, never at prediction time."""
import json
from evaluation.cases import make_case, validate
from evaluation.integrity import ROOT, write


def main():
    p = json.loads((ROOT / 'evaluation/PROTOCOL.json').read_text(encoding='utf-8'))
    cases = {key: [make_case(s) for s in p[key + '_seeds']] for key in ('development', 'evaluation')}
    assert all(validate(c) for cs in cases.values() for c in cs)
    assert not set(p['development_seeds']) & set(p['evaluation_seeds'])
    write(ROOT / 'data/CASES.json', cases)
    print('Prepared2 development and4 final datasets')


if __name__ == '__main__': main()
