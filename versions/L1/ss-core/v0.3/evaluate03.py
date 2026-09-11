import argparse
import json
from evaluation.experiment03 import evaluate

p = argparse.ArgumentParser()
p.add_argument('--output', required=True)
p.add_argument('--split', choices=('development', 'evaluation'), default='evaluation')
a = p.parse_args()
print(json.dumps(evaluate(a.output, a.split), ensure_ascii=False, indent=2))
