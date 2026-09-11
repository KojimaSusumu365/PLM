# PLM-L1-SS-active v0.3：教師対応のSS保持と再発照合の最小実証

外部教師から得た文脈・答えの対応を、保護された補助SS記憶に結合・重畳し、主記憶との不一致を観察する研究用Pythonパッケージです。

**本版は観察専用です。検出器が追加教師を自動取得したり、主記憶の答えを上書きしたりすることはありません。** `eligible_for_inference=false` を維持します。

結果の判断は [REPORT.md](REPORT.md)、式と境界は [SPECIFICATION.md](SPECIFICATION.md) を参照してください。

## 主な結果

固定世界・高負荷・最終測定で、教師直後は正答だった256件中15件が再発しました。補助SSの候補不一致は15件を検出し誤警報0件、従来の相関差低下は14件を検出し誤警報108件でした。ただし別形式の保護SS記憶でも同じ結果で、結合方式固有の優位性ではありません。

補助記憶は外界の正解変更を知ることができず、未登録照会の誤支持も残ります。追加ストレス検査では、保持数を増やすと補助記憶自体が誤りました。同容量を主記憶の拡張に使う対照の方が主回答の成績は高く、システム全体の優位性を実証した版ではありません。

## 起動

Windows、Python 3.12、NumPy 2.3.5で検証しています。Python本体は同梱しません。必要なら仮想環境を作り、依存関係をインストールしてください。このREADMEのあるフォルダを作業ディレクトリにします。

```powershell
python -m pip install -r requirements.txt
$env:OPENBLAS_NUM_THREADS='1'
$env:PYTHONIOENCODING='utf-8'
python -B -m ss_trace observe --state examples/state --input examples/queries.json
```

出力は主相関、補助相関、照合結果です。`main_tentative` と `main_accepted` は0〜3の候補番号、`-1`は保留。`aux_accepted=-1` は補助記憶の保留です。`ss_disagreement=true` でも現在の答えが誤っている証明ではありません。全出力は `action=observe_only`、相関は確率ではありません。

## 教師を手動で一件提示する例

```powershell
python -B -m ss_trace ask --state examples/state --input examples/context.json --out ../active3-request.json
python -B -m ss_trace teach --state examples/state --request ../active3-request.json --feedback examples/feedback.json --out ../active3-updated
python -B -m ss_trace observe --state ../active3-updated --input examples/queries.json
```

`examples/feedback.json` は付属の人工例に対する外部教師の回答です。別の文脈・状態に使い回してはいけません。`examples/EXPECTED.json` は変更前後の期待値です。例は結果から選んだ説明用で、独立の成功率評価ではありません。

```json
{
  "schema": "plm-ss-active3-feedback",
  "request_id": "実際の要求のrequest_id",
  "source": "external_teacher",
  "label": "0"
}
```

古い要求、改変した要求、`source=model_prediction`、未知ラベルは拒否します。教師の申告を検査しますが、教師の本人性・正しさを認証する機能ではありません。照合結果を教師としてそのまま再投入しないでください。

## Pythonから新規状態を作る

```python
from ss_trace.runtime import State
from ss_trace.learning import question, answer, teacher

state = State("main512_pair", seed="my-code-0")
context = {"f0": "0", "f1": "1", "f2": "2", "f3": "3"}
request = question(state, context)
# 外部で確認した答えを与える。予測から自動的に作らない。
answer(state, request, teacher(request, "1"))
print(state.observe([context]))
state.save("../my-active3-state")
```

`answer` は検査後に状態を更新します。背景教師は `question(..., kind="background")` で主記憶だけを更新しますが、一度追加教師として登録した文脈をこの経路で無料再確認することはできません。台帳の上限は512文脈です。

## 再検証・本評価再実行

```powershell
python -B -m unittest discover -s tests -v
python -B verify_release.py --out ../active3-verify
python -B evaluate.py --out ../active3-rerun
```

出力先は**存在しない配布フォルダ外のパス**を指定してください。保存済みの配布フォルダはマニフェストで検査するため、そこへ出力やキャッシュを追加しないでください。`-B` はPythonキャッシュ生成を止めます。

`verify_release.py` は全1152保存状態から相関・指標を再計算し、全192系列の基礎学習後を再生、96基礎モデルを再学習、教師データなしの隔離実行を検査します。`evaluate.py` はさらに32件の参照取得計画から独立に全比較を再実行します。本評価一回は計画用も含め212480教師提示です。時間は環境によります。

## 構成と再現性

- `ss_trace/`：新しい観察用ランタイム、外部教師更新、CLI。
- `ss_multicode/`：v0.2由来の4ファイルをバイト不変で同梱。位相代数と旧主更新との一致検査に使います。
- `evaluation/PROTOCOL.json`、`FREEZE.json`：評価前の条件とソース凍結。
- `results/`：全ケース、参照取得計画、教師列、全測定、相関配列、1152状態。
- `tests/`、`verify_release.py`：単体試験と独立再計算・再学習検証。
- `verification/SUMMARY.json`：全条件の集計と対応差分。
- `verification/REPEATABILITY.json`、`PRESERVATION.json`：二重実行と旧版保全の証拠。
- `verification/STRESS_PLAN.json`、`STRESS.json`、`stress_states/`：主評価後に条件を固定して行った補助記憶の負荷・教師改訂検査。主評価の設定選びには使用していません。
- `verification/BENCHMARK.json`：符号キャッシュ、係数、台帳と実測照合時間。
- `examples/`：隔離した状態と外部教師例。

本版の実行に必要なコード・データ・状態は全て同梱しています。過去の大容量ZIPの再帰同梱は行わず、旧v0.2の各ファイルとZIPのハッシュを `verification/PREVIOUS_BASELINE.json` に残します。旧版は元の場所に変更なく保存します。

自然文の読解・生成、三事象化、P1/S1接続は今回の範囲外です。符号処理・学習・照合はSSですが、候補の列挙、台帳、制御、ファイル保存、採点は通常のPython/JSONです。
