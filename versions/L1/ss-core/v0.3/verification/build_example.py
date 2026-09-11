"""Actual text -> waveform read -> P1/S1 -> cold waveform generation example."""
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from ss_core_v03.runtime import load
from ss_partial.contract import from_meaning
from bridge.carrier import encode
from bridge.runtime import receive
from evaluation.experiment03 import write
from evaluation.oracle import parse

model = load(ROOT)
text = '太郎が花子を助けた。その後、もし次郎が美咲を褒めなかったら。'
reading = model.document.read(text)
assert reading['status'] == 'read'
meaning = model.document.recover(reading['packet'])['meaning']
packet = model.encode(from_meaning(meaning, model.codec.candidates))
wire = encode(model, packet, 'wave03-public-example', 'spread')
reception = receive(model, wire, 'wave03-public-example', 'spread')
assert reception['status'] == 'received'
write(ROOT/'examples/received_packet.json', reception['packet'])
code = "import json; from ss_core_v03.runtime import load; m=load('.'); p=json.load(open('examples/received_packet.json',encoding='utf-8')); print(json.dumps(m.generate(p,'reverse',['object','object']),ensure_ascii=False))"
r = subprocess.run([sys.executable, '-B', '-c', code], cwd=ROOT, capture_output=True, text=True, encoding='utf-8')
assert r.returncode == 0, r.stderr
generated = json.loads(r.stdout)
assert generated['text'] == 'もし美咲を次郎が褒めなかったら。その前に、花子を太郎が助けた。'
write(ROOT/'examples/EXAMPLE.json', {'input': text, 'reading_status': reading['status'],
      'reception': {k: v for k, v in reception.items() if k != 'packet'},
      'fresh_process_generated': generated, 'independent_parse': parse(generated['text']),
      'before_child_cost': model.engine.stats(), 'not_part_of_primary_evaluation': True})
write(ROOT/'examples/READ_TRANSPORT_TRACE.json', model.engine.trace)
print(generated['text'])
