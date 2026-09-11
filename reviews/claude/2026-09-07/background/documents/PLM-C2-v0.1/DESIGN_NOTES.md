# PLM-C2 v0.1 Design Notes

## Objective

C1 v0.3の未見6失敗群を開発診断とし、表層cueだけでなく、主張を構成する対象・event・relationを検査可能なgraphへ分離します。C1 v0.3は変更せず凍結比較対象とします。

## Typed Claim Graph

Graph nodeは `SOURCE`, `CLAUSE`, `EVENT`, `ENTITY`, `CONCEPT`, `EVIDENCE`, `RELATION` の7種類です。主要edgeは次の意味を持ちます。

| Edge | Meaning |
|---|---|
| `CONTAINS` | sourceがclauseを含む |
| `DESCRIBES` | clauseがeventを記述する |
| `YIELDS` | clauseがEvidenceまたはRelationを生成する |
| `ABOUT` | Evidence/Event/Relationの対象Entity |
| `SUPPORTS` / `CONTRADICTS` | EvidenceからConceptへの三値寄与 |
| `GROUNDS` / `DOES_NOT_GROUND` | RelationがConcept解釈を成立／不成立にする |
| `SAME_TARGET_SEQUENCE` / `NEXT_DISTINCT_TARGET` | event間の対象連続性 |
| `SUPERSEDES` | 新Evidenceが旧Evidenceを置換する |

各実行でnode ID重複とedge endpointを検証します。

## Sentence and event relations

ピリオドをboundaryへ追加しつつ、数字に挟まれた小数点は分割しません。時間継起表現を `TARGET_SHIFT` とevent linkへ変換します。改訂表現はprovisional/corrective roleへ変換し、同一target上のEvidenceを `SUPERSEDE` します。

これは完全な構文解析ではありません。略語・colon・談話副詞の全体系は扱いません。

## Morphology and compounds

C1の制御付きinflectionに不規則対応 `bitten → bite` を加えました。閉じた複合語はallowlistで `riverbank(s)` のみ追加します。任意の部分文字列照合は禁止したままなので、`bitter` をBITEとして扱いません。

## Typed relation gate

曖昧語 `bank` と独立した `river` が同一clauseに存在しても、空間Relationが成立しなければriver由来のRIVER_BANK直接Evidenceを無効化します。無効化は削除せず `relation_gated` 状態と `RELATION_GATE` 操作で履歴に残します。

## Evaluation protocol

1. 固定回帰とC1 v0.1/v0.2/v0.3 challengesを事前固定セットとして使用
2. C1 v0.3 challengeをC2開発診断に使用
3. C2/C1 v0.3/v0.2/v0.1/C0を同じcaseで比較
4. semantic `template_group` 単位でcluster bootstrap
5. C2完成後に新規20 seed×3 wrapperを固定
6. challenge SHA-256: `fd87b7663e9912b4898c8023f65c54955d826fdf8782631adb12d490ec6c1c85`
7. 新規challenge初回実行後はengine/Concept-dataを変更しない

## Limits

未見Top-1は `0.8000`、ECEは `0.2582` です。失敗は `revision_colon`, `correction_rather`, `relation_sponsored_cleanup`, `coreference_latter` の4意味groupです。次段階ではdelimiter列挙ではなく構文的なcontrast/revision edge、指示表現からEntityへのcoreference edge、限定的な行為者affordanceが必要です。
