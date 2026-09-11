# PLM-C2 v0.4 Changes

- C2 v0.3を`plm_c2_v03`に凍結。旧テストは各凍結版を検証する。
- 動詞の近接判定を限定構文の主体・対象・態・否定抽出へ変更。名詞supportを除外し、受動文のby-bankを行為者として扱う。
- 個体ID・言及ID・原文内spanを追加。同種個体を区別し、複数群を単数代名詞に結び付けない。
- 訂正フレームを実際のSUPERSEDE操作に接続。日本語の訂正マーカー自体を訂正先にしない。
- reidentifiedを既知改訂役割へ追加。
- Relation Frame schema v2 / Claim Graph schema v3。旧ENTITYノードはTARGET_SCOPEへ改名し、ENTITY_INSTANCE・MENTIONを導入。
- Schema実検証、原文span検証、個体リンク・訂正根拠検証、元データ変更後の再検証を追加。
- R1はobserve_onlyに限定。推論採用は常に無効。旧ready_for_r1_experimentは観察可否を示す互換名で、本番準備完了を意味しない。
- 専用30件で小標本平滑化つき単調校正。確信度の意味と未解決照応を明示。
- 開発23件・保留評価32件・変形対9件を追加。意味内容ごとに例を用意し、意味上の正解を別途注釈する。
- 実装・継承モジュール・評価・テスト・全データをまとめてハッシュ固定。初回holdout結果を保存し再現確認する。
- v0.4専用テスト40件を追加。

## v0.3からの履歴

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
