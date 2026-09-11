# S1受信契約と境界

## 入出力

新しいwire形式は `PLM-S1-chip-observation-packet-v1`。P1 v0.1/v0.2のパケット形式を意味変更して流用しません。SS復調実装済みのフラグはS1の新しい契約に限定し、同梱する旧P1の歴史的なフラグは書き換えません。

パケットは受信チップの実部/虚部、厳密なbool観測マスク、コードブック、公開link設定、正規化、時間軸、元入力の監査digest、観察専用boundary、payload_hashだけを含みます。正解slot、原frame、真の遅延・位相・周波数・チャネルseedを含めません。

受信側ではコードブックとlinkを別途固定します。公開linkはモード、次元、拡散長、パイロット長、ガード長、チップレート、遅延探索範囲、小CFOの事前範囲、拡散符号seedです。これは実際のチャネル真値ではありません。

`plm_s1.packet.from_packet` が厳格な入力検証の正規実装です。`WIRE_CONTRACT.json` は契約の説明であり、JSON Schema検証器の代替実装を意味しません。余分なフィールド、長さ不一致、非有限値、数値をboolの代わりに使ったマスク、隠し領域の非ゼロ値、コードブック不一致、推論フラグの変更を拒否します。

## 受信セッション

```python
session = Session(packet, public_catalogue,
                  expected_book=pinned_book, expected_link=pinned_link)
result = session.query({"document_id": doc, "event_id": event,
                        "role": role, "candidates": candidates})
```

Sessionはパイロット同期と逆拡散を1回行い、凍結したP1 v0.2 Receiverへ数値信号とマスクを渡します。照会は4フィールドに限定し、同期が失敗した場合でも不正な照会形式は拒否します。同期失敗時は候補回復を強制せず、保留します。

P1の公開候補カタログは別入力のままです。あり得る状態・述語やアドレスの集合で、実際のslot割当てや出来事の存在フラグではありません。SS側からそれを事実として扱う機能はありません。

## 境界フラグ

- `ss_demodulation_implemented: true` は本版の離散ベースバンド実装を示すだけです。
- `implementation_scope: synthetic_discrete_complex_baseband_only` を併記します。
- 比較の非拡散モードでは `spreading_applied: false` となります。
- `eligible_for_inference: false` と `inference_enabled: false` を維持します。
- 独立意味評価は `not_performed` のままです。

否定・仮定・隔離・訂正対象などの区別は元のP1信号内に保持します。数値復調の成功を肯定事実へ変換せず、R1/C2の観察や推論許可を書き換えません。

## 信頼と未実装範囲

SHA256はパケット整合性の確認であり、送信者の認証・悪意あるパイロットの検出ではありません。公開パイロットを偽装された場合や、事前範囲外CFOが折り返した場合に、同期を誤受理する可能性があります。これは本版の既知の限界です。

次の拡張候補は、周波数曖昧性を解くパイロット配置/粗同期、分数チップ遅延、サンプル時計ずれ、段階的なマルチパス評価です。追加する場合も、パイロット・ガード・再送・誤り訂正の費用を含む総予算を固定し、未知評価前に方式を凍結します。
