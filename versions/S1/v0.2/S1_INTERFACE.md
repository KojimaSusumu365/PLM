# S1 v0.2 受信契約

新wire形式は `PLM-S1-chip-observation-packet-v2`、producerは `PLM-S1 v0.2`。旧S1 v0.1のwireや歴史的な結果を変更しません。旧packetは新CLIで拒否し、旧受信器はvendor側に保存します。

入力の正規検証器は `plm_s1_v02.packet.from_packet`。WIRE_CONTRACT.jsonは契約の説明であり、JSON Schemaの実装ではありません。余分なフィールド、非有限値、長さ不一致、bool以外のマスク、隠し領域の非ゼロ値、不一致コードブック・link・境界を拒否します。

Sessionはコードブックとlinkの別途固定を必須にします。

```python
session = Session(packet, public_catalogue,
                  expected_book=pinned_book, expected_link=pinned_link)
result = session.query({"document_id": doc, "event_id": event,
                        "role": role, "candidates": candidates})
```

受信チップと観測マスクから1回同期・逆拡散し、旧P1 v0.2 Receiverへ値とマスクを渡します。照会で正解・遅延・CFO・位相を指定することはできず、同期失敗時も不正照会は拒否します。

公開候補カタログは可能なアドレスや状態の集合であり、実際のslot割当てではありません。source_digestは元frameの監査値で、正解検索に使いません。正規化のgainは旧版同様の公開スカラーです。

同期診断のstatus=alignedは、定めたパイロット検査に合格した推定を意味するだけです。真値・認証・意味の保証ではありません。周波数候補差、遅延候補差、ブロックごとの補正整合性も返しますが、確率として扱いません。

- `eligible_for_inference: false`、`inference_enabled: false` を維持。
- `ss_demodulation_implemented: true` の範囲は `synthetic_discrete_complex_baseband_only`。
- 非拡散対照では `spreading_applied: false`。
- 独立意味評価は `not_performed`。

否定・仮定・隔離・訂正対象・同Concept別個体を肯定事実へ変換しません。前後2ブロック配置は比較用として同じv2契約内に明示し、通常の配置はdistributed4です。SHA256は整合性だけで、悪意ある送信者・パイロットの認証を実装していません。
