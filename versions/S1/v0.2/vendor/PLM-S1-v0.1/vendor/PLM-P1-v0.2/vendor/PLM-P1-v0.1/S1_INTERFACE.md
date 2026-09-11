# PLM-P1 → PLM-S1 接続契約 v1

## 今回の接続点

P1が提供するのは複素ベースバンド相当の数値配列です。配列の座標は高次元コードの成分で、物理時刻やチップ列そのものではありません。この配列を受け取る検証器と参照復号器を実装しました。S1のSS型変復調器を実装したという意味ではありません。

wire形式は `PLM-P1-S1-observation-packet-v1`。実行時検証は `plm_p1/packet.py`、構造の説明用Schemaは `S1_PACKET_SCHEMA.json` です。クロスフィールド長・ハッシュ・マスク整合性はSchemaだけでなく実行時検証が必須です。

| 項目 | 契約 |
|---|---|
| codebook | algorithm, dimension, seed, symbol_serialization, phase_units |
| codebook_fingerprint | 上記仕様のcanonical JSON SHA256。受信側が別途固定した値とも照合する |
| codec | event-role-hadamard-sum-v1 |
| samples.real / samples.imag | D個ずつの有限数値。Float64相当。単位化しない |
| observed_mask | D個のboolean。falseの位置の値は0にする |
| source_refs | 文書ID、出来事ID、原記録hashのみ。正解slotsやmetadataは禁止 |
| normalization | unnormalized_sum_unit_phasor_bindings |
| phase_reference | aligned_baseband_required_not_estimated（必要条件の宣言。同期済みとの実測保証ではない） |
| time_axis / chip_rate_hz | 今回はnull。物理的仕様を仮定しない |
| payload_hash | 自分自身を除く全payloadのcanonical JSON SHA256 |
| boundary | observe_only、inference_enabled=false、ss_demodulation_implemented=false |

SHA256は破損・不一致の検査であり、署名や送信者認証ではありません。攻撃者が内容とhashを一緒に変えることは防げないので、受信側のcodebook仕様と配布元の整合性を別に固定します。

## 復号要求

要求JSONはdocument_id/event_id/role/candidatesの4項目だけです。候補は `{kind,scope,id}` の配列。原文、expected、gold、slotsを要求へ混ぜるとCLIは拒否します。候補辞書や照会キーを外部から与える設計であり、未知キー・未知語彙の自己発見は今回の範囲外です。

応答はstatus=recovered/abstain、selected、観測成分数、上位候補と相関値、margin、reason、eligible_for_inference=false。応答に信頼確率を付けません。シリアライズ復元はビット/数値の往復検査であり、物理的な復調試験ではありません。

マスクfalse成分は原信号が分かっていても0として送信します。検証用の原フレームは別ファイルに置き、復号器はそのファイルや出典hashから役割対応を取得しません。

## S1 v0.1で実装すべき内容（今回は未実装）

1. P1コード座標とチップ時間の対応、および複素コードをどのSS方式で送るかを決定する。PN系列やチップレートを追加する場合は新wire版とする。
2. 符号化→拡散→重畳→チャネル→同期→逆拡散→P1照合の一往復を、人工正解で検証する。
3. 位相基準/パイロット、時間ずれ、周波数ずれ、位相ドリフトの推定を実装する。受信器に注入した真のずれ値を渡して正解としない。
4. 誤検出率、見逃し率、役割/個体の回復率、同期成功率、負荷・欠測・雑音ごとの失敗を測る。
5. 元の否定・仮定・隔離・根拠リンクを取り違えない。数値回復が成功しても観察の事実採用は別の承認境界に残す。

## S1の比較条件

同じ入力・候補辞書で、P1の整列済み信号を直接復号した数値上限側の比較、S1チャネル経由、同期を無効にした比較、位相/遅延の真値を与えるoracle比較（参考値のみ）を区別します。入力エネルギー、候補数、重畳数、SNR、系列長を記録します。

成功判定の数値閾値はS1の開発データで定め、別seedの評価前に凍結します。パイロット長、最大遅延、最大周波数ずれ等の物理値は今回のコード次元から勝手に決めません。

P1の基準ケースに合格しただけでS1の実現可能性が全面的に証明されたわけではありません。ただし、S1が何を入力として受け取り、どの情報を失わず返すべきかを、実行可能な数値契約にしました。
