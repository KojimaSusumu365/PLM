# PLM-L1 v0.6：負荷対応型SS連想記憶と未登録照会の誤受理抑制

既知部品の新しい組合せを読む・書く v0.5 の言語系に、学習時の負荷に応じた記憶分割と、部分キー／候補値の独立な位相確認信号を追加する。Python + NumPy の限定実証であり、汎用の文章理解・生成モデルではない。

判定結果は `results/REPORT.md` と `results/RELEASE_DECISION.md`、各照会の全記録は `results/EVALUATION.json`、検証は `verification/` に置く。開発用実行と固定後の評価を区別する。`vendor/PLM-L1-v0.5` は旧版をそのまま保存した評価用資料で、新ランタイムの依存先ではない。

## 起動

Python 3.12、NumPy 2.3.5 で検証する。Python自体は同梱しない。以下は、このREADMEのあるフォルダで実行する例。インストールが必要な場合だけ `python -m pip install -r requirements.txt` を行う。

```powershell
$env:OPENBLAS_NUM_THREADS='1'
$env:PYTHONIOENCODING='utf-8'
python -B -m plm_l1_v06 read --model results/model --text '花子を太郎が助けなかった。' --out work/read-packet.json
python -B -m plm_l1_v06 generate --model results/model --packet work/read-packet.json --goal subject
python -B -m plm_l1_v06 encode --model results/model --meaning examples/MEANING.json --out work/direct-packet.json
python -B -m plm_l1_v06 generate --model results/model --packet work/direct-packet.json --goal object
```

生成側への入力は数値の意味パケットと目標語順だけで、元の文・正解意味・読解トレースは渡さない。目標は `subject` / `object`。未登録語・未対応文法・弱い相関・整合性不良は `abstain` で終了コード2となり、読解時にパケットファイルを作らない。全パケットで `eligible_for_inference=false` を維持する。

出力は上書きしない。再実行時は別の新しい出力名を指定する。

## 再学習・試験

```powershell
python -B -m plm_l1_v06 train --pairs data/folds/object_negative/train.json --lexicon data/lexicon.json --seed banked-evaluation-0 --dimension 8192 --memory-mode split_proof --out work/refit-model
python -B -m unittest discover -s tests -v
python -B evaluate.py --out work/evaluation-rerun
python -B verify_release.py --out work/verification-rerun
```

`evaluate.py` は固定ソースと評価条件を確認して全比較を実行するため、機械により数分以上かかる。`verify_release.py` は保存結果の判定・新版と旧版のテスト・物理的に分離した学習／生成を検証する。後者は全数値評価の再実行ではない。`work/` は配布ハッシュの対象外で、新しい作業出力に使える。

`--memory-mode` の比較方式：

|方式|負荷に応じた分割|組の確認信号|値記憶に使う係数|
|---|---|---|---:|
|single|なし|なし|D|
|split|あり|なし|D|
|proof|なし|あり|3D/4|
|split_proof（既定）|あり|あり|3D/4|
|split_unchecked|あり|計算・記録するが判定には使わない|3D/4|

確認信号のD/4も総係数予算Dに含める。`split_unchecked` は `split_proof` と同じ配列を持つ確認判定の切り分け用であり、運用上推奨する方式ではない。Dは各学習マスクあたり128～16384の128倍数。同時に意味コーデックの次元としても使うが、記憶試験は言語系から分離して実施する。

## 重要な範囲

- 「負荷対応」は学習時の分割数選択。運用中の追加学習・負荷監視・再分割は未実装。
- 分割と照合は学習で選んだ部分キーに対して行う。全文が未登録という理由だけでは拒否しない。既知の部分キーの新しい組合せを許容する。
- 同一予算比較は、記憶サブシステムの重み・メタデータ予約領域・固定キャッシュ・所有Pythonオブジェクトに限定。プロセス全体のRAMや一時領域が同じという意味ではない。詳細は `SPECIFICATION.md`。
- 誤受理の抑制と正答の保留増加にはトレードオフがある。分割単独が常に有利、確認信号が完全な存在証明、あるいは全負荷で容量が増えたとは主張しない。
- 単一事象・五つの意味スロットと限定された語彙／文法を継続する。高負荷の記憶試験は、言語の語彙・文法や意味スロットを増やす実験ではない。
- SS/VSA型位相符号の重畳・結合・相関を使用するが、依存特徴の選択は通常のID3型学習。語彙分割・構造分解・ルーティング・制御にも通常Pythonを使う。「ほぼすべてSS」の完成版ではない。
- P1の部分観測やS1の明示チップ列・パイロット同期との接続、複数事象、長文、R1推論の開放、Concept更新はこの版の範囲外。

旧版パケットはモデルと契約の取り違えを防ぐため新モデルでは拒否する。元データは過去版と共通で、モデル再学習に対する未学習組合せを検査するものであり、プロジェクトとして一度も見ていない自然言語コーパスによる独立実証ではない。
