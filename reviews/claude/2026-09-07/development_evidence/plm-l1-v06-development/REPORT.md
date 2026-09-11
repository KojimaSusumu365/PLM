# PLM-L1 v0.6 評価結果

固定予算の記憶サブシステム比較。未登録照会の拒否率と、登録照会の正答・誤答・保留を分けて評価する。

## 言語試験

|方式|未学習組合せ・読解|未学習組合せ・生成|両側未学習・往復|全往復|
|---|---:|---:|---:|---:|
|single|192/192|192/192|192/192|1536/1536|
|split_proof|192/192|192/192|192/192|1536/1536|
|split_unchecked|192/192|192/192|192/192|1536/1536|

## 独立記憶試験・通常のキー分布（全負荷合算）

|方式|登録照会数|正答|誤答|保留|未登録照会の誤受理|
|---|---:|---:|---:|---:|---:|
|single|1696|1230|153|313|209/2048|
|split|1696|1225|169|302|208/2048|
|proof|1696|925|69|702|77/2048|
|split_proof|1696|948|69|679|76/2048|
|split_unchecked|1696|1164|217|315|291/2048|

未登録誤受理の合算減少率：63.6%。登録正答の維持率：77.1%（single比）。

これは異なる負荷条件を等しい試行構成で合算した値であり、運用時のエラー確率や統計的有意性ではない。負荷ごとの数値を以下に残す。

