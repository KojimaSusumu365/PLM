# PLM-C2 v0.3 Design Notes

## 目的

C2のEvidence・Event・Reference・Revision・Affordanceを、R1で消費できる一つのRelation契約へ正規化する。同時に、v0.2で残った`reclassified`を含む改訂役割と、限定的な代名詞・日本語談話表現を扱う。

## バージョン境界

`plm_c2_v02`と`plm_c2_v01`は凍結比較実装である。現行`plm_c2.PLMC2Engine`はv0.2を継承し、v0.3固有機構だけを追加する。旧Concept dataと旧challengeは変更しない。

## Relation Frame契約

すべてのframeは次の必須fieldを持つ。

```text
frame_id, clause_id, relation_type, subject, predicate, object_text,
voice, polarity, modality, applied
```

任意fieldとして`target_concept`、`target_clause_id`、`source_relation_id`、`source_reference_id`を持つ。JSON Schemaは`RELATION_SCHEMA.json`に固定した。

対応relation typeは`COREFERENCE`、`REVISION`、`FINANCIAL_AFFORDANCE`、`SPATIAL_ASSOCIATION`である。元のEvidence/Relation/Referenceを置換せず、frameから`FRAME_OF`でprovenanceを保持する。

## Claim Graph schema v2

`RELATION_FRAME` nodeを導入し、生成節へ`YIELDS`、元Relation/Referenceへ`FRAME_OF`、Conceptへ`MAPS_TO`、改訂対象節へ`SUPERSEDES_CLAUSE`を張る。node ID一意性、全edge endpoint、frame ID一意性、必須fieldを毎回検証する。

## 改訂役割

単語完全一致ではなく、`reclassif-*`、`relab-*`、`redesignat-*`、`recategoriz-*`の形態familyと、label/classification変更構文を認識する。日本語では再分類・再指定・分類変更・名称変更を扱う。`reidentified`は未見失敗として意図的に保持した。

## 照応

順序表現に加え、earlier/later/previous oneと前者/後者を扱う。`it`/`それ`は最寄り先行節のentity言及が1件の場合だけ解決し、2件以上なら棄却する。`they`/`それら`は複数候補すべてへ同重量で接続し、共通上位Conceptを維持する。訂正節に明示entityがある場合は代名詞Evidenceを追加せず、旧ラベルの再流入を防ぐ。

## 役割ベースaffordance

bankが能動主語で制度的配分・支援predicateを持つ場合に金融機関Conceptを支持する。否定・仮定・受動態ではframeを残すが`applied=false`とする。受動態の`by river ...`を空間関係と誤認しないconsistency gateも適用する。

## 日本語訂正scope

`犬、いや、猫`のように訂正markerが独立節になる場合、corrective状態を直後の同一source節へ伝播する。全角colonもrevision boundaryとして認識する。

## Confidence calibration

v0.2未見評価の95% CI下限0.85を保守priorとして、v0.2のcalibrated confidence `p`を次式で再縮約する。

```text
p_relation = clip(0.86 + 0.20 * (p - 0.82), 0.78, 0.94)
```

元のraw値とv0.2値を両方保持する。これは学習済み確率ではなく、機能benchmark上のheuristicである。

## 評価プロトコル

開発診断は10意味seed×3 wrapper、未見challengeはengine凍結後に作成した24意味seed×3 wrapperである。初回未見結果はTop-1 0.9583、MRR 0.9688、ECE 0.0998で、その後engineとConcept dataを変更していない。

bootstrapは`template_group`単位で行う。Relation Frameは精度寄与ではなく構造契約としてablationし、それ以外の4機能は開発診断上で個別の精度低下を確認する。
