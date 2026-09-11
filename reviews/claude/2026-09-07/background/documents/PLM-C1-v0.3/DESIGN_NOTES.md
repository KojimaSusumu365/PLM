# PLM-C1 v0.3 Design Notes

## Objective

v0.2 post-implementation challengeの7失敗群を開発診断として用い、語彙項目の場当たり的追加ではなく、形態・談話役割・event identity・複合語・open-set確信度の機構を追加します。v0.3完成後は別のchallengeで汎化を測定します。

## Controlled lemma normalization

英語patternを名詞系と動詞系に分け、名詞は複数形、動詞は三単現・過去形・進行形のみ展開します。子音+yは `y/ies` を合成します。`car` を動詞活用させないため、`cared` を `car` と誤認しません。変換は `NormalizationEvent` と `NORMALIZE_MORPHOLOGY` で監査できます。

完全なlemmatizerではないため、`bitten` のような不規則分詞は対象外です。

## Revision roles

談話状態へ `retracted` を追加しました。provisional/corrective/retractionを表層表現から役割へ写像し、次の操作を分離します。

- `SUPERSEDE`: 新しい競合判断による置換
- `RETRACT`: 明示的に撤回されたEvidenceの残差を0へ変更
- `STATE_TRANSITION`: clauseの談話役割を記録

## Event identity

対象切替cueをsource全体ではなくclause単位で解釈し、切替後の節へ新しいinstance scopeを割り当てます。`TARGET_SHIFT` と `target_id` で境界を追跡し、複数instanceを一つのConceptに混合しません。

## Approved compounds

ASCII境界保護を維持しつつ、許可されたhead/suffixだけを複合語として解析します。v0.3では `riverbed`, `riverside`, `riverfront`, `rivermouth` のみです。任意の部分文字列一致へ戻さないための保守的設計です。

## Open-set confidence

対象domainに正負いずれのEvidenceも存在しない場合、`UNRESOLVED`を返しながら `selection_confidence=0.35` とします。否定Evidenceによる棄却と、単に語彙外である状態を区別します。新規未見challengeのconfidence ablationでECE `0.1288` 対 `0.2203` を確認しました。

## Evaluation protocol

1. v0.3回帰、v0.1 challenge、v0.2 challengeを事前固定セットとして使用
2. v0.2 challengeの失敗群をv0.3開発診断に使用
3. v0.3/v0.2/v0.1/C0を同一caseで比較
4. semantic `template_group` 単位でcluster bootstrap
5. engine完成後に新規20 seed×3 wrapperを固定
6. challenge SHA-256: `90a8f9d28b5e2abd86a66b9c60d309992c6c30c123586afcdf51751453e544a8`
7. 新規challenge初回実行後はengine/Concept-dataを変更しない

## Limits

未見Top-1は `0.7000` です。失敗は `target_separate_case_inline`, `target_subsequently`, `revision_originally_revised`, `morph_bitten`, `compound_riverbank_closed`, `relation_river_statistics` の6意味groupです。特にピリオドがclause boundaryに含まれない点と、独立した語 `river` が非空間文脈でも直接RIVER_BANK Evidenceになる点は、次版で表層cue追加ではなく構文・関係型として直す必要があります。
