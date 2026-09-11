# P1数値仕様 v0.1

## 符号の定義

各キーkに対してD成分の単位複素位相コードを割り当てます。

`v_k[j] = exp(i * theta_k[j])`

SHAKE256の固定バイト列をリトルエンディアンuint64に読み、上位53bitを[0,1)へ写し、2π倍してtheta（radian）を得ます。キーはalgorithm・seed・namespace・identifierのcanonical JSON（UTF-8）。Pythonのhash()や実行順に依存しません。

namespaceはevent/role/symbol。symbolにはkind・scope・idがあります。entityとclauseのscopeは文書ID、predicate/state/conceptは通常global。Concept名DOGが同じでも、個体AとBのコードは異なります。コード次元は128〜16384の64の倍数。異なる次元の同じキーは共通接頭部分を持ちます。

実数/虚数の浮動小数演算はNumPyを使います。同環境での再現と浮動小数許容誤差を検証しますが、異なる数値ライブラリ/CPU間の全ビット一致を保証するものではありません。

## 結合と重畳

eを文書で修飾された出来事ID、rを役割、xを値とします。各成分の複素乗算を⊙で表すと、

`binding(e,r,x) = event(e) ⊙ role(r) ⊙ value(x)`

`memory = Σ binding(e,r,x)`

です。単位化や平均化はせず、各結合の重みは1です。memory自体は単位複素ベクトルではありません。和の順序を固定して、入力フレーム順/辞書順への依存をなくします。

役割コードが異なるのでsubject=A,object=Bとsubject=B,object=Aが区別されます。出来事コードは複数出来事の役割値の取り違えを抑えるために使います。役割または出来事結合を外す比較では、対応を交換しても全く同じ信号になる反例を検査します。

利用可能な役割はsubject/object/predicate/polarity/modality/semantic_status/applied/target_clause。複数の値を同じ出来事・役割へ暗黙登録することはせず、同じ文書・出来事IDの重複フレームは拒否します。

否定は「肯定コードにマイナスを掛ける」実装ではなく、polarity:negativeという別値を符号化します。仮定・隔離・appliedも専用の状態役割を持ちます。いずれも事実採用を意味しません。

## 部分相関と判定

観測できた成分の集合をMとし、既知の出来事・役割と候補xに対して

`score(x) = Re(mean(memory[j] * conj(event(e)[j] * role(r)[j] * value(x)[j]), j in M))`

を計算します。単一結合・雑音なしなら正解の値は1。他成分の重畳は干渉として残ります。このscoreは[-1,1]に制限されたcosineでもPearson係数でもなく、整合フィルタの振幅です。確率ではありません。

観測成分64未満は保留。最大score≥0.65、かつ最大scoreとmax(第2位score,0)の差≥0.20なら数値回復とします。0は「その照会先に成分が存在しない」という基準です。候補1件でも0との差を検査します。

正解が候補集合にある保証はありません。負例試験を行いますが、干渉によって閾値を越える誤受理は起こり得ます。常に保留できる安全性は保証しません。

## 人工チャネル

PCG64を明示したNumPy乱数生成器で観測座標を選びます。keep_fractionで指定した成分数を残し、他は0としてmask=falseを付けます。0という観測値と欠測は別です。

各成分に共通のphase_offsetと独立の正規分布位相揺らぎjitter_stdを加えます。さらに実部/虚部それぞれ標準偏差noise_std/√2の独立正規雑音を加えます。noise_stdは複素雑音のRMSで、memory全体に対してSNRを正規化した値ではありません。

phase_offsetなどの真値は評価器だけが知ります。復号器には渡しません。P1には位相同期推定器がなく、共通90度回転は回復失敗側の試験になります。既知の回転を逆に掛ける単体試験は代数確認であり、自動同期の実装ではありません。

## 入力と復号の分離

評価器は原フレームを保持して比較しますが、decode関数はsamples/codebook/query/candidates/maskだけを受け取り、フレーム・正解・metadataを参照しません。出来事IDと候補辞書は既知のサイド情報です。コードからそれらを発見したと主張しません。

P1の候補辞書では各symbolに独立コードを使います。Concept階層に応じた共有成分、意味的類似度の自動形成、学習による符号設計は別の実験課題です。
