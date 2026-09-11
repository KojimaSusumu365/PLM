# 独立評価の注釈手順 v1

## 独立性と役割

実装者とは別の注釈者2名と、両者とは別の裁定者1名を用意します。同じ実装モデルが作った正解、C2予測から転記した正解、既存C0〜C2評価例の言い換えは独立評価と呼びません。注釈者は原文とこの手順だけを見て作業し、両者の注釈を保存した後で裁定します。予測台帳は裁定・正解凍結まで見せません。

IDやprocess_declarationは自己申告で、プログラムは本人性・実際の独立性を検証できません。署名付き作業記録や担当者の確認は実施責任者が別途管理します。全自動生成のテスト用注釈は必ずdataset_kind=syntheticとします。

## コーパス入力

`corpus.json` は次の形の配列です。下記は説明用プレースホルダーで、実例ではありません。

```json
[
  {
    "source_id": "実資料の管理ID",
    "revision": "資料版",
    "source_group": "同一元資料・テンプレート・転載群の管理ID",
    "stratum": "financial_active",
    "provenance": "取得元・取得日・利用権限・匿名化処理の記録",
    "inputs": ["改変せず保存した対象原文"]
  }
]
```

prepare-evaluationはC2を実行せず、空のannotationsとadjudicationを持つタスクを作ります。タスク本文と出典情報のmanifestを別ファイルに保存し、注釈の開始前に保管・凍結します。原文や層別区分を変える場合は黙ってmanifestを再生成せず、新しいバッチとして記録してください。

## 注釈するもの

対象は4種類: FINANCIAL_AFFORDANCE（銀行が行う金融的支援）、SPATIAL_ASSOCIATION（川岸等と周辺対象の明示的空間関係）、COREFERENCE（原文中の特定個体を指す表現）、REVISION（前の主張を置き換える明示的訂正）。単なる同時出現を空間関係にしないこと。銀行を支援の受け手とする文、bank managerなどの複合名詞は銀行が行為者とは限りません。

未知の述語でも原文から対象関係が明確なら注釈します。対応語彙の外だからgoldを空にすることは禁止です。辞書・採点規則を予測確認後に変更しません。金融述語は英語小文字の基本形（grant, award, support, disburse等）で記録します。

Relation1件のフィールド（追加キーなし）:

```json
{
  "relation_type": "FINANCIAL_AFFORDANCE",
  "anchor": {"source_index": 0, "start": 9, "end": 16},
  "subject": {"source_index": 0, "start": 4, "end": 8},
  "predicate": "grant",
  "object": {"source_index": 0, "start": 17, "end": 20},
  "target": null,
  "voice": "active",
  "polarity": "positive",
  "modality": "asserted"
}
```

これは内部教材 `The bank granted aid.` に対応する手書き例です。独立パイロットには使用しません。

## spanと意味の固定規則

- 座標はinputs内のsource_index（0始まり）、原文のUnicodeコードポイント[start,end)。UTF-8バイトやUTF-16単位ではありません。日本語も1文字ごとに数え、絵文字には特に注意します。原文の空白・句読点は変更しません。
- 金融・空間関係のsubject/objectは意味役割の最小の明示スパン。bankは冠詞を含めずbank語そのもの、対象はその行為の対象を表す名詞句（内部修飾・冠詞を含め、無関係な後続節と末尾句読点は除く）。受動文でもsubjectは意味上の行為者で、文法上の主語に入れ替えません。実装の切り出しが広すぎれば誤りです。
- 金融anchorは述語の実際の語形（granted等）。助動詞や否定語は含めません。空間anchorは明示的接続表現（near等）のスパン、predicateはLOCATED_NEAR。
- COREFERENCE: subject/anchorは指示表現（It/They/前者等）、objectは先行する個体の名詞スパン、predicate=REFERS_TO、target=null、voice=n/a。同じConceptの犬2匹は別spanとして扱います。複数照応は1先行個体につき1Relationです。単数でどちらを指すか決められない場合は推測して結ばず、goldには確定できる関係だけを入れます。曖昧性は裁定理由にも記録します。
- REVISION: anchorは訂正節全体（外側の区切りと末尾句読点を除く）。targetは訂正対象の元節全体。subject/object=null、predicate=REVISES、voice=n/a、modality=corrective。先行文との時間順だけで訂正としません。
- polarityはpositive/negative。否定も観察関係として注釈しますが肯定に変えません。
- modalityはasserted/hypothetical/corrective/provisional/retracted/quoted。quotedは評価側に明示的に設けた区分で、C2の現Schemaにはありません。引用内部の関係もquotedとして注釈することで、未対応を隠さずRecallに現します。引用も否定も現実の成立を主張するものではありません。
- voiceはactive/passive/n/a。明示的な空間の受動解釈が不要ならactive、照応/訂正はn/aです。

関係が本当にないと判断した場合はrelations=[]。未作業はnull/未入力のままstatus=pending。曖昧で裁定不能な資料はstatus=excludedと理由を記録し、勝手に「関係なし」に置き換えません。多義性があるが確定関係のみ注釈可能なら、その判断を裁定理由に残します。

## 注釈の返却形式

タスクの本文・出典・task_id・document_id・stratumを保持し、各itemに次を設定します。

```json
{
  "status": "adjudicated",
  "annotations": [
    {"annotator_id": "担当者A", "relations": []},
    {"annotator_id": "担当者B", "relations": []}
  ],
  "adjudication": {
    "adjudicator_id": "裁定者C",
    "relations": [],
    "rationale": "両者の一致点/不一致点と採用理由。空配列なら関係なしと判断した理由。"
  }
}
```

空配列は例示であり、実際のgoldを記入します。原注釈は裁定値で上書きしません。全員が独立した実作業を行ったことを確認したら、バッチのprocess_declarationの3フラグをtrueにし、statementに作業分離・盲検・重複監査の記録を記入します。架空の担当者名で埋めてはいけません。

## 採点

第一指標はrule_checked観察のRelation完全一致micro precision/recall/F1。否定・仮定を含め、肯定事実だけに絞りません。1文書の中で全フィールド完全一致による多重集合照合を行い、TP/FP/FNを文書ごとに計算して合算します。別文書同士では照合しません。欠落goldはFN、重複予測はFP、原文への座標変換不能もFPです。

raw候補の指標は別掲。quarantinedを第一指標から外しても、gold側の対象関係は消さないので見逃しはFNとして残ります。分母0のprecision/recall/F1はnullで、1.0や成功に置き換えません。

補助指標: 文書完全一致、層別成績、2名の文書単位完全一致率、役割/述語/否定等のslot正解数。slotは同じtype+anchorが双方1件ずつの場合だけ整列し、多対多を恣意的に対応付けません。slot指標だけでは見逃し率を評価できないため、必ず完全一致Recallも読みます。

未注釈が1件でも残る、裁定済み50件未満、独立性/盲検等の申告不足、タスクmanifest未提供の場合、real_worldバッチの採点は保留します。除外数と理由、80件計画に対する層別不足、出典群数を必ず報告します。50件到達は推論利用の受入合格ではありません。
