"""Frozen four-fold compositional holdout evaluation, all models refitted."""
import argparse
import copy
import hashlib
import json
from pathlib import Path
from plm_l1_v04.algebra import canonical, digest
from plm_l1_v04.training import fit
from evaluation_support import ROOT, FOLDS, data, train_for, heldout, text_goal, interpret, INVALID, GOALS, OldSS, PartialTable, OldTable


def source_files():
    files=[p for p in ROOT.iterdir() if p.is_file() and p.suffix in (".py",".md",".txt")]
    for name in ("plm_l1_v04","tests","evaluation","data","vendor"):
        files += [p for p in (ROOT/name).rglob("*") if p.is_file()]
    return sorted(p for p in files if "__pycache__" not in p.parts and p.suffix!=".pyc")


def verify_freeze():
    manifest=json.loads((ROOT/"SOURCE_MANIFEST.json").read_text(encoding="utf-8"))
    actual={p.relative_to(ROOT).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in source_files()}
    if actual!=manifest["files"]:
        raise ValueError("frozen source changed")
    return digest(manifest)


def bad_packets(model,meaning):
    p=model.encode(meaning)
    key="model_fingerprint" if "model_fingerprint" in p else "writer_fingerprint"
    n=p["dimension"]
    result=[dict(p,text="hidden source"),dict(p,meaning=meaning),dict(p,**{key:"bad"}),dict(p,dimension=0),
            dict(p,eligible_for_inference=True),dict(p,real=[0.]*n,imag=[0.]*n)]
    for value in (float("nan"),float("inf"),True,"1",1e100):
        q=copy.deepcopy(p)
        q["real"][0]=value
        result.append(q)
    result.append(dict(p,real=p["real"][:-1]))
    return result


def assess(model,split,fold,numeric=True):
    counts={}
    records=[]
    def add(stage,bucket,exact,accepted,record):
        for suffix,value in (("requests",1),("exact",int(exact)),("accepted",int(accepted)),("wrong",int(accepted and not exact))):
            k=stage+"_"+bucket+"_"+suffix
            counts[k]=counts.get(k,0)+value
        records.append({"stage":stage,"bucket":bucket,**record})
    rows=data(split)
    meanings={canonical(r["meaning"]):r["meaning"] for r in rows}
    for key in sorted(meanings):
        meaning=meanings[key]
        packet=model.encode(meaning)
        for goal in GOALS:
            out=model.generate(packet,goal)
            bucket="heldout" if heldout(meaning,goal,fold) else "seen"
            exact=out["status"]=="generated" and interpret(out["text"])==meaning and text_goal(out["text"])==goal
            add("generate",bucket,exact,out["status"]=="generated",{"expected":meaning,"goal":goal,"output":out.get("text"),"status":out["status"],"reason":out.get("reason")})
    for row in rows:
        read=model.read(row["text"])
        bucket="heldout" if heldout(row["meaning"],text_goal(row["text"]),fold) else "seen"
        meaning=model.recover(read["packet"]).get("meaning") if read["status"]=="read" else None
        add("read",bucket,meaning==row["meaning"],read["status"]=="read",{"input":row["text"],"expected":row["meaning"],"recovered":meaning,"status":read["status"],"reason":read.get("reason")})
        for goal in GOALS:
            # No gold meaning or original text enters the generator in this path.
            out=model.generate(read["packet"],goal) if read["status"]=="read" else {"status":"abstain","reason":"reader_abstained"}
            group="both_heldout" if bucket=="heldout" and heldout(row["meaning"],goal,fold) else "other"
            exact=out["status"]=="generated" and interpret(out["text"])==row["meaning"] and text_goal(out["text"])==goal
            add("roundtrip",group,exact,out["status"]=="generated",{"input_for_evaluator_only":row["text"],"expected":row["meaning"],"goal":goal,"output":out.get("text"),"status":out["status"],"reason":out.get("reason")})
    counts["invalid_texts"]=len(INVALID)
    counts["invalid_texts_accepted"]=sum(model.read(text)["status"]=="read" for text in INVALID)
    packets=bad_packets(model,next(iter(meanings.values()))) if numeric else []
    counts["invalid_packets"]=len(packets)
    counts["invalid_packets_generated"]=sum(model.generate(p)["status"]=="generated" for p in packets)
    return {"counts":counts,"records":records,"fingerprint":model.fingerprint,"training_pairs":model.meta["pair_count"],"statistics":model.meta["statistics"]}


def one(seed,fold,condition,dimension,split):
    pairs,lexicon=train_for(fold),data("lexicon")
    if condition=="old_ss":
        model=OldSS(pairs,lexicon,seed,dimension)
    else:
        model=fit(pairs,lexicon,seed=seed,dimension=dimension,partial=condition!="full_context",learning=condition!="no_learning")
    result=assess(model,split,fold)
    result.update(seed=seed,fold=fold,condition=condition,dimension=dimension)
    return result,model


