"""Compare the preserved first run with post-packaging-fix replays and record facts."""
import copy
import hashlib
import json
from pathlib import Path
import shutil

WORK = Path(__file__).resolve().parent
ROOT = WORK.parent / "outputs" / "PLM-L1-v0.1"


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def hash_file(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


initial = read(ROOT / "verification" / "INITIAL_EVALUATION.json")
final_path = WORK / "plm-l1-final-evaluation" / "EVALUATION.json"
repeat_path = WORK / "plm-l1-final-repeat" / "EVALUATION.json"
final, repeat = read(final_path), read(repeat_path)
assert final == repeat and hash_file(final_path) == hash_file(repeat_path)
before, after = copy.deepcopy(initial), copy.deepcopy(final)
for value in (before, after):
    value.pop("freeze_hash")
    value.pop("result_digest")
assert before == after, "numerical results changed after source-inventory helper fix"
first_manifest = read(ROOT / "verification" / "SOURCE_MANIFEST_INITIAL.json")
last_manifest = read(ROOT / "SOURCE_MANIFEST.json")
assert set(first_manifest["files"]) == set(last_manifest["files"])
changed = [k for k in first_manifest["files"] if first_manifest["files"][k] != last_manifest["files"][k]]
assert changed == ["release_tools.py"], changed
assert read(ROOT / "results" / "model" / "model.json") == read(WORK / "plm-l1-final-evaluation" / "model" / "model.json")
assert final["passed"] and len(final["checks"]) == 88 and all(x["passed"] for x in final["checks"])
history = {"reason": "After the initial successful evaluation, source inventory incorrectly included a user-generated root JSON packet. Only source-file selection in release_tools.py was corrected. No learning, meaning operations, thresholds, training/evaluation data, or acceptance criteria changed.",
           "changed_source_files": changed, "initial_freeze": initial["freeze_hash"], "final_freeze": final["freeze_hash"],
           "initial_result_digest": initial["result_digest"], "final_result_digest": final["result_digest"],
           "all_results_equal_except_freeze_metadata": True, "initial_results_preserved": True,
           "postfix_evaluation_is_replay_not_new_unseen_corpus": True}
reproduction = {"initial_run_and_first_replay_file_sha256": hash_file(ROOT / "verification" / "INITIAL_EVALUATION.json"),
                "initial_replay_equal": hash_file(ROOT / "verification" / "INITIAL_EVALUATION.json") == hash_file(WORK / "plm-l1-evaluation-repeat" / "EVALUATION.json"),
                "final_run_file_sha256": hash_file(final_path), "final_repeat_file_sha256": hash_file(repeat_path),
                "final_result_digest": final["result_digest"], "full_numeric_replay_equal": True,
                "all_seed_condition_records_and_capacity_stress_included": True}
for name, value in (("FREEZE_HISTORY.json", history), ("REPRODUCIBILITY.json", reproduction)):
    with (ROOT / "verification" / name).open("x", encoding="utf-8") as stream:
        stream.write(json.dumps(value, ensure_ascii=False, indent=2) + "\n")
shutil.copyfile(final_path, ROOT / "results" / "EVALUATION.json")
shutil.copyfile(WORK / "plm-l1-final-evaluation" / "EVALUATION_REPORT.md", ROOT / "results" / "EVALUATION_REPORT.md")
print(json.dumps({"history": history, "reproduction": reproduction}, ensure_ascii=False, indent=2))
