# PLM-L1 v0.6 評価結果

固定予算の記憶サブシステム比較。未登録照会の拒否率と、登録照会の正答・誤答・保留を分けて評価する。

## 言語試験

|方式|未学習組合せ・読解|未学習組合せ・生成|両側未学習・往復|全往復|
|---|---:|---:|---:|---:|
|single|768/768|768/768|768/768|6144/6144|
|split_proof|768/768|768/768|768/768|6144/6144|
|split_unchecked|768/768|768/768|768/768|6144/6144|

## 独立記憶試験・通常のキー分布（全負荷合算）

|方式|登録照会数|正答|誤答|保留|未登録照会の誤受理|
|---|---:|---:|---:|---:|---:|
|single|3392|2519|307|566|498/4096|
|split|3392|2469|308|615|489/4096|
|proof|3392|1995|125|1272|190/4096|
|split_proof|3392|1937|128|1327|173/4096|
|split_unchecked|3392|2338|387|667|616/4096|

未登録誤受理の合算減少率：65.3%。登録正答の維持率：76.9%（single比）。

これは異なる負荷条件を等しい試行構成で合算した値であり、運用時のエラー確率や統計的有意性ではない。負荷ごとの数値を以下に残す。

|分布|D|N|方式|正答|誤答|保留|未登録誤受理|
|---|---:|---:|---|---:|---:|---:|---:|
|forced_single_bank|2048|128|single|251/256|0|5|1/256|
|forced_single_bank|2048|128|split|136/256|18|102|11/256|
|forced_single_bank|2048|128|proof|205/256|0|51|0/256|
|forced_single_bank|2048|128|split_proof|85/256|7|164|5/256|
|forced_single_bank|2048|128|split_unchecked|126/256|31|99|26/256|
|ordinary|128|8|single|16/16|0|0|0/256|
|ordinary|128|8|split|16/16|0|0|0/256|
|ordinary|128|8|proof|14/16|0|2|0/256|
|ordinary|128|8|split_proof|14/16|0|2|0/256|
|ordinary|128|8|split_unchecked|16/16|0|0|3/256|
|ordinary|128|32|single|48/64|1|15|37/256|
|ordinary|128|32|split|48/64|1|15|37/256|
|ordinary|128|32|proof|30/64|1|33|11/256|
|ordinary|128|32|split_proof|30/64|1|33|11/256|
|ordinary|128|32|split_unchecked|42/64|2|20|62/256|
|ordinary|128|128|single|106/256|61|89|142/256|
|ordinary|128|128|split|106/256|61|89|142/256|
|ordinary|128|128|proof|58/256|21|177|46/256|
|ordinary|128|128|split_proof|58/256|21|177|46/256|
|ordinary|128|128|split_unchecked|96/256|75|85|158/256|
|ordinary|128|256|single|149/512|195|168|169/256|
|ordinary|128|256|split|149/512|195|168|169/256|
|ordinary|128|256|proof|79/512|80|353|83/256|
|ordinary|128|256|split_proof|79/512|80|353|83/256|
|ordinary|128|256|split_unchecked|142/512|230|140|198/256|
|ordinary|512|8|single|16/16|0|0|0/256|
|ordinary|512|8|split|16/16|0|0|0/256|
|ordinary|512|8|proof|16/16|0|0|0/256|
|ordinary|512|8|split_proof|16/16|0|0|0/256|
|ordinary|512|8|split_unchecked|16/16|0|0|0/256|
|ordinary|512|32|single|63/64|0|1|1/256|
|ordinary|512|32|split|63/64|0|1|1/256|
|ordinary|512|32|proof|56/64|0|8|0/256|
|ordinary|512|32|split_proof|55/64|0|9|0/256|
|ordinary|512|32|split_unchecked|63/64|0|1|3/256|
|ordinary|512|128|single|199/256|3|54|42/256|
|ordinary|512|128|split|184/256|4|68|42/256|
|ordinary|512|128|proof|135/256|1|120|16/256|
|ordinary|512|128|split_proof|111/256|2|143|7/256|
|ordinary|512|128|split_unchecked|147/256|5|104|59/256|
|ordinary|512|256|single|297/512|46|169|95/256|
|ordinary|512|256|split|274/512|47|191|90/256|
|ordinary|512|256|proof|182/512|22|308|31/256|
|ordinary|512|256|split_proof|145/512|24|343|26/256|
|ordinary|512|256|split_unchecked|232/512|74|206|116/256|
|ordinary|2048|8|single|16/16|0|0|0/256|
|ordinary|2048|8|split|16/16|0|0|0/256|
|ordinary|2048|8|proof|16/16|0|0|0/256|
|ordinary|2048|8|split_proof|16/16|0|0|0/256|
|ordinary|2048|8|split_unchecked|16/16|0|0|0/256|
|ordinary|2048|32|single|64/64|0|0|0/256|
|ordinary|2048|32|split|64/64|0|0|0/256|
|ordinary|2048|32|proof|62/64|0|2|0/256|
|ordinary|2048|32|split_proof|62/64|0|2|0/256|
|ordinary|2048|32|split_unchecked|64/64|0|0|0/256|
|ordinary|2048|128|single|246/256|0|10|0/256|
|ordinary|2048|128|split|250/256|0|6|0/256|
|ordinary|2048|128|proof|213/256|0|43|0/256|
|ordinary|2048|128|split_proof|207/256|0|49|0/256|
|ordinary|2048|128|split_unchecked|241/256|0|15|0/256|
|ordinary|2048|256|single|452/512|1|59|12/256|
|ordinary|2048|256|split|436/512|0|76|8/256|
|ordinary|2048|256|proof|344/512|0|168|3/256|
|ordinary|2048|256|split_proof|336/512|0|176|0/256|
|ordinary|2048|256|split_unchecked|421/512|1|90|17/256|
|ordinary|8192|8|single|16/16|0|0|0/256|
|ordinary|8192|8|split|16/16|0|0|0/256|
|ordinary|8192|8|proof|16/16|0|0|0/256|
|ordinary|8192|8|split_proof|16/16|0|0|0/256|
|ordinary|8192|8|split_unchecked|16/16|0|0|0/256|
|ordinary|8192|32|single|64/64|0|0|0/256|
|ordinary|8192|32|split|64/64|0|0|0/256|
|ordinary|8192|32|proof|64/64|0|0|0/256|
|ordinary|8192|32|split_proof|64/64|0|0|0/256|
|ordinary|8192|32|split_unchecked|64/64|0|0|0/256|
|ordinary|8192|128|single|256/256|0|0|0/256|
|ordinary|8192|128|split|256/256|0|0|0/256|
|ordinary|8192|128|proof|249/256|0|7|0/256|
|ordinary|8192|128|split_proof|252/256|0|4|0/256|
|ordinary|8192|128|split_unchecked|256/256|0|0|0/256|
|ordinary|8192|256|single|511/512|0|1|0/256|
|ordinary|8192|256|split|511/512|0|1|0/256|
|ordinary|8192|256|proof|461/512|0|51|0/256|
|ordinary|8192|256|split_proof|476/512|0|36|0/256|
|ordinary|8192|256|split_unchecked|506/512|0|6|0/256|

## 判定と限界

固定判定：351/351。開発実行には合否判定を付けない。

確認信号は誤受理を抑えるが、値記憶の次元を消費し、正答を保留に変える場合がある。分割単独の改善、全負荷での容量改善、誤受理ゼロは保証しない。意図的に同じバンクへ衝突させたケースも省略しない。

同一予算は記憶ブロック・付随メタデータ予約領域・固定推論キャッシュ・それらのPythonオブジェクトに限定する。意味コーデック、Model側統計、インタプリタ、照会中の一時割当は含めない。TELEMETRY.jsonに時間とtracemallocの一時割当を別記し、結果ハッシュから除く。通常辞書は同じ照会を解く参考実装だが、予算を揃えていない。

言語試験は既存の限定一事象・五スロット文法。記憶試験のN増加は言語知識の拡張ではない。ID3型の依存特徴選択、文字列処理、ルーティング、制御は通常Python。明示チップ列の拡散・逆拡散や同期との接続は未実装。
