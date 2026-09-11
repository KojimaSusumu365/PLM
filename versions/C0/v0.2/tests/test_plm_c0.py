import unittest
from plm_c0 import PLMC0Engine, PositiveLexicalBaseline, compare, evaluate, load_cases
class TestPLMC0(unittest.TestCase):
    @classmethod
    def setUpClass(cls): cls.e=PLMC0Engine()
    def test_01_dog_bark(self):
        r=self.e.analyze("犬が吠えている"); self.assertEqual(r["selections"]["entity"]["selected"],"DOG"); self.assertEqual(r["selections"]["action"]["selected"],"BARK")
    def test_02_paraphrase(self):
        r=self.e.analyze(["犬が吠えている","ワンちゃんがキャンキャン鳴いている","イヌが声を出している","dog is barking"]); self.assertEqual(r["selections"]["entity"]["selected"],"DOG")
    def test_03_negation(self):
        r=self.e.analyze("犬ではなく猫だった"); self.assertEqual(r["selections"]["entity"]["selected"],"CAT"); self.assertGreater(next(x for x in r["ranking"]["entity"] if x["concept"]=="DOG")["contradiction"],0)
    def test_04_generic(self): self.assertEqual(self.e.analyze("動物が吠えている")["selections"]["entity"]["selected"],"ANIMAL")
    def test_05_financial_bank(self): self.assertEqual(self.e.analyze("I opened a bank account for my money.")["selections"]["place"]["selected"],"FINANCIAL_BANK")
    def test_06_river_bank(self): self.assertEqual(self.e.analyze("We sat on the river bank near the water.")["selections"]["place"]["selected"],"RIVER_BANK")
    def test_07_unknown(self):
        r=self.e.analyze("量子もつれについて考える"); self.assertTrue(all(r["selections"][d]["selected"]=="UNRESOLVED" for d in r["selections"]))
    def test_08_cat_sibling_contradiction(self):
        r=self.e.analyze("猫が鳴いている"); self.assertEqual(r["selections"]["entity"]["selected"],"CAT"); self.assertGreater(next(x for x in r["ranking"]["entity"] if x["concept"]=="DOG")["contradiction"],0)
    def test_09_narrowing(self): self.assertEqual(self.e.analyze("この動物は犬です")["selections"]["entity"]["selected"],"DOG")
    def test_10_vehicle(self): self.assertEqual(self.e.analyze("自動車が走っている")["selections"]["entity"]["selected"],"VEHICLE")

    def test_11_version_and_diagnostics(self):
        r=self.e.analyze("犬が吠えている")
        self.assertEqual(r["version"],"PLM-C0 v0.2")
        self.assertEqual(r["diagnostics"]["concepts_scored"],11)
        self.assertGreater(r["diagnostics"]["patterns_checked"],0)

class TestEvaluation(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cases=load_cases()
        cls.primary=evaluate(PLMC0Engine(),cls.cases,"PLM-C0 v0.2")
        cls.baseline=evaluate(PositiveLexicalBaseline(),cls.cases,"baseline")
        cls.comparison=compare(cls.primary,cls.baseline)

    def test_12_dataset_size(self): self.assertEqual(len(self.cases),36)
    def test_13_metric_ranges(self):
        for report in (self.primary,self.baseline):
            for key in ("top1_accuracy","top5_recall","mrr","unresolved_precision","unresolved_recall","minority_evidence_retention","contradiction_rejection"):
                value=report["metrics"][key]
                self.assertIsNotNone(value)
                self.assertGreaterEqual(value,0.0)
                self.assertLessEqual(value,1.0)
    def test_14_primary_beats_baseline_top1(self):
        self.assertGreater(self.primary["metrics"]["top1_accuracy"],self.baseline["metrics"]["top1_accuracy"])
    def test_15_contradiction_rejection(self):
        self.assertEqual(self.primary["metrics"]["contradiction_rejection"],1.0)
    def test_16_minority_retention(self):
        self.assertEqual(self.primary["metrics"]["minority_evidence_retention"],1.0)
if __name__=="__main__": unittest.main(verbosity=2)
