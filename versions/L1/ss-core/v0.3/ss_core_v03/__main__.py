import argparse
import json
from pathlib import Path
from .runtime import load, run_text

parser = argparse.ArgumentParser(description='Bounded SS waveform read/generate demonstration')
parser.add_argument('--root', default=str(Path(__file__).resolve().parent.parent))
parser.add_argument('--text', required=True)
parser.add_argument('--order', choices=['preserve', 'reverse'], default='preserve')
parser.add_argument('--focus', choices=['subject', 'object'], default='subject')
args = parser.parse_args()
model = load(args.root)
result = run_text(model, args.text, args.order, [args.focus, args.focus])
print(json.dumps(result, ensure_ascii=False, indent=2))
raise SystemExit(0 if result['status'] == 'generated' else 2)
