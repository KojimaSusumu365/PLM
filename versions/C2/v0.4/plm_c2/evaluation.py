from collections import Counter
from hashlib import sha256
from pathlib import Path
import json

from plm_c0 import evaluate, load_cases
from plm_c2_v03 import PLMC2Engine as FrozenV03
from .engine import C2Config, PLMC2Engine
from .audit import export_r1_observations

ROOT = Path(__file__).resolve().parents[1]


def load_v04_cases(split):
    return json.loads((ROOT / "data" / f"{split}_c2_v04.json").read_text(encoding="utf-8"))["cases"]


def projected_frame(frame, result):
    value = dict(frame)
    clauses = {c["clause_id"]: c for c in result["clauses"]}
    value["target_text"] = clauses.get(frame.get("target_clause_id"), {}).get("text")
    if frame["relation_type"] == "COREFERENCE":
        mentions = [m for m in result.get("mentions", []) if m["clause_id"] == frame.get("target_clause_id")
                    and m["kind"] == "nominal" and any(c in {"DOG", "CAT", "HUMAN", "ANIMAL", "LIVING", "VEHICLE"}
                                                     for c in m["concept_candidates"])]
        value["antecedent_ordinal"] = next((i for i, m in enumerate(mentions) if m["mention_id"] == frame.get("object_mention_id")), None)
    return value


def _normalize(value):
    return value.strip().lower().rstrip(".。") if isinstance(value, str) else value


def match_gold(gold, predictions):
    used, missing = set(), []
    for expected in gold:
        index = next((i for i, row in enumerate(predictions) if i not in used
                      and all(_normalize(row.get(k)) == _normalize(v) for k, v in expected.items())), None)
        if index is None:
            missing.append(expected)
        else:
            used.add(index)
    return {"tp": len(used), "fp": len(predictions) - len(used), "fn": len(missing),
            "missing": missing, "unexpected": [r for i, r in enumerate(predictions) if i not in used]}


def _prf(counts):
    tp, fp, fn = (counts[k] for k in ("tp", "fp", "fn"))
    return {"tp": tp, "fp": fp, "fn": fn,
            "precision": round(tp / (tp + fp), 4) if tp + fp else None,
            "recall": round(tp / (tp + fn), 4) if tp + fn else None,
            "f1": round(2 * tp / (2 * tp + fp + fn), 4) if 2 * tp + fp + fn else 1.0}


def semantic_evaluate(engine, cases):
    raw_totals, checked_totals, reasons = Counter(), Counter(), Counter()
    rows, schema_errors, graph_errors, constraints_failed = [], [], [], []
    inference_leaks = 0
    for case in cases:
        result = engine.analyze(case["inputs"])
        frames = result["relation_frames"]
        predictions = [projected_frame(f, result) for f in frames]
        raw = match_gold(case["gold_frames"], predictions)
        raw_totals.update({k: raw[k] for k in ("tp", "fp", "fn")})
        audited = "semantic_audit" in result
        checked = match_gold(case["gold_frames"], [projected_frame(f, result) for f in frames if f.get("semantic_status") == "rule_checked"]) if audited else None
        constraints = []
        if audited:
            checked_totals.update({k: checked[k] for k in ("tp", "fp", "fn")})
            audit = result["semantic_audit"]
            schema_errors.extend({"case": case["id"], "error": x} for x in audit["schema_errors"])
            graph_errors.extend({"case": case["id"], "error": x} for x in audit["graph_errors"])
            reasons.update(x for row in audit["frames"] for x in row["reasons"])
            if audit["schema_valid"] and audit["graph_valid"]:
                exported = export_r1_observations(result)
                inference_leaks += int(exported["boundary"]["inference_enabled"])
                inference_leaks += sum(o["eligible_for_inference"] for o in exported["observations"])
            if "reference_status" in case:
                actual = [r["status"] for r in result["reference_resolutions"]]
                if case["reference_status"] not in actual:
                    constraints.append("reference_status")
            if "distinct_nominal_entities" in case:
                actual = {m["entity_id"] for m in result["mentions"] if m["kind"] == "nominal"
                          and any(c in {"DOG", "CAT", "HUMAN"} for c in m["concept_candidates"])}
                if len(actual) != case["distinct_nominal_entities"]:
                    constraints.append("distinct_nominal_entities")
            constraints_failed.extend({"case": case["id"], "error": x} for x in constraints)
        if raw["fp"] or raw["fn"] or (checked and (checked["fp"] or checked["fn"])) or constraints:
            rows.append({"id": case["id"], "raw": raw, "checked": checked, "constraint_failures": constraints})
    return {"cases": len(cases), "raw_candidates": _prf(raw_totals),
            "rule_checked": _prf(checked_totals) if isinstance(engine, PLMC2Engine) else None,
            "schema_errors": schema_errors, "graph_errors": graph_errors,
            "constraint_failures": constraints_failed, "inference_leaks": inference_leaks,
            "quarantine_reasons": dict(reasons), "failures": rows}


