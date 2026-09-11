# PLM-R1 v0.1 観察レビュー台帳

推論は無効。rule_checkedはC2の規則整合性であり、独立評価済みの事実を意味しません。
同一内容は1件として集計し、別出典・改訂との対応は別に保持します。

内容 16 件 / 出典・改訂 17 件 / 観察 14 件。

## internal:hypothetical@1

内容ID: 0579d7d6292831c04c742dee785987fc875163735f1cedb690801ae9785d10e9

原文: If the bank grants aid.

C2分類（Relationの真偽とは別）: entity → UNRESOLVED; selection_confidence=0.7778

C2分類（Relationの真偽とは別）: place → UNRESOLVED; selection_confidence=0.7778

### F0001 — FINANCIAL_AFFORDANCE

節: If the bank grants aid

主体: bank / 述語: grant / 対象: aid

状態: rule_checked / positive / hypothetical / active; 推論不可。

主体個体: 0579d7d6292831c04c742dee785987fc875163735f1cedb690801ae9785d10e9:ENT000001 / 対象個体: 0579d7d6292831c04c742dee785987fc875163735f1cedb690801ae9785d10e9:ENT000002

規則・隔離理由: bounded_bank_event / 

根拠 E0001: If the bank grants aid; active=True; superseded_by=None

根拠 E0002: If the bank grants aid; active=True; superseded_by=None

## internal:plural_reference@1

内容ID: 187adb556062f61ec6f8a07bbdc4971ce0fac9755e2a9efefcb8d8379fddd020

原文: A dog and another dog entered. / They were photographed.

C2分類（Relationの真偽とは別）: entity → DOG; selection_confidence=0.9286

C2分類（Relationの真偽とは別）: place → UNRESOLVED; selection_confidence=0.7778

### F0001 — COREFERENCE

節: They were photographed

主体: They / 述語: REFERS_TO / 対象: DOG

状態: rule_checked / positive / asserted / n/a; 推論不可。

主体個体: 187adb556062f61ec6f8a07bbdc4971ce0fac9755e2a9efefcb8d8379fddd020:ENT000001 / 対象個体: 187adb556062f61ec6f8a07bbdc4971ce0fac9755e2a9efefcb8d8379fddd020:ENT000001

規則・隔離理由: instance_reference / 

根拠 E0001: A dog and another dog entered; active=True; superseded_by=None

### F0002 — COREFERENCE

節: They were photographed

主体: They / 述語: REFERS_TO / 対象: DOG

状態: rule_checked / positive / asserted / n/a; 推論不可。

主体個体: 187adb556062f61ec6f8a07bbdc4971ce0fac9755e2a9efefcb8d8379fddd020:ENT000002 / 対象個体: 187adb556062f61ec6f8a07bbdc4971ce0fac9755e2a9efefcb8d8379fddd020:ENT000002

規則・隔離理由: instance_reference / 

根拠 E0002: A dog and another dog entered; active=True; superseded_by=None

## internal:active@1, internal:active-copy@1

内容ID: 1d386a06d70a3a239ffc27b767c7997533c0b8958be3ae6ba2ef76a47d2256d4

原文: The bank granted aid.

C2分類（Relationの真偽とは別）: entity → UNRESOLVED; selection_confidence=0.7778

C2分類（Relationの真偽とは別）: place → FINANCIAL_BANK; selection_confidence=0.875

### F0001 — FINANCIAL_AFFORDANCE

節: The bank granted aid

主体: bank / 述語: grant / 対象: aid

状態: rule_checked / positive / asserted / active; 推論不可。

主体個体: 1d386a06d70a3a239ffc27b767c7997533c0b8958be3ae6ba2ef76a47d2256d4:ENT000001 / 対象個体: 1d386a06d70a3a239ffc27b767c7997533c0b8958be3ae6ba2ef76a47d2256d4:ENT000002

規則・隔離理由: bounded_bank_event / 

根拠 E0001: The bank granted aid; active=True; superseded_by=None

根拠 E0002: The bank granted aid; active=True; superseded_by=None

根拠 E0003: The bank granted aid; active=True; superseded_by=None

根拠 E0004: The bank granted aid; active=True; superseded_by=None

## internal:quoted@1

内容ID: 228fc660b83c9d4223cc3a173e59bf0cb7a468c43e0236cb3df1215a62f47e9b

原文: &quot;The bank granted aid.&quot;

注意: no_rule_checked_relation_review_original_text

C2分類（Relationの真偽とは別）: entity → UNRESOLVED; selection_confidence=0.7778

