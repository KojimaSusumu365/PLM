# PLM-L1 v0.7：二事象の分離表現と意味保持生成

明示的に区切られた二文を読み、二つの出来事の主語・目的語・述語・肯否・仮定を一つのSS/VSA型位相信号に結合する。生成側はその数値信号から二事象を取り出し、それぞれの語順を変えて書く。原文を生成器に渡さない。

今回のv0.7は二事象の最小実証。先に提案したv0.6の負荷偏り対策とは別の作業であり、その弱点を解決した版ではない。

## 起動例

Python 3.12 / NumPy 2.3.5を想定し、Python本体は同梱しない。必要な場合だけ `python -m pip install -r requirements.txt`。このREADMEのフォルダで実行する。

```powershell
$env:OPENBLAS_NUM_THREADS='1'
$env:PYTHONIOENCODING='utf-8'
python -B -m plm_l1_v07 read --model results/model --text '太郎が花子を助けた。花子が太郎を助けなかった。' --out work/packet.json
python -B -m plm_l1_v07 recover --model results/model --packet work/packet.json
python -B -m plm_l1_v07 generate --model results/model --packet work/packet.json --goals object subject
```

意味が正しく保持される場合の出力は「花子を太郎が助けた。花子が太郎を助けなかった。」。二事象の順は保持し、第一文だけ目的語先行に変える。`--goals` の二項は、それぞれの事象の文内語順であり、時間順や因果関係を指定するものではない。

```powershell
python -B -m plm_l1_v07 encode --model results/model --meaning examples/MEANING.json --out work/direct-packet.json
python -B -m plm_l1_v07 generate --model results/model --packet work/direct-packet.json --goals subject object
python -B -m plm_l1_v07 train --pairs data/folds/object_negative/train.json --lexicon data/lexicon.json --component-seed banked-evaluation-0 --event-seed events-evaluation-0 --out work/refit-model
python -B -m unittest discover -s tests -v
python -B evaluate.py --out work/evaluation-rerun
python -B verify_release.py --out work/verification-rerun
```

出力は上書きしない。再実行では新しい出力名を使う。保留は終了コード2。第二文が読めない場合も、部分的な意味パケットや第一文だけの生成を成功として出力しない。`work/` は配布整合性検証の対象外で、作業出力に使える。

## 内容と制約

- 一事象の読み方・書き方は、v0.6と同じ432文／意味対から学習する。v0.6の部品コードを変更せず同梱し、主モデルの部品重みも一致させる。
- 二事象の区切り・位置符号・結合規約は設計済みで、学習により獲得したものではない。二事象の教師例は訓練に使わない。
- 標準方式 `bound` は同じD係数へ二事象を重ねる。`partitioned` は前半／後半に分ける対照、`unbound` は事象符号を外す診断用。後者は順序情報を失うため通常利用には適さない。
- 数値パケットは一組のreal/imag配列だけ。原文・二事象の意味一覧・二つの下位パケット・正解候補の絞り込みを添付しない。`recover` は確認用に復元した意味を表示するが、その表示を生成器へ転送する経路ではない。
- 二文を句点「。」で明示的に区切る。代名詞、省略、未知語、三つ以上の出来事、自由長文は対象外。提示順は扱うが、時間・因果・矛盾の解決は行わない。
- 既知部品の新しい二文組合せを制御文法で評価する。新しい自然文文法の学習や、独立した人手コーパスへの一般性を示すものではない。
- 基底生成・結合・重畳・相関は位相演算だが、特徴学習・分割・制御・文字列組立には通常Pythonが残る。全SS学習、P1観測マスク/S1チップ列・同期の接続、R1推論開放、Concept更新は行わない。

仕様は `SPECIFICATION.md`、結果は `results/REPORT.md` と `results/RELEASE_DECISION.md`、各試行は `results/EVALUATION.json`、検証は `verification/`。`vendor/PLM-L1-v0.6` は旧版回帰・独立採点用で、新しいランタイムはvendorを参照しない。
