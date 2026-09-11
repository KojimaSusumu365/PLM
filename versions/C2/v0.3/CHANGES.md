# PLM-C2 v0.3 Changes

- C2 v0.2を`plm_c2_v02`として凍結同梱
- 共通`RelationFrame` dataclassとRelation契約を追加
- Claim Graph schema v2と`RELATION_FRAME` nodeを追加
- `FRAME_OF`、`MAPS_TO`、`SUPERSEDES_CLAUSE` edgeを追加
- Relation Frame JSON Schemaを追加
- 改訂predicateを形態family単位へ一般化
- bounded pronounおよび日英nominal referenceを追加
- 明示entityを持つ訂正節での代名詞再流入guardを追加
- 制度的role affordance predicate群を追加
- 否定・仮定・受動態のrelation consistency gateを追加
- 日本語訂正scope伝播と全角colon revisionを追加
- relation-aware confidence calibrationを追加
- 30件の開発診断と72件の凍結後未見challengeを追加
- 全比較、ablation、Relation/Graph auditを評価suiteへ追加
- v0.3テスト32件を追加し、全146テストへ拡張