C2分類（Relationの真偽とは別）: place → FINANCIAL_BANK; selection_confidence=0.875

### F0001 — FINANCIAL_AFFORDANCE

節: &quot;The bank granted aid

主体: bank / 述語: grant / 対象: aid

状態: quarantined / positive / asserted / active; 推論不可。

主体個体: 228fc660b83c9d4223cc3a173e59bf0cb7a468c43e0236cb3df1215a62f47e9b:ENT000001 / 対象個体: 228fc660b83c9d4223cc3a173e59bf0cb7a468c43e0236cb3df1215a62f47e9b:ENT000002

規則・隔離理由: bounded_bank_event / quoted_scope_requires_review

根拠 E0001: &quot;The bank granted aid; active=True; superseded_by=None

根拠 E0002: &quot;The bank granted aid; active=True; superseded_by=None

根拠 E0003: &quot;The bank granted aid; active=True; superseded_by=None

根拠 E0004: &quot;The bank granted aid; active=True; superseded_by=None

## internal:negative@1

内容ID: 3676c0c094f8160336daf6fee0934100ba5c7c51525b54a3a6cb81f2a2636dc6

原文: The bank did not grant aid.

C2分類（Relationの真偽とは別）: entity → UNRESOLVED; selection_confidence=0.7778

C2分類（Relationの真偽とは別）: place → UNRESOLVED; selection_confidence=0.7778

### F0001 — FINANCIAL_AFFORDANCE

節: The bank did not grant aid

主体: bank / 述語: grant / 対象: aid

状態: rule_checked / negative / asserted / active; 推論不可。

主体個体: 3676c0c094f8160336daf6fee0934100ba5c7c51525b54a3a6cb81f2a2636dc6:ENT000001 / 対象個体: 3676c0c094f8160336daf6fee0934100ba5c7c51525b54a3a6cb81f2a2636dc6:ENT000002

規則・隔離理由: bounded_bank_event / 

根拠 E0001: The bank did not grant aid; active=True; superseded_by=None

根拠 E0002: The bank did not grant aid; active=True; superseded_by=None

## internal:passive@1

内容ID: 4bbe40e48eb604ec5c37c3f503bdc2115cd5710beeee2f7849c9e2abf6517c52

原文: Grants for a river restoration were awarded by the bank.

C2分類（Relationの真偽とは別）: entity → UNRESOLVED; selection_confidence=0.7778

C2分類（Relationの真偽とは別）: place → FINANCIAL_BANK; selection_confidence=0.875

### F0001 — SPATIAL_ASSOCIATION

節: Grants for a river restoration were awarded by the bank

主体: bank / 述語: river / 対象: Grants for a river restoration were awarded by the bank

状態: quarantined / positive / asserted / active; 推論不可。

主体個体: None / 対象個体: None

規則・隔離理由: legacy_context / legacy_association_not_semantically_verified

根拠 E0001: Grants for a river restoration were awarded by the bank; active=False; superseded_by=None

根拠 E0002: Grants for a river restoration were awarded by the bank; active=True; superseded_by=None

根拠 E0003: Grants for a river restoration were awarded by the bank; active=True; superseded_by=None

根拠 E0004: Grants for a river restoration were awarded by the bank; active=True; superseded_by=None

根拠 E0005: Grants for a river restoration were awarded by the bank; active=True; superseded_by=None

### F0002 — FINANCIAL_AFFORDANCE

節: Grants for a river restoration were awarded by the bank

主体: bank / 述語: award / 対象: Grants for a river restoration

状態: rule_checked / positive / asserted / passive; 推論不可。

主体個体: 4bbe40e48eb604ec5c37c3f503bdc2115cd5710beeee2f7849c9e2abf6517c52:ENT000002 / 対象個体: 4bbe40e48eb604ec5c37c3f503bdc2115cd5710beeee2f7849c9e2abf6517c52:ENT000003

規則・隔離理由: bounded_bank_event / 

根拠 E0001: Grants for a river restoration were awarded by the bank; active=False; superseded_by=None

根拠 E0002: Grants for a river restoration were awarded by the bank; active=True; superseded_by=None

根拠 E0003: Grants for a river restoration were awarded by the bank; active=True; superseded_by=None

根拠 E0004: Grants for a river restoration were awarded by the bank; active=True; superseded_by=None

根拠 E0005: Grants for a river restoration were awarded by the bank; active=True; superseded_by=None

## internal:ambiguous_reference@1

内容ID: 4cb3659fc1f64c064625a734ec5d8e745d6f94fb41073f84d5e589e18e6bb665

