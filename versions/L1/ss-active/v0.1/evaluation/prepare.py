import json
from evaluation.cases import make_case, validate
from evaluation.integrity import ROOT, write


def main():
    p = json.loads((ROOT/'evaluation/PROTOCOL.json').read_text(encoding='utf-8'))
    data = {key: [make_case(seed, size) for seed in p[key+'_seeds'] for size in p['group_sizes']] for key in ('development', 'evaluation')}
    assert all(validate(c) for cases in data.values() for c in cases)
    write(ROOT/'data/CASES.json', data)
    print('Prepared development and evaluation cases')


if __name__ == '__main__': main()
