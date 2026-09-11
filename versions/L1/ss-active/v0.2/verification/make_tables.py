"""Generate factual report tables from frozen-evaluation outputs, not hand-entered values."""
import json,statistics,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from evaluation.integrity import write
s=json.loads((ROOT/'verification/SUMMARY.json').read_text(encoding='utf-8'))
labels={'random_once':'無作為','ambiguity_once':'曖昧さのみ','mixed_once':'探索併用','ambiguity_revisit':'曖昧さ＋再確認','mixed_revisit':'探索＋再確認'}
def row(world,arm,stage='post_E',size=128):return next(r for r in s['rows'] if (r['size'],r['world'],r['strategy'],r['checkpoint'])==(size,world,arm,stage))
lines=[];checked=[]
def heading(text,columns):lines.extend(['',text,'','|'+'|'.join(columns)+'|','|'+'|'.join(['---']*len(columns))+'|'])
def record(values):
    line='|'+'|'.join(map(str,values))+'|';lines.append(line);checked.append(line)
heading('高負荷・固定世界、E学習後',['方式','暫定正解','受理正解','誤受理','保留','未登録誤受理'])
c=next(r for r in s['no_acquisition_controls'] if (r['size'],r['world'],r['checkpoint'])==(128,'stationary','post_E'))['metrics']['groups'];g=c['old_all']
record(['追加教師なし',*[g[k] for k in ('tentative_correct','accepted_correct','accepted_wrong','accepted_abstained')],c['never_taught']['unseen_false_accept']])
for arm,label in labels.items():
    r=row('stationary',arm);g=r['metrics']['groups']['old_all'];record([label,*[g[k] for k in ('tentative_correct','accepted_correct','accepted_wrong','accepted_abstained')],r['metrics']['groups']['never_taught']['unseen_false_accept']])
heading('高負荷・変更世界、E学習後',['方式','変更項目の発見','受理正解','誤受理','変更項目の暫定正解','未登録誤受理','再確認件数'])
c=next(r for r in s['no_acquisition_controls'] if (r['size'],r['world'],r['checkpoint'])==(128,'changed_pool16','post_E'))['metrics']['groups'];g=c['old_all']
record(['追加教師なし',0,g['accepted_correct'],g['accepted_wrong'],c['changed_pool']['tentative_correct'],c['never_taught']['unseen_false_accept'],0])
for arm,label in labels.items():
    r=row('changed_pool16',arm);gs=r['metrics']['groups'];record([label,r['selection']['changed_keys_selected_unique'],gs['old_all']['accepted_correct'],gs['old_all']['accepted_wrong'],gs['changed_pool']['tentative_correct'],gs['never_taught']['unseen_false_accept'],r['selection']['revisit_teachers']])
heading('高負荷、最初の16件で訂正した集合の保持',['世界','方式','初回訂正数','D後の正解','教師32件時の正解','E後の正解','D後再発からE後に回復'])
for world,jworld in (('stationary','固定'),('changed_pool16','変更')):
    for arm,label in labels.items():
        a=row(world,arm,'q16')['metrics']['groups']['first_block_corrected'];d=row(world,arm,'post_D')['metrics']['groups']['first_block_corrected'];q=row(world,arm,'q32')['metrics']['groups']['first_block_corrected'];e=row(world,arm)['metrics']['groups']
        record([jworld,label,a['requests'],d['tentative_correct'],q['tentative_correct'],e['first_block_corrected']['tentative_correct'],e['post_D_relapsed_first_block']['tentative_correct']])
heading('高負荷・固定世界、直接教え直していない旧記憶',['方式','教師32件時の受理正解','E後の受理正解'])
for arm,label in labels.items():record([label,*[row('stationary',arm,stage)['metrics']['groups']['protected_old']['accepted_correct'] for stage in ('q32','post_E')]])
heading('低負荷、E学習後',['世界','方式','受理正解','誤受理','未登録誤受理','再確認件数'])
for world,jworld in (('stationary','固定'),('changed_pool16','変更')):
    for arm,label in labels.items():
        r=row(world,arm,size=64);g=r['metrics']['groups'];record([jworld,label,g['old_all']['accepted_correct'],g['old_all']['accepted_wrong'],g['never_taught']['unseen_false_accept'],r['selection']['revisit_teachers']])
heading('高負荷・代表条件での中央値、3回ずつ',['方式','32件の選択','32件の回答検証・更新','D/E背景学習'])
bench=json.loads((ROOT/'verification/BENCHMARK.json').read_text(encoding='utf-8'))['rows']
for arm,label in labels.items():
    b=[r for r in bench if r['strategy']==arm];record([label,*[f"{statistics.median(r['times'][key] for r in b):.3f}秒" for key in ('selection_seconds','response_seconds_including_revalidation','background_seconds')]])
with (ROOT/'verification/TABLES.md').open('x',encoding='utf-8') as f:f.write('\n'.join(lines)+'\n')
write(ROOT/'verification/TABLE_ROWS.json',checked);print('\n'.join(lines))