def metamorphic_evaluate(engine):
    cases = json.loads((ROOT / "data" / "metamorphic_c2_v04.json").read_text(encoding="utf-8"))
    rows = []
    for case in cases:
        a, b = engine.analyze(case["a"]), engine.analyze(case["b"])
        selections = [a["selections"]["place"]["selected"], b["selections"]["place"]["selected"]]
        passed = selections == [case["expected"], case.get("expected_b", case["expected"])]
        if case["relation"] == "voice_invariance":
            for result, voice in ((a, "active"), (b, "passive")):
                passed &= any(f["subject"].lower() == "bank" and f["predicate"] == case["predicate"]
                              and _normalize(f["object_text"]) == _normalize(case["object_text"])
                              and f["voice"] == voice and f["applied"] for f in result["relation_frames"])
        elif case["relation"] == "polarity_flip":
            passed &= any(f["relation_type"] == "FINANCIAL_AFFORDANCE" and f["polarity"] == "negative"
                          and not f["applied"] for f in b["relation_frames"])
        rows.append({"id": case["id"], "passed": bool(passed), "selected": selections})
    return {"passed": sum(r["passed"] for r in rows), "total": len(rows), "cases": rows}


def verify_freeze():
    from freeze_runtime import tracked_files
    path = ROOT / "FREEZE_MANIFEST.json"
    if not path.exists():
        return {"valid": False, "errors": ["freeze_manifest_missing"]}
    manifest = json.loads(path.read_text(encoding="utf-8"))
    errors = [name for name, digest in manifest["files"].items()
              if not (ROOT / name).is_file() or sha256((ROOT / name).read_bytes()).hexdigest() != digest]
    current_names = {p.relative_to(ROOT).as_posix() for p in tracked_files(ROOT)}
    errors.extend("untracked:" + name for name in sorted(current_names - set(manifest["files"])))
    return {"valid": not errors, "errors": errors, "file_count": len(manifest["files"]),
            "manifest_sha256": sha256(path.read_bytes()).hexdigest()}


def first_run_signature(suite):
    return {"holdout_labels": suite["holdout"]["v04"]["cases"],
            "holdout_semantics": suite["holdout"]["semantics_v04"],
            "metamorphic": suite["metamorphic"], "freeze": suite["freeze"]}