原文: A dog and another dog entered. / It was photographed.

注意: no_relation_extracted_not_proof_of_absence

注意: reference_ambiguous:S002:C001

注意: no_rule_checked_relation_review_original_text

C2分類（Relationの真偽とは別）: entity → DOG; selection_confidence=0.5556

C2分類（Relationの真偽とは別）: place → UNRESOLVED; selection_confidence=0.7778

## internal:empty@1

内容ID: 4f53cda18c2baa0c0354bb5f9a3ecbe5ed12ab4d8e11ba873c2f11161202b945

原文: 

注意: no_relation_extracted_not_proof_of_absence

注意: no_rule_checked_relation_review_original_text

C2分類（Relationの真偽とは別）: entity → UNRESOLVED; selection_confidence=0.7778

C2分類（Relationの真偽とは別）: place → UNRESOLVED; selection_confidence=0.7778

## internal:known_reassessed@1

内容ID: 66e3cc15d0e3bb2a385eff17955db901960dafac71ca5a7a4e5f06985c728dd1

原文: Originally marked cat: reassessed as dog.

注意: no_relation_extracted_not_proof_of_absence

注意: no_rule_checked_relation_review_original_text

C2分類（Relationの真偽とは別）: entity → ANIMAL; selection_confidence=0.5556

C2分類（Relationの真偽とは別）: place → UNRESOLVED; selection_confidence=0.7778

レビュー記録: known-gap:known_reassessed / internal_implementation_note_not_independent_reviewer / needs_review

C2 known gap: reassessed is unsupported; no grounded revision. R1 retains source and classification without repairing C2.

## internal:japanese_revision@1

内容ID: 7c5d32dff5bbda8a8f7f34306dc5aa6732fb2b564fa56be3bb8c3574e5fda0ba

原文: 犬、いや、猫。

C2分類（Relationの真偽とは別）: entity → CAT; selection_confidence=0.9286

C2分類（Relationの真偽とは別）: place → UNRESOLVED; selection_confidence=0.7778

### F0001 — REVISION

節: 猫

主体: S001:C003 / 述語: REVISES / 対象: 犬

状態: rule_checked / positive / corrective / n/a; 推論不可。

主体個体: None / 対象個体: None

規則・隔離理由: ledger_supersession / 

根拠 E0001: 犬; active=False; superseded_by=E0002

根拠 E0002: 猫; active=True; superseded_by=None

## internal:spatial@1

内容ID: 93618c0b86895b024b86991ea41764716a7afca3269b18f2f0a0433314fae7e5

原文: The bank is near the river.

C2分類（Relationの真偽とは別）: entity → UNRESOLVED; selection_confidence=0.7778

C2分類（Relationの真偽とは別）: place → RIVER_BANK; selection_confidence=0.9286

### F0001 — SPATIAL_ASSOCIATION

節: The bank is near the river

主体: bank / 述語: LOCATED_NEAR / 対象: river

状態: rule_checked / positive / asserted / n/a; 推論不可。

主体個体: 93618c0b86895b024b86991ea41764716a7afca3269b18f2f0a0433314fae7e5:ENT000001 / 対象個体: 93618c0b86895b024b86991ea41764716a7afca3269b18f2f0a0433314fae7e5:ENT000002

規則・隔離理由: bounded_spatial / 

根拠 E0001: The bank is near the river; active=True; superseded_by=None

根拠 E0002: The bank is near the river; active=True; superseded_by=None

根拠 E0003: The bank is near the river; active=True; superseded_by=None

根拠 E0004: The bank is near the river; active=True; superseded_by=None

根拠 E0005: The bank is near the river; active=True; superseded_by=None

## internal:known_disbursed@1

内容ID: b2323bbe2679ad07d35bd122a9cbd3fac61fe203b9c548e3f7ad8ab1f1bb89ea

原文: The bank disbursed grants for river restoration.

注意: no_rule_checked_relation_review_original_text

C2分類（Relationの真偽とは別）: entity → UNRESOLVED; selection_confidence=0.7778

C2分類（Relationの真偽とは別）: place → UNRESOLVED; selection_confidence=0.7778

### F0001 — SPATIAL_ASSOCIATION

節: The bank disbursed grants for river restoration

主体: bank / 述語: river / 対象: The bank disbursed grants for river restoration

状態: quarantined / positive / asserted / active; 推論不可。

主体個体: None / 対象個体: None

規則・隔離理由: legacy_context / legacy_association_not_semantically_verified

