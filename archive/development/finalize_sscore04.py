"""Create the final report/archive, then test the actual extracted archive."""
import hashlib,json,os,re,shutil,subprocess,sys,tempfile,zipfile
from pathlib import Path
BASE=Path(__file__).resolve().parents[1]
ROOT=BASE/'outputs/PLM-L1-SS-core-v0.4'
sys.path.insert(0,str(ROOT))
from evaluation.integrity import read,write,sha
from evaluation.verify04 import verify,preserve,manifest
from evaluation.reproduce04 import cold

def main():
    verify();s=read(ROOT/'results/run1/SUMMARY-all.json');rep=read(ROOT/'verification/REPRODUCTION04.json')
    assert s['main']['correct']==80 and s['main']['wrong_text']==s['main']['held']==0
    assert s['main']['regression_text_equal']==48
    u=s['updates'];assert u['updated']==u['target_retained']==u['correct_generated']==u['correct_reload_generated']==12 and u['non_targets_equal']==132
    p=s['partial'];assert p['held_before']==p['correct_after']==p['states_retained']==4 and p['non_targets_equal']==44
    assert s['faults']['requests']==s['faults']['expected_response']==10 and s['faults']['wrong_text']==0
    assert rep['cold']['passed'] and all(rep['rebuild'].values())
    preservation=preserve();write(ROOT/'verification/PRESERVATION04.json',preservation)
    rows=read(ROOT/'results/run1/MAIN.json');updates=read(ROOT/'results/run1/UPDATES.json')
    sample=next(r for r in updates if r['target']=='event:1/subject')
    index=read(ROOT/'bundle04/IO.json')['addresses'].index(sample['target'])
    cold_input=ROOT/'verification/COLD_UPDATED_INPUT';cold_input.mkdir(exist_ok=False)
    shutil.copytree(ROOT/f'results/run1/shards/updates-{index}/updates/wm-{index}',cold_input/'wm')
    shutil.copy2(ROOT/'results/run1/cold/controls.npz',cold_input/'controls.npz')
    write(cold_input/'EXPECTED.json',{'text':sample['reload_result']['text']})
    cold_updated=cold(cold_input);write(ROOT/'verification/COLD_UPDATED04.json',cold_updated)
    assert cold_updated['passed']
    first=next(r for r in rows if r['case']=='evaluation/1' and r['style']==0)
    second=next(r for r in rows if r['case']=='evaluation/1' and r['style']==1)
    initial=read(ROOT/'verification/FREEZE04-initial.json')['files'];final=read(ROOT/'verification/FREEZE04.json')
    changed=[k for k in sorted(set(initial)|set(final['files'])) if initial.get(k)!=final['files'].get(k)]
    assert changed==['evaluation/experiment04.py','evaluation/parallel04.py','evaluation/reproduce04.py']
    maincost=s['main'];baseline=read(ROOT/'data/V03_MAIN.json');old=[r for r in baseline if r['method']=='integrated']
    regression=[r for r in rows if r['case'].startswith('evaluation/')]
    oldticks=sum(r['result']['cost']['ticks'] for r in old)
    newticks=sum(r['result']['cost']['ticks'] for r in regression)
    parallel=read(ROOT/'results/PARALLEL.json')
    report=f'''# PLM-L1-SS-core v0.4 実施報告

## 結論

限定された二事象の言語範囲で、**SS意味ワーキングメモリ→役割参照→局所訂正→生成を、意味辞書への復元なしで接続**した。80生成は全件正しく、12種類の訂正で対象の更新と非対象保持を確認した。旧読解器や汎用制御のSS化は未完であり、「ほぼ全SS」の完成ではない。

## 実測結果

|評価|結果|意味する範囲|
|---|---:|---|
|単体・回帰試験|95 / 95|新規20、従来75。異常系と旧bridgeも含む|
|既存24文×2様式|48 / 48 正しく生成|保存済みv0.3出力とも全件文字列一致|
|状態組合せ16文×2様式|32 / 32 正しく生成|二事象の肯否×法の4×4を被覆|
|主評価の誤生成 / 保留|0 / 0|有限80要求に限った観測|
|独立局所訂正|12 / 12 成功|10役割＋時間関係＋提示順|
|非対象項目の保持|132 / 132|各訂正について残る11項目|
|訂正後の生成 / 保存再ロード後の生成|12 / 12、12 / 12|意味と表層形式を別パーサで採点|
|未観測・読取不能・複数候補・競合|4 / 4 保持して保留|教師後4 / 4正しく生成、非対象44 / 44保持|
|障害/位相/誤教師の期待応答|10 / 10|9条件で保留、位相回転1条件で正しく生成|
|2回の実行結果|{rep['repeat']['identical_files_excluding_timing']}ファイル一致|時間計測以外の個票・窓ログ・保存信号等|
|数値束のオフライン再構築|4 / 4ファイル指紋一致|重み・公開基底・教師報告を再生成|
|最小配置の別プロセス生成|更新前/更新後2ケース成功|旧言語モデル/読解器/生成器/評価器/IO.jsonなし|

採点、各文章、訂正対象、保留理由、窓ログは `results/run1` と `results/run2` に収録した。集計は `SUMMARY-all.json`、原記録は `shards/`。生成器へ正解意味・正解文章を渡していない。独立採点器も限定言語仕様に基づくもので、人間による一般日本語の理解評価ではない。

## 実際に生成できた文章

入力：

> {first['input']}

提示順を保ち、両文を主語先行で生成：

> {first['result']['text']}

提示順を逆転し、第1文を目的語先行に生成：

> {second['result']['text']}

否定・仮定・人物の役割・時間関係を保ったまま出力形式を変えている。これは限定語彙と学習済み構文部品の生成であり、自由な長文作文ではない。

局所訂正の別例。入力：

> {sample['before_input']}

外部教師 `{sample['target']} = {sample['teacher']}` を信号化して与えると：

> {sample['result']['text']}

対象以外の11項目を保持。保存した数値WMを読み直して逆順生成すると：

> {sample['reload_result']['text']}

## 今回の実装上の進歩

- WMは意味内容と状態の2重畳信号だけを保持する。役割ごとの値辞書に置き換えただけではない。
- 役割は位相信号のオペランドとして渡り、事象信号と結合してWMを参照する。
- 訂正は対象アドレスで旧候補信号和を引き、新教師信号を足す。全体整合と非対象11項目を再照合してから返す。
- 生成操作とオペランドの対応もSS記憶で回収し、値信号を語彙/時間接続の表層信号に接続する。文字列化は出力端に限定する。
- `revise_and_generate` は訂正拒否時に文章を返さない。未確定状態を勝手に単一値へ確定しない。

ただし新しい生コーパスから文法や訂正判断を学習したわけではない。旧生成プログラムを再利用し、52の符号対応と45のドメイン対応を加算学習した。新たな接続層の学習量は794,624チップ加算。

## 計算量とサイズ

主評価80生成の、新WMから文字出力までの合計：

- 受信窓：{maincost['generation_windows']:,}
- 受信tick：{maincost['generation_ticks']:,}
- 候補×チャネル×ペイロードtickの積：{maincost['generation_products']:,}
- 読解側は40文を各1回実行し、別途{maincost['reader_ticks_once_per_document']:,}tick。2出力間で数値Packetを共有した。
- 局所更新の書込みtick合計：{u['write_ticks']:,}。各訂正試行の計測区間（更新開始から診断・保存再ロード後生成まで）の受信tickは{u['total_ticks_including_external_diagnostics']:,}。入力読解と初期診断はこの区間外。

WM本体は262,144 bytes。公開基底・旧プログラム重み・新対応重みを含む数値束は非圧縮配列で27,394,048 bytes。うち新規対応/ドメイン学習重みは1,310,720 bytes。

回帰48生成について、新版の生成部分だけで{newticks:,}tick、旧v0.3の保存済み読解＋生成では{oldticks:,}tickだった。処理境界が違うため速度倍率としては比較しないが、今回の直結と再検査には大きな追加計算がある。高速化・省メモリ化・性能上の優越性を主張しない。

最終評価は8ワーカープロセス、{parallel['jobs']}独立ジョブ、壁時計{parallel['seconds']:.3f}秒。Pythonのシミュレーション時間であり、専用回路の性能指標ではない。1tickはCPUの1命令ではない。

受信tickや候補積の件数はEngineの相関窓を集計したもの。信号の生成/結合、ファイル処理、文字列連結等を含む全計算のFLOP数ではない。

## 変更固定と再現

最終固定指紋：`{final['digest']}`（{len(final['files'])}ファイル）。旧v0.3の348ファイル、ZIP、コピーした140ファイルの不変を確認した。

初回固定後にはWindows隔離実行のUTF-8指定と、独立評価事例の並列配置という2件の実行基盤変更があった。変更ファイルは評価ヘルパー3つのみ。数値ランタイム・重み・データ・閾値・採点規約は不変。旧指紋/旧ソース/中断ログを残し、最終評価は最初から2回実施した。途中の評価を成績の分母へ追加していない。詳細は `verification/AMENDMENT04*.json` と `CORPUS.md`。

## 残っている課題

1. 入力側の文字処理・構造組立てには旧来の記号処理が残る。読解器内の意味辞書まで消したわけではない。
2. opcode実行、保留閾値、固定文脈ポート、停止規則、入出力符号帳は設計した通常処理である。
3. 新WMは2事象・12項目に限定。多数事象、長期連続更新、可変容量、未知語、一般照応、自由作文は未評価。
4. 不確実な意味は保持するが、不明部分を明示した部分文章の生成は行わず保留する。教師は外部指定。
5. 数値整合は事実の正しさを認証しない。ドメイン内の誤教師や共通原因の整合的誤りは防げない。
6. 一体APIは拒否した訂正に対して古い文章を返さないが、永続的な訂正待ちワークフローや物理書込みACKは新WMの実装範囲外。
7. 既存の逐次I/Q相関・パイロットを使うが、新WM全体を物理搬送して周波数探索/復調した実証ではない。

次の優先候補は、入力側の「役割割当て→新WMへの書込み」を意味辞書を介さず接続する小さな実証である。その後、通常の制御に残る処理選択・保留・停止のどこをSS状態遷移として学習させるかを切り分ける。今回の結果だけで「ほぼ全SS」や一般言語理解の達成とは判断しない。
'''
    with (ROOT/'REPORT.md').open('x',encoding='utf-8') as f:f.write(report)
    verify();count=manifest();archive=ROOT.with_name(ROOT.name+'.zip')
    with zipfile.ZipFile(archive,'x',compression=zipfile.ZIP_DEFLATED,compresslevel=6) as z:
        for path in sorted(ROOT.rglob('*')):
            if path.is_file():
                assert '__pycache__' not in path.parts;z.write(path,ROOT.name+'/'+path.relative_to(ROOT).as_posix())
    archive_sha=sha(archive);extract=Path(tempfile.mkdtemp(prefix='sscore04-zipcheck-',dir=BASE/'work'))
    with zipfile.ZipFile(archive) as z:
        assert z.testzip() is None
        for name in z.namelist():
            target=(extract/name).resolve();assert target.is_relative_to(extract.resolve())
        z.extractall(extract)
    extracted=extract/ROOT.name
    env={**os.environ,'OPENBLAS_NUM_THREADS':'1','PYTHONIOENCODING':'utf-8','PYTHONDONTWRITEBYTECODE':'1'}
    checks={}
    for mode in ('verify','check-manifest'):
        r=subprocess.run([sys.executable,'-X','utf8','-B','-m','evaluation.verify04',mode],cwd=extracted,env=env,capture_output=True,text=True,encoding='utf-8',check=True);checks[mode]=r.stdout.strip()
    print(json.dumps({'archive_created':str(archive),'zip_sha256':archive_sha,'files':count+1,'extraction':str(extracted),'checks':checks}),flush=True)
    test=subprocess.run([sys.executable,'-X','utf8','-B','-m','unittest','discover','-s','tests','-v'],cwd=extracted,env=env,capture_output=True,text=True,encoding='utf-8')
    logfile=archive.with_name(ROOT.name+'-POSTZIP-TESTS.log');logfile.write_text(test.stdout+test.stderr,encoding='utf-8')
    assert test.returncode==0 and 'Ran 95 tests' in test.stderr and '\nOK\n' in test.stderr,test.stderr[-3000:]
    for mode in ('verify','check-manifest'):
        subprocess.run([sys.executable,'-X','utf8','-B','-m','evaluation.verify04',mode],cwd=extracted,env=env,capture_output=True,text=True,encoding='utf-8',check=True)
    assert sha(archive)==archive_sha
    post={'zip':str(archive),'zip_sha256':archive_sha,'zip_bytes':archive.stat().st_size,'archive_files':count+1,'extracted_tests':95,
          'extracted_manifest_checked_before_and_after':True,'freeze':final['digest'],'test_log':str(logfile),'previous':preserve()}
    write(archive.with_name(ROOT.name+'-POSTZIP.json'),post)
    note=archive.with_name(ROOT.name+'-VERIFICATION.md')
    note.write_text(f"# PLM-L1-SS-core v0.4 最終梱包検証\n\n全{count+1}ファイルをZIP化し、実際に別フォルダへ展開して95試験を全通過。展開後の指紋検査を試験前後に実施。\n\n- ZIPサイズ：{archive.stat().st_size:,} bytes\n- ZIP SHA256：`{archive_sha}`\n- 最終ソース指紋：`{final['digest']}`\n- 2回の評価：時間計測を除く{rep['repeat']['identical_files_excluding_timing']}ファイルが一致\n- 旧v0.3：348ファイルとZIPが不変\n\n詳細：同じ場所のPOSTZIP.jsonとPOSTZIP-TESTS.log。ZIP内部のREPORT.md、SPECIFICATION.md、BOUNDARY_AUDIT.mdを参照してください。\n",encoding='utf-8')
    print(json.dumps(post,ensure_ascii=False),flush=True)

if __name__=='__main__':main()
