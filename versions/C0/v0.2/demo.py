import json
from plm_c0 import PLMC0Engine
engine=PLMC0Engine()
cases={
"multi_paraphrase_consensus":["犬が吠えている","ワンちゃんがキャンキャン鳴いている","イヌが声を出している","dog is barking"],
"negation":"犬ではなく猫だった",
"generic_only":"動物が吠えている",
"financial_bank":"I opened a bank account for my money.",
"river_bank":"We sat on the river bank near the water."
}
for name,value in cases.items():
    r=engine.analyze(value)
    print("\n===",name,"===")
    print(json.dumps({"inputs":r["inputs"],"selections":r["selections"],"ranking":{k:v[:4] for k,v in r["ranking"].items()}},ensure_ascii=False,indent=2))
