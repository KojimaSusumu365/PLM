"""Read-only analysis of the sealed first result; NEVER changes selection or thresholds."""
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parent/"PLM-P1-v0.2"
result=json.loads((ROOT/"results/EVALUATION_RESULTS.json").read_text(encoding="utf-8"))
errors=[r for r in result["rows"] if r["method"]=="projected_adaptive" and r["condition"] in {"masked_noise","unknown_nuisance"} and r["outcome"] in {"wrong","abstained","false_accept"}]
out={"scope":"post-evaluation diagnosis only; no source or policy changes", "rows":errors}
(ROOT/"results/POST_EVALUATION_ERRORS.json").write_text(json.dumps(out,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
lines=["# 未知評価後の残存誤り監査", "", "以下は初回結果の解釈であり、評価後の方式選択・閾値調整はしていません。", ""]
for r in errors:
    lines += [f"## {r['condition']} / {r['outcome']}","",f"符号seed {r['code_seed']}、チャネルseed {r['channel_seed']}、{r['event_id']} / {r['role']}、負例種別または正例: {r['test_kind']}。",
              f"首位スコア {r['top_score']}、振幅閾値 {r.get('amplitude_threshold')}、候補間差 {r['margin']}、差の閾値 {r.get('margin_threshold')}。判定理由: {r['reason']}。", ""]
lines += ["## 固定判定とのトレードオフ", "",
          "同じ干渉除去後の固定判定では、masked_noiseの回復は512/512、負例誤受理は0/1024でした。採用した適応判定は同じ回復数で誤受理1/1024です。一方jitter_onlyでは、固定判定508/512に対して適応判定512/512でした。",
          "したがって、適応判定がすべての条件で固定判定を上回るとは結論しません。開発段階で選んだ方式を維持し、両方式の結果を全て公開します。追加校正を行うなら新しい開発・評価分割を設け、今回の未知評価を再び未知データと呼ばないことが必要です。", "",
          "## S1へ進む際の注意", "",
          "P1の主目標は達成しましたが、極端な観測不足・高負荷では全保留です。同期後にP1が保留した場合も失敗として残し、SS復調器で強制的に候補を受理しない設計にします。",
          "今回の計算では同じ候補符号を繰り返し組み立てるため評価に時間がかかります。将来のキャッシュ・行列計算の共通化は有用ですが、今回は固定後のコードを変更せず実行しました。", ""]
(ROOT/"results/POST_EVALUATION_AUDIT.md").write_text("\n".join(lines),encoding="utf-8")
print(json.dumps(out,indent=2))