def judge(rows,protocol,regressions=()):
    checks=[]
    for fold in protocol["folds"]:
        for seed in protocol["evaluation_seeds"]:
            variants={r["condition"]:r["counts"] for r in rows if r["fold"]==fold and r["seed"]==seed}
            full=variants["partial"]
            values={}
            for key in ("read_heldout","read_seen","generate_heldout","generate_seen","roundtrip_both_heldout","roundtrip_other"):
                values[key]=full[key+"_exact"]/full[key+"_requests"]>=.98
            values["no_wrong"]=sum(v for k,v in full.items() if k.endswith("_wrong"))==0
            values["invalid_boundaries"]=full["invalid_texts_accepted"]+full["invalid_packets_generated"]==0
            for condition in ("full_context","old_ss"):
                c=variants[condition]
                values[condition+"_seen_control"]=all(c[s+"_seen_exact"]/c[s+"_seen_requests"]>=.98 for s in ("read","generate"))
                values[condition+"_novelty_drop"]=all(full[s+"_heldout_exact"]/full[s+"_heldout_requests"]-c[s+"_heldout_exact"]/c[s+"_heldout_requests"]>=.50 for s in ("read","generate"))
            c=variants["no_learning"]
            values["learning_required"]=sum(v for k,v in c.items() if k.endswith("_accepted") and k not in ("invalid_texts_accepted",))==0
            checks += [{"fold":fold,"seed":seed,"name":name,"passed":bool(value)} for name,value in values.items()]
    if regressions:
        c=regressions[0]["counts"]
        full_correct=all(c[s+"_"+b+"_exact"]==c[s+"_"+b+"_requests"] for s,b in (("read","seen"),("read","heldout"),("generate","seen"),("generate","heldout"),("roundtrip","other"),("roundtrip","both_heldout")))
        checks.append({"fold":"all","seed":"regression","name":"full_training_regression","passed":full_correct and c["invalid_texts_accepted"]+c["invalid_packets_generated"]==0})
    return checks


