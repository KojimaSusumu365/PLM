# S1チップ列デモ

TX_CHIPS.jsonに8480個の明示的な複素チップを保存。RECEIVED_CHIP_PACKET.jsonはその25%を観測した信号だけで、真の遅延・位相・周波数や元のslot割当てを含みません。

DESPREAD_VALUES.jsonに逆拡散後の2048成分と観測マスクを保存しています。チャネル真値は別の評価者用ファイルです。

BUDGET_AND_SPECTRUM_CONTROLS.jsonは総エネルギー・時間・離散DFTの帯域外成分比・全チップ観測時の雑音分散倍率を比較します。実RF帯域や処理利得の測定ではありません。
