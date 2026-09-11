# PLM-S1 v0.2

周波数曖昧性の低減と同期の誤受理対策。Python/NumPyを維持し、旧S1 v0.1全330ファイル（P1/R1/C2を含む）を無変更で保存しています。

P1の2048複素成分を4チップずつに拡散する処理は維持。256パイロットチップを前後2か所から4か所へ再配置し、広い周波数探索、候補競合の検査、補正後のブロック整合性検査を追加しました。総8480チップ、総送信エネルギー57344は旧版・各対照方式と同じです。

この版は人工離散複素ベースバンドの実験実装です。RF実機、独立意味評価、認証は未実施。復調や同期の成功は意味の真偽ではなく、`eligible_for_inference: false` を維持します。

## 結果・検証

本READMEと実装は未使用seedの評価前に固定します。確定結果は `results/RELEASE_DECISION.md`、全条件は `results/EVALUATION_REPORT.md`、機能検証は `verification/VERIFICATION_REPORT.md` を参照してください。

回復評価は旧S1、直接参照、非拡散反復、新SS、真の補正を使う評価専用oracleの5方式。同期評価は新SS、配置だけを旧型へ戻す対照、旧受信器を比較します。oracle以外の受信器へ真値は渡しません。

## 実行

Python 3.12 / NumPy 2.3.5。新しいライブラリや外部サービスは導入していません。展開したPLM-S1-v0.2フォルダで実行します。`python` は利用するPython実行ファイルに置き換えてください。

```powershell
$env:OPENBLAS_NUM_THREADS = '1'
python -B -m unittest discover -s tests -v
python -B -m plm_s1_v02 decode --packet examples/RECEIVED_CHIP_PACKET.json --query examples/QUERY.json --catalogue examples/PUBLIC_CATALOGUE.json --expected-codebook examples/CODEBOOK.json --expected-link examples/LINK.json --out recovered.json
```

デモの受信信号は25%チップ観測、−5チップ遅延、約1.061538 Hzの周波数ずれ、位相・雑音を含みます。受信パケットに真値はありません。送信チップ列と真値は評価者用の別ファイルです。

全世代テスト・CLI・旧版部分回帰と、新S1 v0.2数値評価の全再実行:

```powershell
python -B verify_release.py --out-dir verification-repeat
```

全新数値評価だけを再現:

```powershell
python -B evaluate.py --split evaluation --out-dir evaluation-repeat
```

新数値評価の再計算のみを省く短い検証:

```powershell
python -B verify_release.py --smoke-only --out-dir smoke-repeat
```

旧S1 v0.1は1440照会・60同期監査、旧P1 v0.2は1440照会の部分回帰を再実行します。旧版の全数値結果はファイルハッシュで保存を確認し、毎回すべて再計算したとは主張しません。

## 主なファイル

- `NUMERICAL_SPEC.md`: 配置・周波数探索・保留条件・公平性・限界。
- `S1_INTERFACE.md`, `WIRE_CONTRACT.json`: 新wire形式と観察専用境界。
- `evaluation/PROTOCOL.json`, `evaluation/SELECTION.md`: 評価前の条件固定と開発判断。
- `evaluation/PILOT_LAYOUT_SEARCH.json`: 信号の周波数応答だけで比較した837配置。
- `examples/`: 明示チップ列、受信パケット、逆拡散値、実際の復号例。
- `SOURCE_MANIFEST.json`, `EVALUATION_STARTED.json`, `FIRST_EVALUATION.json`: 固定・開始・初回結果の記録。

## 制約

受入周波数は±2 Hz、探索は±4 Hz。±1.9 Hzまでを主な取得率評価、±2 Hz近傍を境界評価とします。範囲外の試験点で拒否できても、あらゆる範囲外信号への保証にはなりません。

1チップ1サンプルでは8000.1 Hzと0.1 Hzが同じ離散列になり、識別できません。また、有効パイロットだけでも同期は成立し、送信者やペイロードの認証にはなりません。この2点も失敗・限界側の試験として明示します。

分数チップ遅延、サンプル時計ずれ、時間変動CFO、マルチパス、RF前段は未実装です。25%チップ観測はP1成分の25%観測とは異なり、復元成分のカバー率を別途報告します。
