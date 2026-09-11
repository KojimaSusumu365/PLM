"""Reproducible test runner; writes only verification artifacts."""
import io
from pathlib import Path
import unittest
import sys


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    root = Path(__file__).resolve().parent
    buffer = io.StringIO()
    suite = unittest.defaultTestLoader.discover(str(root / "tests"))
    result = unittest.TextTestRunner(stream=buffer, verbosity=2).run(suite)
    (root / "TEST_OUTPUT.txt").write_text(buffer.getvalue(), encoding="utf-8")
    passed = result.testsRun - len(result.failures) - len(result.errors) - len(result.skipped)
    report = ("# PLM-C2 v0.4 テスト結果\n\n"
              f"実行 {result.testsRun}、合格 {passed}、失敗 {len(result.failures)}、エラー {len(result.errors)}、skip {len(result.skipped)}。\n\n"
              "旧版ごとの凍結実装テストに加え、v0.4の意味役割・個体照応・訂正根拠・校正・R1観察境界を検証。\n"
              "不正Schema、参照先欠落、元文章との不一致、グラフ破損、主体差し替え、推論モード要求も検査した。\n\n"
              "再実行: `python -B verify_release.py`。詳細はTEST_OUTPUT.txt。\n")
    (root / "TEST_REPORT.md").write_text(report, encoding="utf-8")
    print(report)
    if not result.wasSuccessful():
        print(buffer.getvalue())
        raise SystemExit(1)


if __name__ == "__main__":
    main()
