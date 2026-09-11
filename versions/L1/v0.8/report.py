"""Human-readable summary derived only from the saved numerical records."""
from collections import defaultdict


def render(result):
    lines=['# PLM-L1 v0.8 評価結果\n','## 二事象・時間関係・指定提示順の完全一致\n',
           '|方式|読解|直接生成|読解→生成|\n|---|---:|---:|---:|\n']
    for mode in ('bound','partitioned'):
        rows=[r for r in result['standard'] if r['mode']==mode]
        values=[]
        for stage in ('read','generate','roundtrip'):
            values.append(str(sum(r['counts'][stage]['exact'] for r in rows))+'/'+str(sum(r['counts'][stage]['requests'] for r in rows)))
        lines.append('|'+mode+'|'+'|'.join(values)+'|\n')
    lines+=['\n同じ制御文法の反復であり、件数は独立自然文の種類数ではない。生成の成功には両事象の全スロット、相対時間関係、指定提示順と各文内語順が必要。\n',
            '\n## 低次元・方向を消した対照\n\n|D|方式|正答|誤答|保留|前後反転で同じ信号|\n|---:|---|---:|---:|---:|---:|\n']
    groups=defaultdict(list)
    for r in result['codec']: groups[(r['dimension'],r['mode'])].append(r)
    for (d,mode),rows in sorted(groups.items()):
        c={k:sum(r['counts'][k] for r in rows) for k in ('requests','exact','wrong','abstained')}
        rr=[x for r in rows for x in r['records'] if x['reversed_edge_same_signal'] is not None]
        lines.append(f"|{d}|{mode}|{c['exact']}/{c['requests']}|{c['wrong']}|{c['abstained']}|{sum(x['reversed_edge_same_signal'] for x in rr)}/{len(rr)}|\n")
    lines+=['\n比較予算は数値係数Dと期待平均エネルギー。候補基底・メタデータ・全RAM・速度の同一予算ではない。partitionedも位相コードを使用する。\n',
            '\n## codec単体への相対L2雑音\n\n|D|雑音比|正答|誤答|保留|\n|---:|---:|---:|---:|---:|\n']
    groups=defaultdict(list)
    for r in result['noise']: groups[(r['dimension'],r['level'])].append(r)
    for (d,level),rows in sorted(groups.items()):
        c={k:sum(r['counts'][k] for r in rows) for k in ('requests','exact','wrong','abstained')}
        lines.append(f"|{d}|{level}|{c['exact']}/{c['requests']}|{c['wrong']}|{c['abstained']}|\n")
    lines+=['\n評価意味から直接符号化した信号の診断。読解→通信→生成、P1部分観測、S1同期の試験ではない。\n',
            '\n## 学習対応の対照\n\n|対照|読解の対応一致|生成の対応一致|想定した保留を含む条件適合|\n|---|---:|---:|---:|\n']
    for name,row in result['learning_controls'].items():
        if name=='relation_table_reference': continue
        c=row['counts']; good=sum((not r['accepted']) if r['expected_abstain'] else r['exact'] for r in row['records'])
        lines.append(f"|{name}|{c['read']['exact']}/{c['read']['requests']}|{c['generate']['exact']}/{c['generate']['requests']}|{good}/{len(row['records'])}|\n")
    reference=result['learning_controls']['relation_table_reference']
    n=len(reference['records'])
    lines.append(f"\n通常表の関係照合参考：読解{sum(r['read_exact'] for r in reference['records'])}/{n}、書き方{sum(r['write_exact'] for r in reference['records'])}/{n}。六キーずつの関係対応だけの比較で、全言語系・同一RAM/速度比較ではない。\n")
    lines+=['\n教師反転の正答は反転後の教師に対する一致であり、通常の日本語正答ではない。無学習／未学習の向きは保留を期待する。既知marker在庫で未知表現を拒否する通常処理も含む。\n',
            f"\n固定受入：{sum(c['passed'] for c in result['checks'])}/{len(result['checks'])}。開発実行には固定評価の合否を付けない。\n",
            '\n## 未実現\n\n時間表現とグラフの六対応ずつを学ぶ限定実証。境界・スキーマ・特徴キー・位相結合は手設計。二事象の同一性はパケット内の局所IDで、クロス文書照応ではない。否定・仮定の記述を現実の生起へ昇格させない。因果、条件付き関係論理、未知語、三事象以上、記憶偏り改善、全SS学習、P1/S1接続、R1推論・Concept更新は行わない。\n']
    return ''.join(lines)
