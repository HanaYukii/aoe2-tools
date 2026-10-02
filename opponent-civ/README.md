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
| `--demo` | 虛構範例畫面，不監看個人錄影、不連網；仍需遊戲文字資料 |

設定與視窗位置分別保存在 `%LOCALAPPDATA%\aoe2-tools\opponent-civ\settings.json` 與 `window.json`。首次嘗試放在副螢幕，之後記住視窗位置。不要將本機設定或錄影加入版本控制。

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
| `rec_header.py` | 解析錄影檔開頭的玩家與文明資料 |
| `history.py` / `savegames.py` | 最近 10 場、錄影搜尋、玩家推斷 |
| `civdata.py` / `units.py` | 遊戲文明文字、特殊兵種與克制說明 |
| `ratings.py` | 官方排行榜目前積分 |
| `launcher.py` | Steam 啟動與視窗位置 |
| `demo.py` | 公開截圖用虛構對局 |
| `verify_offline.py` | 驗證本機錄影的解析結果 |

兵種克制關係以遊戲英文說明的固定句型解析，再對應繁中兵種名稱；沒有記載時不自行推論。`python units.py` 可列出資料與尚未對應的英文詞。

解析器只處理所需的錄影檔頭欄位，不依賴完整對局解析套件。遊戲改版後若解析失敗，可執行 `python opponent-civ/verify_offline.py` 協助定位。