def run_suite(bootstrap_samples=2000):
    prior_names = ["benchmark_v03.json", "challenge_c1_v01.json", "challenge_c1_v02.json", "challenge_c1_v03.json",
                   "challenge_c2_v01.json", "challenge_c2_v02.json", "development_c2_v03.json", "challenge_c2_v03.json"]
    prior, prior_audit_errors = {}, []
    for name in prior_names:
        cases = load_cases(str(ROOT / "data" / name))
        if name == "benchmark_v03.json":
            cases = [c for c in cases if c["split"] == "test"]
        prior[name] = {"v04": evaluate(PLMC2Engine(), cases, "v0.4", bootstrap_samples=bootstrap_samples),
                       "v03": evaluate(FrozenV03(), cases, "v0.3", bootstrap_samples=bootstrap_samples)}
        for case in cases:
            audit = PLMC2Engine().analyze(case["inputs"])["semantic_audit"]
            if not audit["schema_valid"] or not audit["graph_valid"]:
                prior_audit_errors.append({"dataset": name, "id": case["id"], "schema": audit["schema_errors"], "graph": audit["graph_errors"]})
    suites = {}
    for split in ("development", "holdout"):
        cases = load_v04_cases(split)
        suites[split] = {"v04": evaluate(PLMC2Engine(), cases, "v0.4", bootstrap_samples=bootstrap_samples),
                          "v03": evaluate(FrozenV03(), cases, "v0.3", bootstrap_samples=bootstrap_samples),
                          "uncalibrated": evaluate(PLMC2Engine(config=C2Config(use_empirical_calibration=False)), cases, "uncalibrated", bootstrap_samples=0),
                          "semantics_v04": semantic_evaluate(PLMC2Engine(), cases),
                          "semantics_v03": semantic_evaluate(FrozenV03(), cases)}
    ablations = {name: semantic_evaluate(PLMC2Engine(config=config), load_v04_cases("development"))
                 for name, config in {"no_semantic_roles": C2Config(use_semantic_roles=False),
                                      "no_instance_coreference": C2Config(use_instance_coreference=False),
                                      "no_grounded_revisions": C2Config(use_grounded_revisions=False)}.items()}
    split_inputs = {s: {json.dumps(c["inputs"], ensure_ascii=False) for c in load_v04_cases(s)} for s in ("development", "calibration", "holdout")}
    intersections = {f"{a}/{b}": len(split_inputs[a] & split_inputs[b]) for a, b in (("development", "calibration"), ("development", "holdout"), ("calibration", "holdout"))}
    calibration_model = json.loads((ROOT / "data" / "calibration_v04_model.json").read_text(encoding="utf-8"))
    suite = {"version": "PLM-C2 v0.4", "protocol": {"external_corpus": False, "independent_authorship": False,
                "holdout_execution": "first run after full runtime and calibration freeze; no subsequent runtime tuning",
                "semantic_score": "gold slot matching, separate from runtime consistency checks",
                "raw_vs_checked": "raw includes quarantined candidates; checked is a selective subset",
                "split_input_overlap": intersections}, "prior": prior, "prior_audit_errors": prior_audit_errors,
             **suites, "ablations": ablations, "metamorphic": metamorphic_evaluate(PLMC2Engine()),
             "calibration_model": calibration_model, "freeze": verify_freeze()}
    dev, held = suite["development"], suite["holdout"]
    first_path = ROOT / "FIRST_EVALUATION.json"
    first_matches = json.loads(first_path.read_text(encoding="utf-8")) == first_run_signature(suite) if first_path.exists() else None
    acceptance = {
        "all_prior_label_accuracy_at_least_0_98": all(s["v04"]["metrics"]["top1_accuracy"] >= .98 for s in prior.values()),
        "development_label_accuracy_1": dev["v04"]["metrics"]["top1_accuracy"] == 1.,
        "development_checked_semantic_f1_at_least_0_98": dev["semantics_v04"]["rule_checked"]["f1"] >= .98,
        "development_instance_constraints": not dev["semantics_v04"]["constraint_failures"],
        "holdout_label_accuracy_at_least_0_85": held["v04"]["metrics"]["top1_accuracy"] >= .85,
        "holdout_checked_precision_at_least_0_90": (held["semantics_v04"]["rule_checked"]["precision"] or 0) >= .90,
        "holdout_checked_recall_at_least_0_75": (held["semantics_v04"]["rule_checked"]["recall"] or 0) >= .75,
        "holdout_instance_constraints": not held["semantics_v04"]["constraint_failures"],
        "schema_and_graph_contracts": not prior_audit_errors and all(not suites[s]["semantics_v04"][k] for s in suites for k in ("schema_errors", "graph_errors")),
        "inference_never_enabled": all(s["semantics_v04"]["inference_leaks"] == 0 for s in suites.values()),
        "metamorphic_pairs_pass": suite["metamorphic"]["passed"] == suite["metamorphic"]["total"],
        "calibration_input_disjoint": not any(intersections.values()),
        "calibrator_bound_to_calibration_data": calibration_model["data_sha256"] == sha256((ROOT / "data" / "calibration_c2_v04.json").read_bytes()).hexdigest(),
        "complete_runtime_freeze_matches": suite["freeze"]["valid"],
        "first_holdout_run_reproduced": first_matches,
        "frozen_v03_reference_preserved": prior["challenge_c2_v03.json"]["v03"]["metrics"]["top1_accuracy"] == .9583,
    }
    suite["acceptance"], suite["acceptance_passed"] = acceptance, all(acceptance.values())
    return suite