def report(output,result):
    result["result_digest"]=digest(result)
    (output/"EVALUATION.json").write_text(json.dumps(result,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    totals={}
    for r in result["results"]:
        counts=totals.setdefault(r["condition"],{k:0 for k in r["counts"]})
        for k,v in r["counts"].items():
            counts[k]+=v
    def ratio(c,key):
        return str(c[key+"_exact"])+"/"+str(c[key+"_requests"])
    lines=["# PLM-L1 v0.4 評価結果","","4種類の語順×肯否の組合せを1つずつ丸ごと学習から除外。各モデルは同じ432対から再学習。", "",
           "| 方式 | 未学習組合せ 読解 | 未学習組合せ 生成単体 | 読解・生成とも未学習組合せ | 既出組合せ 読解/生成 | 誤受理・誤出力 |",
           "|---|---:|---:|---:|---:|---:|"]
    for name,c in totals.items():
        wrong=sum(v for k,v in c.items() if k.endswith("_wrong"))+c["invalid_texts_accepted"]+c["invalid_packets_generated"]
        lines.append(f"| {name} | {ratio(c,'read_heldout')} | {ratio(c,'generate_heldout')} | {ratio(c,'roundtrip_both_heldout')} | {ratio(c,'read_seen')} / {ratio(c,'generate_seen')} | {wrong} |")
    lines += ["",f"受入：{sum(c['passed'] for c in result['checks'])}/{len(result['checks'])}、合格判定：{result['passed']}。", "",
              "partialは学習した部分手掛かりで照合。full_contextは同じ断片分割だが照会の全特徴を必要とする比較。old_ssはv0.2読解器とv0.3生成器を同じ制限データで再学習。no_learningは語彙以外の連想重みを無効化。保留は成功に数えない。",
              "", "## 表引き比較（各foldに1回、符号反復なし）", "", "| fold | 方式 | 未学習 読解 | 未学習 生成 | 未学習 往復 |", "|---|---|---:|---:|---:|"]
    for r in result["references"]:
        c=r["counts"]
        lines.append(f"| {r['fold']} | {r['condition']} | {ratio(c,'read_heldout')} | {ratio(c,'generate_heldout')} | {ratio(c,'roundtrip_both_heldout')} |")
    lines += ["", "部分手掛かりを使う表引きも同じ自動特徴選択と断片分割を使う。数値符号は用いない。この比較は分解と共有の寄与を区別するためで、SSの速度・容量・省電力優位性を示すものではない。", "",
              "## 低次元ストレス（非合否）", "", "| seed | 次元 | 未学習 読解 | 未学習 生成 | 未学習 往復 | 誤受理・誤出力 |", "|---|---:|---:|---:|---:|---:|"]
    for r in result["stress"]:
        c=r["counts"]
        wrong=sum(v for k,v in c.items() if k.endswith("_wrong"))+c["invalid_texts_accepted"]+c["invalid_packets_generated"]
        lines.append(f"| {r['seed']} | {r['dimension']} | {ratio(c,'read_heldout')} | {ratio(c,'generate_heldout')} | {ratio(c,'roundtrip_both_heldout')} | {wrong} |")
    lines += ["", "## 全学習データでの回帰", ""]
    for r in result["regressions"]:
        c=r["counts"]
        lines.append(f"576対をすべて学習した新方式：読解 {c['read_seen_exact']+c['read_heldout_exact']}/{c['read_seen_requests']+c['read_heldout_requests']}、生成単体 {c['generate_seen_exact']+c['generate_heldout_exact']}/{c['generate_seen_requests']+c['generate_heldout_requests']}。このモデルを組合せ除外試験には用いていない。")
    lines += ["", "## 主張の境界", "", "評価には既存192文を再利用する。各foldで未学習組合せ48、既出組合せ144。4fold×4符号の反復であり、独立した新規自然文コーパスではない。語・語義・構文要素は既知で、初めてなのはそのモデルの学習から除いた語順×肯否の組合せ。",
              "", "手設計の分解は『内容語の役割順序＋その間のmarker列』。依存特徴の選択は通常の情報利得による分類処理で学び、学習された対応を位相連想記憶に保存・相関照合する。全学習処理のSS化や構文部品の無制約な発見ではない。",
              "", "v0.3の次語自己回帰から、学習した役割順序と記号列部品を組み立てる生成へ変更した。記号列部品には語尾と句点をまとめた断片も含まれる。任意の階層・新語義・長文・自由作文は対象外。",
              "", "読解と生成は共通の断片記憶を利用するため、往復だけで評価せず、各単体を別実装の限定文法で採点する。原文や正解意味を生成側へ渡すのは禁じるが、生成単体試験は定義上正解意味を入力する。",
              "", "今回の部分照合は文脈特徴の射影。P1の観測数値成分マスク/干渉除去の統合ではない。Phase/VSA領域であり、S1の明示チップ同期統合・R1推論開放・Concept更新は行っていない。", "",
              f"結果digest：`{result['result_digest']}`",f"ソース固定digest：`{result['freeze_hash']}`",""]
    (output/"EVALUATION_REPORT.md").write_text("\n".join(lines),encoding="utf-8")


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--out",required=True)
    parser.add_argument("--development",action="store_true")
    args=parser.parse_args()
    output=Path(args.out)
    if output.exists():
        raise ValueError("fresh output required")
    freeze="development_not_frozen" if args.development else verify_freeze()
    protocol=json.loads((ROOT/"evaluation"/"PROTOCOL.json").read_text(encoding="utf-8"))
    output.mkdir(parents=True)
    split="development" if args.development else "evaluation"
    seeds=protocol["development_seeds"] if args.development else protocol["evaluation_seeds"]
    results=[]
    for fold in protocol["folds"]:
        for seed in seeds:
            for condition in protocol["conditions"]:
                row,model=one(seed,fold,condition,protocol["dimension"],split)
                results.append(row)
                print(json.dumps({"fold":fold,"seed":seed,"condition":condition,"counts":row["counts"]}),flush=True)
                if fold==protocol["folds"][0] and seed==seeds[0] and condition=="partial":
                    model.save(output/"model")
    references=[]
    for fold in protocol["folds"]:
        for name,cls in (("partial_table",PartialTable),("old_whole_table",OldTable)):
            r=assess(cls(train_for(fold),data("lexicon")),split,fold,numeric=False)
            r.update(fold=fold,condition=name)
            references.append(r)
    stress=[]
    if not args.development:
        for seed in protocol["stress_seeds"]:
            for dimension in protocol["stress_dimensions"]:
                r,_=one(seed,protocol["folds"][0],"partial",dimension,split)
                stress.append(r)
                print(json.dumps({"stress":seed,"dimension":dimension,"counts":r["counts"]}),flush=True)
    regressions=[]
    model=fit(data("train"),data("lexicon"),seed="parts-full-regression-0")
    regressions.append(assess(model,split,protocol["folds"][0]))
    checks=[] if args.development else judge(results,protocol,regressions)
    result={"schema":"plm-l1-v04-results-v1","freeze_hash":freeze,"results":results,"references":references,"stress":stress,"regressions":regressions,
            "checks":checks,"passed":bool(checks) and all(c["passed"] for c in checks)}
    report(output,result)
    print("RESULT_DIGEST "+result["result_digest"],flush=True)
    return 0 if args.development or result["passed"] else 1


if __name__=="__main__":
    raise SystemExit(main())
