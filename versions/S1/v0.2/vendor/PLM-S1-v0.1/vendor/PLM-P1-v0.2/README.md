# PLM-P1 v0.2

部分観測時の回復改善・誤受理制御とS1同期準備。

現行Python/NumPyを維持し、P1 v0.1の符号器・R1/C2観察境界を変更せず、公開候補語彙による干渉除去と観測条件に応じた復号判定を追加した実験版です。Lisp/Prolog、新しい外部サービス、追加インストールは使っていません。

## 結果の読み方

確定した結果は `results/EVALUATION_REPORT.md`、受入判断は `results/RELEASE_DECISION.md`、検証は `verification/VERIFICATION_REPORT.md`。本READMEは未知評価を実行する前に固定するため、未取得の性能を先に書き込みません。

コードが動くこと、数値目標を満たすこと、意味が正しいことは別です。全出力は観察専用で、`eligible_for_inference: false`。独立意味評価・SS型復調そのものは未完了です。

## 実装した内容

- 元の複素Phase符号を維持。否定・仮定・隔離状態、applied、訂正target_clauseを落とさない。
- 観測された成分上だけで、公開候補が張る干渉部分空間を除去。正解の状態割当てを渡さない。
- 観測成分数、除去後の自由度、残留信号パワー、候補数に応じた閾値と保留理由。
- 同じ次元・情報・送信エネルギーで、旧方式、適応判定のみ、干渉除去＋固定/適応判定、2領域分割を比較。
- 16符号seed × 4チャネルseedの未知評価、2種類の負例、過負荷・語彙外・低次元などの失敗側評価。
- 2048成分のうち128成分を使うパイロット位相同期試作。真の回転角は実際の受信器に渡さない。

公開カタログは追加のモデル知識です。主体/対象の正解対応や出来事の存在フラグではありませんが、「事前知識なし」の改善とも主張しません。合成実験では述語・状態の計11候補と、実体のない4つのdecoyアドレスを含む公開名前空間を使います。実データ用の語彙整備は別課題です。

## 実行

Python 3.12とNumPy 2.3.5で検証。以下の `python` はご自身のPython実行ファイルに置き換えられます。新モジュール名は `plm_p1_v02`、旧 `plm_p1` は同梱した固定版から読みます。

```powershell
$env:OPENBLAS_NUM_THREADS = '1'
python -B -m unittest discover -s tests -v
python -B -m plm_p1_v02 decode --packet examples/OBSERVATION_PACKET.json --query examples/QUERY.json --catalogue examples/PUBLIC_CATALOGUE.json --expected-codebook examples/CODEBOOK.json --out recovery.json
python -B -m plm_p1_v02 decode --packet examples/PILOT_PACKET.json --query examples/QUERY.json --catalogue examples/PUBLIC_CATALOGUE.json --expected-codebook examples/CODEBOOK.json --out pilot-recovery.json
python -B verify_release.py --out-dir verification-repeat
```

`--expected-codebook` を必須にして、受信側でコードブックを別途固定します。query/packetへのgoldや真のphase_offset追加は拒否します。通常信号はv0.1 wire互換です。パイロット付き信号は明示的に別wire形式です。

数値評価だけの再現:

```powershell
python -B evaluate.py --split evaluation --out-dir evaluation-repeat
```

初回評価は `FIRST_EVALUATION.json` に記録し、再実行で上書きしません。ソース変更後はfreeze検証で停止します。数値目標が未達なら `verify_release.py` はexit 1にします。旧v0.1の既知の未達だけは比較基準として明示的に扱い、機能回帰失敗と混同しません。

## 同梱資料

- `NUMERICAL_SPEC.md`: 数式、閾値、同一予算の定義と限界。
- `S1_INTERFACE.md`: パイロットの費用、受信境界、S1へ残す作業。
- `evaluation/PROTOCOL.json`, `evaluation/SELECTION.md`: 評価条件と開発段階の選択根拠。
- `results/V01_FAILURE_DIAGNOSIS.md`: 旧失敗5件の干渉分解。未知評価には数えない。
- `examples/`: 原入力（評価者用）と、原入力を含まない数値パケット・照会・公開カタログ。
- `vendor/PLM-P1-v0.1/`: 全177ファイルをそのまま保存。R1とC2も内包。

旧C2/R1の既知の意味誤りを本版で直したとは主張しません。復調成功・高い相関・数値回復成功を、観察内容の真偽判定へ昇格させる経路はありません。
