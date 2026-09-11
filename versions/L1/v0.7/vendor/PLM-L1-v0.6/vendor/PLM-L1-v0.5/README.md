# PLM-L1 v0.5：読解受理と意味信号の整合・干渉耐性の検証

v0.4の部品再利用型の読解・生成を維持し、読解が成功を返す条件に『出力する数値意味信号を復元でき、読解時に選んだ意味と一致すること』を加えます。
これは受理契約の修正です。新しい意味回復アルゴリズム・雑音除去・容量適応の完成を意味しません。
確定結果はresults/EVALUATION_REPORT.md、到達点と限界はresults/RELEASE_DECISION.mdに保存します。本READMEは固定評価前に凍結します。

## 変更したこと

1. 文・意味対から学習した部品で、文章の意味候補を選ぶ（v0.4と同じ）。
2. 候補を5スロットの位相意味信号へ変換する（v0.4と同じ）。
3. その信号を復元し、候補との完全一致を確認する（v0.5で追加）。
4. 復元不能はmeaning_signal_unrecoverable、不一致はmeaning_signal_mismatchとして保留し、パケットを出さない。

正解意味を読解器へ与えません。自身の誤った意味候補を一貫して符号化できてしまう可能性はあるため、この確認だけで意味の正しさを証明したとは扱いません。別実装の限定文法による独立採点を続けます。
数値符号・学習された重み・特徴選択・相関閾値・残差閾値・生成方式は据え置きます。新旧は同じ432対・seed・次元で再学習し、数値重みが完全一致することを確認します。

## 起動方法

Python 3.12 / NumPy 2.3.5。Python本体は同梱しません。ZIPを展開し、PLM-L1-v0.5フォルダで実行します。

```powershell
$env:OPENBLAS_NUM_THREADS='1'
$env:PYTHONIOENCODING='utf-8'
python -B -m plm_l1_v05 read --model results/model --text '花子を太郎が助けなかった。' --out work/meaning.json
python -B -m plm_l1_v05 generate --model results/model --packet work/meaning.json --goal subject
```

再学習する場合：

```powershell
python -B -m plm_l1_v05 train --pairs data/folds/object_negative/train.json --lexicon data/lexicon.json --seed checked-evaluation-0 --out work/my-model
```

付属モデルは対象先行×否定の144対を外した432対で学習します。旧版の全学習済み重みは使いません。語種・語義・5意味スロットは初期知識です。
初期語彙6人・4動詞、2語順、肯否×断定形/仮定形、1出来事、最大9トークンの範囲です。仮定形は後件のない実験用の条件節です。
モデル・パケットは未使用の出力名を指定し、上書きしません。読解/生成の保留は終了コード2、形式エラーは1です。保留時には意味パケットや部分的な完成文を出しません。

## 信号契約

読解成功の外側の応答にsignal_verified=trueと検証方法を付けますが、この情報を数値パケットに埋め込みません。受信側のgenerateは毎回recoverで検査し、以前の読解成功を根拠に検査を省略しません。
パケットはschema/model_fingerprint/dimension/real/imag/eligible_for_inferenceのみ。原文・意味ラベル・trace・検証済みフラグ等の追加は拒否します。
モデルschemaはplm-l1-checked-v1、パケットschemaはplm-l1-checked-meaning-v1。v0.4のモデル/パケットを暗黙に新版として読み込まず、同じ数値符号でも版を区別します。
fingerprintは整合性識別で、認証ではありません。別の有効な意味信号への置換を検知する機能はありません。

encodeコマンドは意味から数値信号を構成するだけです。低次元でその信号を復元可能だと保証するものではなく、readの受理契約とは区別します。

```powershell
python -B -m plm_l1_v05 encode --model results/model --meaning examples/MEANING.json --out work/direct.json
python -B -m plm_l1_v05 generate --model results/model --packet work/direct.json --goal object
```

## 再検証

```powershell
python -B -m unittest discover -s tests -v
python -B evaluate.py --out work/evaluation-repeat
python -B verify_release.py --out work/verification
```

evaluateは全数値評価を再実行します。verify_releaseはソース/保存結果・機能テスト・物理的に分離した学習/生成環境を検証する別コマンドです。
work/は利用者の再実行用の保存場所として、配布ファイル一覧検査から除外します。

## 試験を分ける理由

| 試験 | 変えるもの | 測るもの |
|---|---|---|
| 標準の新旧比較 | 受理ゲートのみ | 未学習組合せの読解・生成・往復の正解維持 |
| 言語モデルの低次元試験 | 次元・符号seed | 復元不能の受理、整合した誤読、保留 |
| 意味信号の雑音試験 | 読解後の数値信号に加える相対L2雑音 | 復元と生成の正解/誤受理/保留、入力全体での生成率 |
| 連想記憶の負荷試験 | 8候補のまま格納対応数を8〜256へ | 格納アドレスの回復と未格納アドレスの誤受理 |

負荷試験は独立した記憶部品の実験で、言語モデルの語彙や意味スロットを拡大する実装ではありません。
雑音は複素ガウス方向をノルム調整した数値摂動で、S1のチップ列や同期・RF環境のモデルではありません。
雑音後の成功率は転送できたパケットに条件付けた率と、読解保留も含む元の全要求に対する率を分けます。

標準条件では全6区分の正解率98%以上・v0.4の正解数維持・誤受理なしを要求します。全保留を合格としません。
低次元の既知2例は既知不具合の回帰で、未知評価とはしません。高負荷や雑音下での意味誤り・未格納誤受理は非合否の測定として残し、結果を見て閾値を変えません。
元コーパス576/192/192と4分割は既存v0.4からの再利用です。各foldの未学習組合せ48要求×4fold×4符号は、768種類の新規自然文を意味しません。

## SS方式としての位置付けと未実装範囲

主要な対応照合・意味回復は位相相関を使います。追加した受理ゲートも数値信号を実際に復元しますが、候補比較・分岐は通常のPython補助処理です。
特徴選択は通常の情報利得による記号・統計処理、部品分割は手設計のままです。v0.4で部分共有型の通常表引きも成功した事実は変わらず、SS独自の優位性は主張しません。
P1の観測数値成分マスク・干渉除去、S1同期受信器との統合、負荷適応、未知語義・階層・複数出来事・長文、全学習のSS化は未実装です。
R1推論/Concept更新は開放せず、出力はeligible_for_inference=false。旧L1/P1/S1の成果物は保持し、vendor/PLM-L1-v0.4に旧版をバイト同一で同梱します。
