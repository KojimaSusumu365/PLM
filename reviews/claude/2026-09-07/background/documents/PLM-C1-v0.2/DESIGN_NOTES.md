# PLM-C1 v0.2 Design Notes

## Objective

v0.1の未調整challengeで露出した未知の訂正マーカー、二重否定、reported denial、形態変化、条件文、対象混同を、Evidence表現と明示演算の拡張で扱います。v0.1とC0 v0.3は凍結比較対象です。

## Evidence model

Evidenceを概念・票・重みに加えて、次の状態を持つledger itemとして保持します。

\[
E=(concept,vote,weight,source,clause,scope,target,polarityDepth,state,active)
\]

`target_id` は談話上の対象インスタンス、`polarity_depth` は対象Evidenceへ作用する否定演算子数です。履歴を削除せず、訂正されたEvidenceは `active=false`, `effective_weight=0` とします。

## Polarity composition

英語・日本語の否定cueを節内で数え、奇数なら負票、偶数なら正票とします。英語adversative後は前方scopeをリセットし、`not only` は否定として数えません。これは浅い決定規則であり、完全な統語解析ではありません。

## Discourse state machine

節を `asserted`, `provisional`, `corrective`, `hypothetical` に分類します。corrective節は同一domainの過去の競合Evidenceを `SUPERSEDE` し、hypothetical節の関係boostは適用しません。状態変化は `STATE_TRANSITION` として監査できます。

## Target tracking

`separately`, `later`, `afterward`, `その後`, `別に` などの切替cueから対象instanceを分離します。同一domainに複数targetの正Evidenceが残る場合、一つのConceptへ混合せず `ISOLATE_CONFLICT` で棄却します。

## Relation Evidence

曖昧語 `bank` とcontext triggerの関係を `RelationEvidence` として記録します。金融affordanceは接続を認め、川岸の解釈には `near`, `beside`, `along`, `そば`, `沿い` などの空間cueを要求します。仮定・否定された関係は記録しますが適用しません。

## Evaluation protocol

1. v0.3回帰288件とv0.1 challenge 60件を事前固定セットとして使用
2. v0.2、凍結v0.1、C0 v0.3を同じcaseで比較
3. 5つのv0.2機能とresidualのablationを既存challengeで評価
4. semantic `template_group` 単位でcluster bootstrap
5. engine完成後に新規20 seed×3 wrapperを固定
6. SHA-256 `34b396ab0916b617e31e0162dc44c4a2eed52ecc57556a29c328dc1cd8808d53`
7. 新規challenge初回実行後はengine/Concept-dataを変更しない

## Limits

未見challenge Top-1は `0.6500` です。辞書にない `formerly`, `ultimately`, `取り消し`, `別件`、不規則形 `puppies`、過去形 `barked`、複合語 `riverbed` を処理できません。現在の状態機械と対象追跡はcue-drivenで、構文・照応・イベント同一性の一般モデルではありません。
