import json
from pathlib import Path
from ss_partial.runtime import PartialModel
from ss_core_v03.training import transfer
from ss_core_v03.waveform import Engine

root = Path(__file__).resolve().parent
model = PartialModel.load(root/'model')
programs, audit = transfer(model.document.base.component, Engine())
for name, program in zip(('sentence', 'document'), programs):
    program.save(root/'programs'/name)
(root/'programs/TRAINING.json').write_text(json.dumps(audit, ensure_ascii=False, sort_keys=True, indent=2)+'\n', encoding='utf-8')
print(audit)
