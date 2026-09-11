# PLM-L1 v0.8：二事象の時間関係の学習と意味保持生成

「その後、」「その前に、」「関係の記述なし」という三つの限定表現と、二事象の前後／順序不明の対応を、文章・意味の対から位相連想記憶へ学習する。出来事の局所ID、文章での提示順、時間関係を別々に一つの数値信号へ保持し、提示順を逆にしても時間関係を保持する最小実証。

日本語一般の時間表現、因果推論、自由長文の生成器ではない。前段の提案で例にした「〜する前に」という埋込み節は今回は扱わず、明示二文＋接続prefixに範囲を絞る。結果は `results/REPORT.md` と `results/RELEASE_DECISION.md`、全件は `results/EVALUATION.json`。

## 起動例

Python 3.12 / NumPy 2.3.5。Python本体は同梱しない。必要な環境だけ `python -m pip install -r requirements.txt`。このREADMEのあるフォルダで実行する。

```powershell
$env:OPENBLAS_NUM_THREADS='1'
$env:PYTHONIOENCODING='utf-8'
python -B -m plm_l1_v08 read --model results/model --text '太郎が花子を助けた。その後、花子が健太を褒めた。' --out work/packet-01.json
python -B -m plm_l1_v08 recover --model results/model --packet work/packet-01.json
python -B -m plm_l1_v08 generate --model results/model --packet work/packet-01.json --order reverse --goals subject subject
```

対応が保持される場合の出力は「花子が健太を褒めた。その前に、太郎が花子を助けた。」。`--order`はpreserve/reverseの提示順、`--goals`は出力する第一／第二文それぞれの文内語順で、実際の時間順を上書きする指定ではない。

```powershell
python -B -m plm_l1_v08 encode --model results/model --meaning examples/MEANING.json --out work/direct-01.json
python -B -m plm_l1_v08 generate --model results/model --packet work/direct-01.json --order reverse --goals object subject
python -B -m plm_l1_v08 train --component-pairs data/component_train.json --temporal-pairs data/temporal_train.json --lexicon data/lexicon.json --seed temporal-evaluation-0 --out work/refit-01
python -B -m unittest discover -s tests -v
python -B verify_release.py --out work/verify-01
python -B evaluate.py --out work/evaluation-01
```

出力を上書きしないため、再実行時は新しい出力名を指定する。保留は終了コード2。未知接続表現、未対応文、不正パケット、弱い相関、片方だけの成功は文書全体の保留となり、部分的なパケット／完成文を成功として返さない。

`verify_release.py`は保存結果の再採点、全世代テスト、隔離学習・隔離生成を確認する。全数値評価の再実行は`evaluate.py`で別に行う。`--preflight`は凍結前の隔離境界検査のみで、全テスト・全評価を実行した意味ではない。

## 学習・意味の境界

- 一事象部品はv0.6と同じ432対・同じseed・8192次元で再学習し、コード・主部品fingerprintを維持。
- 時間関係は216文／意味対（204種類の表面文）から学習。読み方・書き方それぞれ六つの完全関係キーをSS/VSA型位相記憶へ保持する。実行時に「その後ならbefore」のPython分岐や意味対応表を置かない。
- 初期語義、グラフスキーマ、field選択、句点／読点分割、局所ID、位相結合は設計。構造発見や全SS学習を達成したとは言わない。
- 記述なしは学習したempty-marker→unknownの対応。未知markerをunknownへ置き換えるのではなく、学習から得たmarker在庫で保留する。
- 事象IDはパケット内の局所的な提示発生の識別子。生成時に再割当てせず、提示順だけを変える。再読解時はIDを新しく付け、評価では対応を明示して比較する。文書間の同一事象認定ではない。
- 肯否・仮定は各事象に保持するが、両者が現実に生起した証明ではない。仮定の作用域を含む時間論理や、非生起区間の推論は扱わない。
- 転送はreal/imag一組の数値パケットだけ。原文・事象一覧・時間関係JSON・提示順ヒント・goldを生成器へ渡さない。全出力で`eligible_for_inference=false`。

## 評価の位置付け

各splitで順序を無視しても重ならない36事象対を使い、開発・評価は各864要求（表面文816種類）。時間関係三値、ID提示順二通り、文内語順四通りを比較する。時間学習には主体／主体の文内語順だけを使い、他の三組合せと新しい事象対を評価に残す。ただし一事象の語彙・文法・分割の土台は既存プロジェクトからの再利用で、独立に収集した人手自然文コーパスではない。

bound、分割配置partitioned、方向を消したundirectedを比較する。partitionedは同じD係数・期待平均エネルギーで、全RAMや速度を揃えた対照ではない。通常表でも六つの関係対応を実現できることを確認し、SS固有の優位性を主張しない。

仕様は `SPECIFICATION.md`、固定条件は `evaluation/PROTOCOL.json`。`vendor/PLM-L1-v0.7`は旧版411ファイルをそのまま保存し、旧版回帰・人工文法による採点に使用する。新ランタイム・新学習器はvendorを参照しない。

v0.6の記憶負荷偏り、P1部分観測／S1チップ・同期接続、三事象以上、代名詞・省略、R1推論・Concept更新は未実施。Windowsでは再帰vendorのパスが長いため、短い場所へ展開する。