根拠 E0001: The bank disbursed grants for river restoration; active=True; superseded_by=None

根拠 E0002: The bank disbursed grants for river restoration; active=True; superseded_by=None

根拠 E0003: The bank disbursed grants for river restoration; active=False; superseded_by=None

レビュー記録: known-gap:known_disbursed / internal_implementation_note_not_independent_reviewer / needs_review

C2 known gap: disbursed is unsupported; expected financial relation is absent. R1 displays the document and does not invent the missing relation.

## internal:no_relation@1

内容ID: b6f171d05abfb9278489c90bfad635a9a639a75a931c17654beaff26dd16f8d2

原文: Clouds gather overhead.

注意: no_relation_extracted_not_proof_of_absence

注意: no_rule_checked_relation_review_original_text

C2分類（Relationの真偽とは別）: entity → UNRESOLVED; selection_confidence=0.7778

C2分類（Relationの真偽とは別）: place → UNRESOLVED; selection_confidence=0.7778

## internal:revision@1

内容ID: be88b8d60516ba94fdb72df52c38000414e3411bfab3a5b22f7a16ada6f41649

原文: Originally marked dog: reclassified as cat.

C2分類（Relationの真偽とは別）: entity → CAT; selection_confidence=0.9286

C2分類（Relationの真偽とは別）: place → UNRESOLVED; selection_confidence=0.7778

### F0001 — REVISION

節: reclassified as cat

主体: S001:C002 / 述語: REVISES / 対象: Originally marked dog

状態: rule_checked / positive / corrective / n/a; 推論不可。

主体個体: None / 対象個体: None

規則・隔離理由: ledger_supersession / 

根拠 E0001: Originally marked dog; active=False; superseded_by=E0002

根拠 E0002: reclassified as cat; active=True; superseded_by=None

## internal:known_passive_agent_manager@1

内容ID: cce4feae018a182f41cf2736c899d0e6f2f44d7e99c0ba2a7c4387d6696f2cfc

原文: A river plan was supported by the bank manager.

注意: no_rule_checked_relation_review_original_text

C2分類（Relationの真偽とは別）: entity → UNRESOLVED; selection_confidence=0.7778

C2分類（Relationの真偽とは別）: place → RIVER_BANK; selection_confidence=0.9286

### F0001 — SPATIAL_ASSOCIATION

節: A river plan was supported by the bank manager

主体: bank / 述語: LOCATED_NEAR / 対象: river

状態: quarantined / positive / asserted / n/a; 推論不可。

主体個体: cce4feae018a182f41cf2736c899d0e6f2f44d7e99c0ba2a7c4387d6696f2cfc:ENT000002 / 対象個体: cce4feae018a182f41cf2736c899d0e6f2f44d7e99c0ba2a7c4387d6696f2cfc:ENT000001

規則・隔離理由: bounded_spatial / unverified_spatial_attachment

根拠 E0001: A river plan was supported by the bank manager; active=True; superseded_by=None

根拠 E0002: A river plan was supported by the bank manager; active=True; superseded_by=None

根拠 E0003: A river plan was supported by the bank manager; active=True; superseded_by=None

根拠 E0004: A river plan was supported by the bank manager; active=True; superseded_by=None

根拠 E0005: A river plan was supported by the bank manager; active=True; superseded_by=None

レビュー記録: known-gap:known_passive_agent_manager / internal_implementation_note_not_independent_reviewer / needs_review

C2 holdout policy expected UNRESOLVED but selected RIVER_BANK at 0.9286 selection_confidence. Policy-dependent expected label; Relation is quarantined. R1 does not repair this.

## internal:singular_reference@1

内容ID: ffc251f27d8454caa72d918e7bfc093c31a21f2f8d8b930658b71bdee46c7bb2

原文: A cat entered. / It was photographed.

C2分類（Relationの真偽とは別）: entity → CAT; selection_confidence=0.9286

C2分類（Relationの真偽とは別）: place → UNRESOLVED; selection_confidence=0.7778

### F0001 — COREFERENCE

節: It was photographed

主体: It / 述語: REFERS_TO / 対象: CAT

状態: rule_checked / positive / asserted / n/a; 推論不可。

主体個体: ffc251f27d8454caa72d918e7bfc093c31a21f2f8d8b930658b71bdee46c7bb2:ENT000001 / 対象個体: ffc251f27d8454caa72d918e7bfc093c31a21f2f8d8b930658b71bdee46c7bb2:ENT000001

規則・隔離理由: instance_reference / 

根拠 E0001: A cat entered; active=True; superseded_by=None