def render_markdown(suite):
    lines = ["# PLM-C2 v0.4 評価レポート", "", "Relationの正解照合、個体照応、訂正先の根拠、R1観察境界を評価した。",
             "全データは同じ開発過程で作成した内部評価であり、外部独立評価ではない。holdoutは実行を保留した分割である。", "",
             "## 分類とRelation意味評価", "", "| 分割 | 件数 | v0.4分類 | v0.3分類 | v0.4検証済みP/R/F1 | v0.4全候補P/R/F1 |", "|---|---:|---:|---:|---|---|"]
    for name in ("development", "holdout"):
        s = suite[name]
        p, raw = s["semantics_v04"]["rule_checked"], s["semantics_v04"]["raw_candidates"]
        lines.append(f"| {name} | {s['semantics_v04']['cases']} | {s['v04']['metrics']['top1_accuracy']} | {s['v03']['metrics']['top1_accuracy']} | {p['precision']}/{p['recall']}/{p['f1']} | {raw['precision']}/{raw['recall']}/{raw['f1']} |")
    lines += ["", "検証済みはrule_checkedの部分集合。全候補には採用不可・未対応の候補も含む。P/R/F1は別途注釈した主体・述語・対象・態・否定・訂正先・照応先との照合であり、形式検証とは別である。", "",
              "## 既存評価の回帰", "", "| データ | v0.4 Top-1 | v0.3 Top-1 |", "|---|---:|---:|"]
    for name, s in suite["prior"].items():
        lines.append(f"| {name} | {s['v04']['metrics']['top1_accuracy']} | {s['v03']['metrics']['top1_accuracy']} |")
    lines += ["", "holdout Top-1の95% cluster-bootstrap CI: " + json.dumps(suite["holdout"]["v04"]["confidence_intervals"]["top1_accuracy_95"]),
              "", "## holdoutの失敗", ""]
    errors = [c for c in suite["holdout"]["v04"]["cases"] if not c["top1_correct"]]
    lines.extend(f"- {c['id']}: 正解 {c['expected']} / 出力 {c['predicted']} / 確信度 {c['selection_confidence']}" for c in errors)
    if not errors:
        lines.append("- 分類の失敗なし。")
    for c in suite["holdout"]["semantics_v04"]["failures"]:
        if c["checked"] and (c["checked"]["fp"] or c["checked"]["fn"]):
            lines.append(f"- Relation {c['id']}: FP={c['checked']['fp']}, FN={c['checked']['fn']}")
    lines += ["", "## 校正と保留", "", "30件の専用校正データで単調な確信度変換を推定。分類・保留の正誤を目的とし、個体同定の正しさとは区別する。", "",
              "| 分割 | 校正前ECE | 校正後ECE | 校正前Brier | 校正後Brier |", "|---|---:|---:|---:|---:|"]
    for name in ("development", "holdout"):
        old, new = suite[name]["uncalibrated"]["metrics"], suite[name]["v04"]["metrics"]
        lines.append(f"| {name} | {old['expected_calibration_error']} | {new['expected_calibration_error']} | {old['brier_score']} | {new['brier_score']} |")
    lines += ["", "閾値別の採用率と精度、信頼区間、校正区間ごとの件数はJSONを参照。校正の改善は全分布への保証ではない。", "",
              "## R1境界・反事実的変形", "", f"- 意味を保つ態変換・接頭辞・無関係文、および否定反転: {suite['metamorphic']['passed']}/{suite['metamorphic']['total']}。",
              "- R1はobserve_only。全候補に根拠・検証状態を付け、推論採用は常に無効。空入力は準備完了にしない。",
              "- export時に再検証し、壊れたSchema・参照・グラフを拒否。意味が未検証の候補はquarantinedとして表示。", "",
              "## 機能除去診断", "", "| 除去機能 | 検証済みF1 | 個体制約違反数 |", "|---|---:|---:|"]
    for name, s in suite["ablations"].items():
        lines.append(f"| {name} | {s['rule_checked']['f1']} | {len(s['constraint_failures'])} |")
    lines += ["", "## 受入判定", ""]
    lines.extend(f"- {'PASS' if passed else 'PENDING' if passed is None else 'FAIL'}: {name}" for name, passed in suite["acceptance"].items())
    lines += ["", f"全体: {'PASS' if suite['acceptance_passed'] else 'NOT PASS'}", "",
              "## 制約", "", "英語の限定構文と小さなConcept辞書に依存する。校正データ30件・holdout32件は小規模で、構文・語彙も完全独立ではない。複雑な照応・省略・引用・未知述語・一般的な構文解析は未解決。R1の自動推論や本番開放は今回の成果に含まれない。", ""]
    return "\n".join(lines)