|分布|D|N|方式|正答|誤答|保留|未登録誤受理|
|---|---:|---:|---|---:|---:|---:|---:|
|forced_single_bank|2048|128|single|125/128|0|3|0/128|
|forced_single_bank|2048|128|split|78/128|10|40|7/128|
|forced_single_bank|2048|128|proof|99/128|0|29|0/128|
|forced_single_bank|2048|128|split_proof|40/128|5|83|7/128|
|forced_single_bank|2048|128|split_unchecked|63/128|20|45|13/128|
|ordinary|128|8|single|8/8|0|0|0/128|
|ordinary|128|8|split|8/8|0|0|0/128|
|ordinary|128|8|proof|7/8|0|1|0/128|
|ordinary|128|8|split_proof|7/8|0|1|0/128|
|ordinary|128|8|split_unchecked|8/8|0|0|0/128|
|ordinary|128|32|single|24/32|0|8|15/128|
|ordinary|128|32|split|24/32|0|8|15/128|
|ordinary|128|32|proof|13/32|0|19|5/128|
|ordinary|128|32|split_proof|13/32|0|19|5/128|
|ordinary|128|32|split_unchecked|22/32|1|9|38/128|
|ordinary|128|128|single|53/128|31|44|57/128|
|ordinary|128|128|split|53/128|31|44|57/128|
|ordinary|128|128|proof|24/128|9|95|23/128|
|ordinary|128|128|split_proof|24/128|9|95|23/128|
|ordinary|128|128|split_unchecked|43/128|38|47|73/128|
|ordinary|128|256|single|66/256|101|89|73/128|
|ordinary|128|256|split|66/256|101|89|73/128|
|ordinary|128|256|proof|33/256|49|174|26/128|
|ordinary|128|256|split_proof|33/256|49|174|26/128|
|ordinary|128|256|split_unchecked|64/256|125|67|86/128|
|ordinary|512|8|single|8/8|0|0|0/128|
|ordinary|512|8|split|8/8|0|0|0/128|
|ordinary|512|8|proof|8/8|0|0|0/128|
|ordinary|512|8|split_proof|8/8|0|0|0/128|
|ordinary|512|8|split_unchecked|8/8|0|0|0/128|
|ordinary|512|32|single|32/32|0|0|0/128|
|ordinary|512|32|split|30/32|0|2|0/128|
|ordinary|512|32|proof|23/32|0|9|0/128|
|ordinary|512|32|split_proof|24/32|0|8|0/128|
|ordinary|512|32|split_unchecked|31/32|0|1|2/128|
|ordinary|512|128|single|95/128|1|32|18/128|
|ordinary|512|128|split|86/128|3|39|18/128|
|ordinary|512|128|proof|62/128|2|64|7/128|
|ordinary|512|128|split_proof|61/128|1|66|4/128|
|ordinary|512|128|split_unchecked|81/128|3|44|28/128|
|ordinary|512|256|single|138/256|20|98|43/128|
|ordinary|512|256|split|127/256|34|95|41/128|
|ordinary|512|256|proof|66/256|9|181|15/128|
|ordinary|512|256|split_proof|70/256|10|176|16/128|
|ordinary|512|256|split_unchecked|109/256|50|97|54/128|
|ordinary|2048|8|single|8/8|0|0|0/128|
|ordinary|2048|8|split|8/8|0|0|0/128|
|ordinary|2048|8|proof|8/8|0|0|0/128|
|ordinary|2048|8|split_proof|8/8|0|0|0/128|
|ordinary|2048|8|split_unchecked|8/8|0|0|0/128|
|ordinary|2048|32|single|32/32|0|0|0/128|
|ordinary|2048|32|split|32/32|0|0|0/128|
|ordinary|2048|32|proof|31/32|0|1|0/128|
|ordinary|2048|32|split_proof|32/32|0|0|0/128|
|ordinary|2048|32|split_unchecked|32/32|0|0|0/128|
|ordinary|2048|128|single|118/128|0|10|0/128|
|ordinary|2048|128|split|126/128|0|2|0/128|
|ordinary|2048|128|proof|106/128|0|22|0/128|
|ordinary|2048|128|split_proof|106/128|0|22|0/128|
|ordinary|2048|128|split_unchecked|122/128|0|6|0/128|
|ordinary|2048|256|single|224/256|0|32|3/128|
|ordinary|2048|256|split|234/256|0|22|4/128|
|ordinary|2048|256|proof|141/256|0|115|1/128|
|ordinary|2048|256|split_proof|160/256|0|96|2/128|
|ordinary|2048|256|split_unchecked|215/256|0|41|10/128|
|ordinary|8192|8|single|8/8|0|0|0/128|
|ordinary|8192|8|split|8/8|0|0|0/128|
|ordinary|8192|8|proof|8/8|0|0|0/128|
|ordinary|8192|8|split_proof|8/8|0|0|0/128|
|ordinary|8192|8|split_unchecked|8/8|0|0|0/128|
|ordinary|8192|32|single|32/32|0|0|0/128|
|ordinary|8192|32|split|32/32|0|0|0/128|
|ordinary|8192|32|proof|32/32|0|0|0/128|
|ordinary|8192|32|split_proof|32/32|0|0|0/128|
|ordinary|8192|32|split_unchecked|32/32|0|0|0/128|
|ordinary|8192|128|single|128/128|0|0|0/128|
|ordinary|8192|128|split|128/128|0|0|0/128|
|ordinary|8192|128|proof|128/128|0|0|0/128|
|ordinary|8192|128|split_proof|125/128|0|3|0/128|
|ordinary|8192|128|split_unchecked|128/128|0|0|0/128|
|ordinary|8192|256|single|256/256|0|0|0/128|
|ordinary|8192|256|split|255/256|0|1|0/128|
|ordinary|8192|256|proof|235/256|0|21|0/128|
|ordinary|8192|256|split_proof|237/256|0|19|0/128|
|ordinary|8192|256|split_unchecked|253/256|0|3|0/128|

## 判定と限界

固定判定：0/0。開発実行には合否判定を付けない。

確認信号は誤受理を抑えるが、値記憶の次元を消費し、正答を保留に変える場合がある。分割単独の改善、全負荷での容量改善、誤受理ゼロは保証しない。意図的に同じバンクへ衝突させたケースも省略しない。

同一予算は記憶ブロック・付随メタデータ予約領域・固定推論キャッシュ・それらのPythonオブジェクトに限定する。意味コーデック、Model側統計、インタプリタ、照会中の一時割当は含めない。TELEMETRY.jsonに時間とtracemallocの一時割当を別記し、結果ハッシュから除く。通常辞書は同じ照会を解く参考実装だが、予算を揃えていない。

言語試験は既存の限定一事象・五スロット文法。記憶試験のN増加は言語知識の拡張ではない。ID3型の依存特徴選択、文字列処理、ルーティング、制御は通常Python。明示チップ列の拡散・逆拡散や同期との接続は未実装。
