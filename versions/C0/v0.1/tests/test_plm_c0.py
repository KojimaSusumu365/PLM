import unittest
from plm_c0 import PLMC0Engine
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
if __name__=="__main__": unittest.main(verbosity=2)
