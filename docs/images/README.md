# README 截圖

2026-10-29，以目前程式在 macOS 離線預覽中擷取；Windows 的視窗裝飾與字型可能不同。

| 圖片 | 示範內容 | RP 來源 |
| --- | --- | --- |
| `opponent-elo.png` | 對手目前 Elo、文明特性 | [516908358](https://www.aoe2insights.com/match/516908358/) |
| `opening.png` | 羅馬前期流程、最近對局 | [516908358](https://www.aoe2insights.com/match/516908358/) |
| `roman-reference.png` | 羅馬主線與分支入口 | [516908358](https://www.aoe2insights.com/match/516908358/) |
| `arena-reference.png` | 勃根地競技場、四 TC 與帝王準備 | [516700174](https://www.aoe2insights.com/match/516700174/) |

玩家、文明與地圖由已下載 RP 的檔頭載入，流程和戰術卡使用內建資料。這些是工具介面截圖，不是遊戲播放畫面或自動復盤結果；RP 本體未納入儲存庫。

更新時使用含 Tk 的 Python 啟動介面，載入同場 RP、切換對應流程／速查，確認文字未截斷後再擷取視窗。一般離線展示可執行 `python opponent-civ/dashboard.py --demo`，但該模式預設使用虛構對局，不能當成上述 RP 的替代資料。

`dashboard.png`、`counters.png` 為舊版介面截圖，首頁已不再使用。

對手資訊圖的 Elo 由官方排行榜 API 於截圖時查得，非當場歷史積分。文明文字透過正式 `load_civs` 讀取本機遊戲繁中檔案，包含缺少說明 ID 的新版索引格式。
