"""Write the user-facing decision from finished measurements, not expectations."""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent / "outputs" / "PLM-L1-v0.4"
result = json.loads((ROOT / "results" / "EVALUATION.json").read_text(encoding="utf-8"))
repro = json.loads((ROOT / "verification" / "REPRODUCIBILITY.json").read_text(encoding="utf-8"))
model = json.loads((ROOT / "results" / "model" / "model.json").read_text(encoding="utf-8"))
assert result["passed"] and repro["status"] == "passed"
totals = {}
for row in result["results"]:
    target = totals.setdefault(row["condition"], {})
    for key, value in row["counts"].items():
        target[key] = target.get(key, 0) + value


def ratio(c, key):
    return f"{c[key + '_exact']}/{c[key + '_requests']}"


def wrong(c):
    return sum(v for k, v in c.items() if k.endswith("_wrong")) + c["invalid_texts_accepted"] + c["invalid_packets_generated"]


c = totals["partial"]
lines = [
    "# PLM-L1 v0.4：実施結果と到達点", "", "実施日：2026-09-07", "",
    "## 結論", "",
    "限定された言語範囲で、既知の語順・役割・助詞/語尾部品を、学習から丸ごと外した語順×肯否の組合せへ再利用できました。読解と生成の双方を新しい部品学習方式に変更しています。",
    "", "例えば付属モデルは『対象先行・否定』を一切学習していません。それでも『花子を太郎が助けなかった。』を読み、主体先行の『太郎が花子を助けなかった。』へ生成できます。対象先行のままの生成や仮定形、主客を交換した例も確認しました。原文は生成器へ渡さず、数値意味パケットだけを受け渡します。",
    "", "## 固定評価", "",
    "学習576対のうち、対象とする語順×肯否の144対を除き、432対で再学習。除外セルを入れ替えた4分割×4符号seedです。開発データで実装を検証した後に、ソース・データ・閾値・評価を凍結して実行しました。",
    "", "| 方式 | 未学習組合せの読解 | 未学習組合せの生成単体 | 両側が未学習組合せの往復 | 既出組合せの読解/生成 |", "|---|---:|---:|---:|---:|",
]
for name, row in totals.items():
    lines.append(f"| {name} | {ratio(row, 'read_heldout')} | {ratio(row, 'generate_heldout')} | {ratio(row, 'roundtrip_both_heldout')} | {ratio(row, 'read_seen')} / {ratio(row, 'generate_seen')} |")
lines += [
    "", f"新方式の全往復は {c['roundtrip_other_exact'] + c['roundtrip_both_heldout_exact']}/{c['roundtrip_other_requests'] + c['roundtrip_both_heldout_requests']}。誤った意味の受理・完成文出力は {sum(v for k,v in c.items() if k.endswith('_wrong'))} 件。不正文の受理は {c['invalid_texts_accepted']}/{c['invalid_texts']}、不正パケットからの生成は {c['invalid_packets_generated']}/{c['invalid_packets']} でした。保留は成功に含めません。",
    "", f"事前受入条件は {sum(x['passed'] for x in result['checks'])}/{len(result['checks'])} 合格。機能・旧版回帰テストは {sum(repro['test_counts'].values())} 件（新版46＋v0.3の53＋v0.2の52＋v0.1の47）。全数値評価を2回実行し、結果JSON、結果報告、モデル情報のバイト列と数値重み配列が一致しました。",
    "", "比較のfull_contextは部品分割を同じにして全特徴を必要とする方式、old_ssは旧v0.2読解器とv0.3生成器を同じ432対から再学習した方式です。両者は既出組合せでは動作し、未学習組合せでは保留しました。全学習済みの旧重みを渡した比較ではありません。no_learningは初期語彙だけ残し、それ以外の数値重みを無効にしています。",
    "", "## 何による改善か", "",
    "通常の表引きでも、同じ部分特徴の選択と部品共有を使えば、各分割で未学習組合せの読解・生成・往復がそれぞれ48/48、4分割合計192/192でした。旧来の全文型/prefix表引きはそれぞれ0/192。したがって、改善の根拠は部品の分解と学習した依存関係の共有にあり、SS方式だけの汎化・速度・容量優位性は示していません。",
    "", "v0.3の次語自己回帰から、役割順序とmarker列部品を組み立てる生成へ変えました。分割規約そのものは手設計です。教師は文と意味の対と初期語彙で、手順・語順ラベル・除外セルを学習APIに与えていませんが、語種・語義・意味スロット・一意に対応できる内容語などの前提があります。",
    "", "対応に必要な特徴は、学習時に通常の情報利得による記号・統計処理で選択します。選ばれた対応を位相連想記憶に保存し、実行時は部分キーで相関照合します。特徴値→正解の表や決定木を実行モデルに残してはいませんが、全学習処理をSS化したわけではありません。",
    "", "### 付属モデルが選んだ手掛かり", "", "| 判断 | 学習で残した特徴 |", "|---|---|",
    "| 内容語の役割 | 直後の記号 |",
    "| 肯否 | 述語の後の記号列 |",
    "| 断定形/仮定形 | 先頭の記号列 |",
    "| 出力語順 | 先頭に指定した役割 |",
    "| 助詞・先頭・語尾部品 | 付く役割、必要に応じて仮定・肯否。語順指定への依存は除去 |",
    "", f"付属モデルは {repro['phase_vector_count']} 本の8192次元複素ベクトルを持ち、重み本体は {repro['raw_phase_weights_bytes']:,} バイトです。候補符号・キャッシュ・メタデータ等を含む総メモリではなく、従来版との同一メモリ予算比較でもありません。",
    "", "## 低次元での限界（非合否試験）", "", "| seed | 次元 | 未学習 読解 | 未学習 生成 | 未学習 往復 | 誤受理・誤出力 |", "|---|---:|---:|---:|---:|---:|",
]
for row in result["stress"]:
    s = row["counts"]
    lines.append(f"| {row['seed']} | {row['dimension']} | {ratio(s, 'read_heldout')} | {ratio(s, 'generate_heldout')} | {ratio(s, 'roundtrip_both_heldout')} | {wrong(s)} |")
