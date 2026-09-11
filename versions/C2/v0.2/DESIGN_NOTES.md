# PLM-C2 v0.2 Design Notes

## 目的

v0.1で未解決だったcolon内の改訂、`rather`訂正、スポンサー行為、`latter`照応を、Evidence ledgerとClaim Graphの追跡可能性を保ったまま解決する。

## バージョン境界

`plm_c2_v01`はv0.1の完全な凍結コピーである。`plm_c2.PLMC2Engine`はこれを継承し、v0.2固有処理だけを追加する。旧データ、旧engine、旧評価期待値は変更しない。

## 順序付き照応

直前から逆向きに、同一節内に2件以上のentity直接言及を持つ最寄り節を探す。`former`/`first`は先頭、`latter`は末尾、`second`は2番目へ解決する。解決結果は追加Evidence、`RESOLVE_REFERENCE` operation、`ReferenceLink`として記録する。

Claim Graphには`REFERENCE` nodeを追加し、参照節から`YIELDS`、Conceptへ`RESOLVES_TO`、先行節へ`REFERS_BACK_TO`を張る。追加後に全edge endpointを再検査する。

## 訂正と改訂の境界

独立した`rather`/`instead`の直前でzero-width分割し、後続節を`corrective`とする。比較構文`rather than`と`instead of`は対象外である。

colonは無条件には分割しない。後続が`revised`、`amended`、`updated`、`corrected`等の明示的改訂markerの場合だけ境界にする。これにより`Record:`等のwrapperを保持する。

## Agentive affordance

曖昧語`bank`が能動主語であり、閉じた能力動詞集合`sponsor`、`fund`、`finance`、`underwrite`、`lend`を48文字以内に持つ場合、`FINANCIAL_AFFORDANCE` relationを生成する。肯定・非仮定の場合に金融Conceptを支持し、川岸Conceptを反証する。

否定と仮定ではrelationを記録するが適用しない。典型的な受動態では能力推論を行わず、`by river ...`を空間関係と誤認しない。

## Confidence calibration

v0.1の凍結未見正解率0.80を経験的priorとし、raw confidence `p`を次式で縮約する。

```text
p_cal = clip(0.82 + 0.25 * (p - 0.82), 0.70, 0.93)
```

raw値は`raw_selection_confidence`に残す。これは学習済み確率ではなく、小規模機能benchmark上の保守的heuristicである。

## 評価プロトコル

旧5評価セットを開発・回帰用に固定した。v0.2 engineとConcept dataのSHA-256を記録後、新規20意味テンプレートを作成し3 wrapperへ展開した。初回未見評価はTop-1 0.95、MRR 0.9625、ECE 0.1497であり、その後engineとConcept dataは変更していない。

bootstrapはwrapperを独立標本と扱わず、`template_group`単位で行う。4精度機能はC2 v0.1 challenge上のablationで各0.05の低下を示し、校正機能を外すとECEが0.1964から0.2466へ悪化する。
