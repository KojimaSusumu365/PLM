# PLM-C1 v0.1 Design Notes

## Objective

PLM-C0 v0.3で観測した訂正、長距離否定、文脈漏れを、語彙追加ではなくEvidenceの構造化と明示演算で扱います。

## Evidence ledger

Evidenceを次のタプルとして扱います。

\[
E=(concept,vote,weight,source,clause,scope,status,order)
\]

`active=false` のEvidenceは履歴として保持しますが、Consensusには加算しません。`effective_weight` が現在の寄与です。

## Explicit operations

### NEGATE

節内で否定スコープに入るEvidenceを負票にします。C0の固定文字窓より広く、同じ節内の否定辞から対象までを追跡します。英語のadversative以降はスコープをリセットし、日本語の名詞・述語後続否定も扱います。

### SUPERSEDE

訂正節に新しいConcept証拠がある場合、同じdomainの過去の異なる正票を無効化します。

\[
w_{effective}(E_{old}) \leftarrow 0
\]

元の証拠は削除せず、`superseded_by` で置換先を参照します。`no_residual` ablationでは訂正を検出しても重みを残します。

### ISOLATE

文脈ruleは曖昧語を含む同じ節にだけ適用します。別節や別入力にcontext triggerが存在しても、曖昧語の候補へ無条件に加算しません。

`Separately` / `Later` 等で別インスタンスが示され、同じdomainの複数scopeが競合する場合は `ISOLATE_CONFLICT` として `UNRESOLVED` にします。

## Context polarity

川・水辺contextは否定下で無効にします。一方、金融affordanceは「loanを提供しない」のような否定文でもbank senseを識別するため、Concept存在の負票にはせず型情報として使います。この差は `concepts_c1.json` の `negation_sensitive` で表します。

## Evaluation protocol

1. v0.3の288件を変更せず回帰セットとして使用
2. test 216件でC1/C0/lexical baselineを比較
3. `no_scope`, `no_correction`, `no_residual`, `no_negation` を評価
4. 72意味group単位でcluster bootstrap
5. 実装後に20個の新規challengeを固定し、初回実行後はモデルを調整しない

## Results and limits

C1は既知回帰testを全件解決し、操作ablationでも寄与が確認できました。しかし未調整challenge Top-1は `0.2000` に留まり、C0との差の95%区間も `[-0.1000, 0.3000]` でゼロを含みます。

これは現在のC1が「構造を持つが、scope/correction detectorは辞書的」という状態を示します。次段階ではマーカー列挙ではなく、有限状態の談話遷移、形態正規化、極性合成、対象インスタンス追跡が必要です。
