# PLM-L1-SS-core v0.2

独立再照合と更新前後の整合検査による誤更新抑制。

SS記憶を別の読出し窓で再観測し、更新案を再読出しして外部教師との整合を調べる。保留時にはSS係数と版を維持し、値を含まない要再確認フラグを保存する。正しい教師の再受理後に生成を再開する。

この検査は完全な安全保証ではない。全観測に共通する一貫した破損や、教師自体の誤りは検出できない場合がある。単純な反復平均との比較、過剰保留、失敗例を含む数値は `REPORT.md` を参照。

## 内容

- `ss_core_v02/`: 新しい更新ゲート、保留台帳、生成入口、CLI。
- `ss_core/`: 変更していない前版の逐次波形コア。
- `bridge/`, `ss_*`, `plm_l1_v09/`, `vendor/`, `model/`: 接続に必要な既存実装とモデル。
- `data/GUARD_CORPUS.json`: 新しい開発・評価データ。`CORE01_*` は前版の未評価更新を追跡する保存係数・結果。
- `evaluation/`, `evaluate.py`: 固定プロトコル、故障モデル、独立限定文法評価、全比較実験。
- `tests/`: 継承30＋新規23=53テスト。
- `results/`: 主比較336試行、各試行の直後・後続学習後の保存物、生成文、採点、旧更新追跡。
- `examples/reconfirmation/`: 保留から再確認への実行例、実際の波形NPZ、別プロセス生成結果。
- `verification/`, `verify_release.py`: 保全、試験、反復比較、隔離推論、配布検証。
- `SPECIFICATION.md`, `CORPUS.md`, `REPORT.md`: 仕様、データ設計、実施結果と限界。

前版全体のZIPを再収納したものではなく、今回の再現に必要なコード・モデル・資料・結果を同梱する。新しい語彙・文法の学習や実回路化は行っていない。

## 再現

Python 3.11以降とNumPy 2.3.5を使用する。実行確認はWindows/Python 3.12.14。以下はZIPの展開先直下で実行する。必要に応じて `python` を環境のPythonのフルパスに置き換える。

```powershell
$env:OPENBLAS_NUM_THREADS='1'
$env:PYTHONIOENCODING='utf-8'
python -B -m unittest discover -s tests -v
python -B evaluate.py --out ../ss-core02-repeat
python -B verify_release.py --out ../ss-core02-verify --repeat ../ss-core02-repeat
```

出力先は新規の外部ディレクトリを使う。既存結果や保存記憶は上書きしない。完全評価は多数の保存・再ロード・生成を含むため数分以上かかる。ネットワークや外部LLMサービスは不要。

## 再確認待ちの保存物を照会

```powershell
python -B -m ss_core_v02 generate --model model --memory examples/reconfirmation/held-store --scope examples/reconfirmation/scope.json --wire examples/reconfirmation/query-wire.json --message-id demo02/query
```

`needs_confirmation`、終了コード2となり、旧値で文章を出さない。

## 正常な教師で再確認

```powershell
python -B -m ss_core_v02 learn --model model --memory examples/reconfirmation/held-store --scope examples/reconfirmation/scope.json --wire examples/reconfirmation/final-wire.json --message-id demo02/final --out ../ss-core02-confirmed --method guard
python -B -m ss_core_v02 generate --model model --memory ../ss-core02-confirmed --scope examples/reconfirmation/scope.json --wire examples/reconfirmation/query-wire.json --message-id demo02/query --order reverse --goals object subject
```

学習時の `--method` は `single`、`mean4`、`unchecked`、`guard`（既定）を選択できる。新規記憶を作る場合はlearnの `--memory` を省く。

重要：learnは更新を保留・拒否した場合も、新しい出力先へ保留台帳を保存する。この場合の終了コードは2。成功時だけ保存する前版CLIと異なる。返された新しい保存物を次の照会に使わず、古い保存物を使い続ければ、要再確認フラグは反映されない。

生成は教師ファイルや学習時の領収書を必要としない。CLIに登録する教師の真偽や送信者の認証機能はない。