lines += [
    "", "128次元・parts-stress-0の2件は、既出組合せ『花子が健太を褒めた。』『健太を花子が褒めた。』に対して読解側がreadを返した一方、出力した意味信号を回復するとambiguous_meaningで保留したものです。評価では成功と扱わず、受理後の意味不成立として2件を誤りに数えました。生成側も保留し、誤った完成文は出ていません。読解の受理判定と信号復元可能性の整合が、低次元での残課題です。詳細はSTRESS_FAILURE_AUDIT.json。",
    "この試験は容量適応や未知分布での安全性を証明しません。低次元の失敗も保存し、ソース・閾値・受入条件を事後に変更してはいません。",
    "", "## 再現・分離・保存", "",
    "432文・意味対と初期語彙、新版パッケージだけの環境で再学習し、付属モデルとfingerprintが一致しました。旧版コード・旧教師・旧重み・評価データはこの環境にありません。",
    "読解・学習の実行ファイルを配置しない生成専用環境でも、数値パケットのみの転送で4例が正しい意味と語順を保持しました。共通の数値モデルと特徴補助コードは残ります。読解に関係する知識まで一切消した検査ではありません。",
    "過去のL1 v0.1〜v0.3、P1 v0.2、S1 v0.2のフォルダ/ZIP計948ファイルと、同梱v0.3の143ファイルの保持を確認しました。最終ZIP実展開後の検証結果は配布フォルダ外のPLM-L1-v0.4-VERIFICATION.json/.mdに記録します。",
    "", "## まだ実現していないこと", "",
    "評価の元192文は既存版からの再利用です。48要求×4分割×4符号の768は768種類の新規自然文を意味しません。未学習とは当該432対で再学習したモデルから除外した組合せという意味で、未知語義・未知構文・任意の構文階層への一般化ではありません。",
    "初期の6人・4動詞、2語順、肯否×断定形/仮定形、1出来事、最大9トークンの範囲です。仮定形は後件のない実験用の条件節です。長文理解、複数出来事、照応、自由作文は未実装です。",
    "今回の部分照合は文脈特徴の射影であり、P1の数値観測成分マスク・干渉除去との統合ではありません。Phase/VSA領域での実証で、S1の明示チップ列・同期受信器は未接続です。R1推論やConcept更新も開放していません。",
    "", "## 次に検討する範囲", "",
    "まず低次元で見つかった『読解の受理と意味信号の復元可能性』の判定不整合を解消し、干渉増加時の保留を検証する必要があります。そのうえで、複数出来事を別々の役割束として保持し、主客や否定を混線させずに読み書きできるかへ広げる案があります。本版では次段階の実装は行っていません。",
    "", "## 再現用識別子", "",
    f"- source freeze：`{result['freeze_hash']}`",
    f"- result digest：`{result['result_digest']}`",
    f"- primary model：`{model['fingerprint']}`",
    "", "起動方法はREADME.md、全件の記録はEVALUATION.json、学習分割はdata/SPLIT_AUDIT.json、再実行の一致確認はverification/REPRODUCIBILITY.jsonを参照してください。", "",
]
with (ROOT / "results" / "RELEASE_DECISION.md").open("x", encoding="utf-8") as stream:
    stream.write("\n".join(lines))
print(json.dumps({"report": str(ROOT / "results" / "RELEASE_DECISION.md"), "result_digest": result["result_digest"]}))
