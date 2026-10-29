# 開發與進階使用

一般使用者請到 [首頁下載 EXE](../README.md)。原始碼使用 Python 3.12 與標準函式庫，打包才需要 PyInstaller。

## 執行

從此資料夾執行 `python dashboard.py`，首次啟動會顯示設定。支援：

| 參數 | 用途 |
| --- | --- |
| `--setup` | 啟動前重新開啟設定 |
| `--with-game` | 先開工具，再透過 Steam 啟動遊戲 |
| `--no-elo` | 關閉連網積分查詢 |
| `--game-dir PATH` | 覆寫遊戲安裝位置 |
| `--dir PATH` | 覆寫錄影資料夾，可重複指定 |
| `--profile-id N` | 覆寫自己的玩家 ID |
| `--lang tw` | 資料語言：tw 繁中、en 英文、zh 簡中；介面仍以繁中為主 |
| `--demo` | 虛構範例畫面，不監看錄影、不連網；無遊戲安裝也能預覽內建流程 |

設定與視窗位置分別保存在 `%LOCALAPPDATA%\aoe2-tools\opponent-civ\settings.json` 與 `window.json`。首次嘗試放在副螢幕，之後記住視窗位置；只要有第二個螢幕，就不會開在遊戲所在的主螢幕上，即使上次是在只有一個螢幕時關掉的。不要將本機設定或錄影加入版本控制。

終端機版可執行 `python watch.py`，其設定透過參數指定，不讀取 GUI 設定。紀錄寫入上述 LOCALAPPDATA 資料夾的 `watch_log.jsonl`。

## 驗證與打包

在 repository 根目錄執行：

```powershell
python -m unittest discover -s opponent-civ -p "test_*.py" -v
python -m pip install pyinstaller==6.22.3
python opponent-civ/build_exe.py
```

產物為 `opponent-civ/build/release/aoe2-opponent-dashboard.exe` 與 `SHA256SUMS.txt`。打包使用自製圖示，不需要安裝遊戲。加上 `--desktop` 才會另外複製 EXE 到本機桌面。

推送 `v*` tag 會觸發 GitHub Actions：測試 → Windows x64 打包 → 建立 Release。也可手動執行 workflow 取得測試產物；手動執行不會建立 Release。

## 主要模組

| 檔案 | 功能 |
| --- | --- |
| `dashboard.py` | 深色介面、歷史對局、背景積分查詢 |
| `settings.py` | 首次設定、本機設定保存、玩家選擇 |
| `rec_header.py` | 解析錄影檔開頭的玩家、文明與地圖資料 |
| `mapdata.py` | 地圖編號對應遊戲 `maps.json` 的地圖名稱；模組地圖顯示檔名，戰役顯示「劇本／戰役」 |
| `history.py` / `savegames.py` | 最近 10 場、錄影搜尋、玩家推斷 |
| `civdata.py` / `units.py` | 遊戲文明文字、特殊兵種與克制說明 |
| `ratings.py` | 官方排行榜目前積分 |
| `launcher.py` | Steam 啟動與視窗位置 |
| `demo.py` | 公開截圖用虛構對局 |
| `verify_offline.py` | 驗證本機錄影的解析結果 |

兵種清單取自遊戲的文明科技樹（`CivTechTrees`）：各建築的特殊兵種（不只城堡，例如攻城器製造所的榴彈砲），以及少數文明共有的地區兵種（例如象弓騎兵、瓦蘭吉衛隊），菁英與重裝升級併入原兵種，並標示生產建築與開放時代。兵種克制關係以遊戲英文說明的固定句型解析，再對應繁中兵種名稱；沒有記載時不自行推論。`python units.py` 可列出資料與尚未對應的英文詞。

解析器只處理所需的錄影檔頭欄位，不依賴完整對局解析套件。遊戲改版後若解析失敗，可執行 `python opponent-civ/verify_offline.py` 協助定位。

## 流程與速查

前期流程依文明推薦順序與地圖選取；「換流程」與步驟標記屬於當場對局。流程庫可搜尋、加入或移出推薦，用 ▲▼ 調整順序；個人排序存在本機設定資料夾。

內建資料為 `data/builds.zh-TW.json`。保留流程的固定 ID，避免使用者的推薦順序失效。速查以 `build_ids` 連到前期流程；`civ` 指定文明，或留空並用 `maps` 限定地圖，供所有文明使用。卡片依視窗寬度排成一至三欄，字級自動適配，空間不足時可捲動。

本機影片可由流程庫的「本機影片（選用）…」指定資料夾，以對應檔名辨識；沒有影片不影響內建流程。教材及個人 RP 不放入儲存庫或 EXE。

## 離線預覽

在 repository 根目錄，使用含 Tk 的 Python 3.12+：

```sh
python opponent-civ/dashboard.py --demo
python opponent-civ/dashboard.py --demo --demo-build 33
```

預設使用明確標示的虛構對局與文明說明，流程使用完整內建資料；可用 `--game-dir` 載入自己的遊戲文字。macOS 預覽不驗證 Windows 錄影監看或雙螢幕 API。

首頁截圖使用本機已下載 RP 載入介面，詳見 [截圖來源](../docs/images/README.md)。它們不是遊戲播放畫面，也不表示已實作自動復盤。

## 地圖注意

`data/map-notes.zh-TW.json` 獨立保存地圖提醒。一般內建圖優先比對 map ID；自訂圖依完整別名比對，避免套用到同名變體或 QS 快速開局。切換對局自動換內容，不搶選分頁；右上可手動預習或回到本場。資料隨 EXE 內建，打包驗證包含地圖頁數。

[盤點、來源與待補地圖](../docs/map-notes-research.md)。
