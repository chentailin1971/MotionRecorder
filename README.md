# Motion Detection Recording / 移動偵測錄影

[中文](#中文) · [English](#english)

---

## 中文

使用本機 Web Cam 做**移動偵測錄影**的 Windows 桌面程式。可設定多組偵測時段(含星期),偵測到移動時自動錄影,每次錄影的開始與結束都會寫入 log。介面支援**中文 / English** 一鍵切換。

**版次** v2 · **日期** 2026-10-29 · **作者** Chen Tai Lin

### 功能

- **移動偵測錄影**:以畫面差異偵測移動,有移動才開始錄影,移動停止後再續錄指定秒數後結束。
- **多排程**:最多 5 組時段,每組可各自勾選週一至週日;結束時間早於開始時間視為**跨午夜**(歸屬於「開始」那一天)。時段之外攝影機會關閉,並以大字顯示**倒數計時**到下一次偵測。
- **每次錄影都記 log**:`motion_log.txt` 記錄監控開始 / 停止、偵測啟動 / 結束、錄影開始 / 結束(含長度與檔名)。
- **預錄**:移動發生前的幾秒畫面也會一併錄下。
- **預覽鏡頭**:不錄影、不受排程限制,方便調整攝影機角度。
- **暫停 / 繼續**:鏡頭保持開啟,但暫停偵測與錄影。
- **畫面旋轉**:不旋轉 / 左轉 90° / 右轉 90° / 旋轉 180°。
- **錄影檔管理**:列出所有錄影檔,可直接播放、刪除,或依保留天數清除舊檔(刪除前會確認)。
- **影像時間浮水印**:日期時間寫在畫面右上角(預覽與錄影檔皆有)。
- **雙語介面**:右上角黃色按鈕切換 `ENG` / `中文`,首次使用預設中文,並記住上次選擇。

### 系統需求

- Windows 10 / 11(64 位元)
- 一支 Web Cam
- 從原始碼執行需要 Python 3.10 以上(開發環境為 Python 3.13)

> 程式使用 DirectShow 開啟攝影機,並使用 Windows 的 `os.startfile`,**僅支援 Windows**。

### 使用方式

**方式一:使用打包好的 exe**

1. 下載並解壓縮 `MotionRecorder_v2.zip`,放在可寫入的位置(例如 `C:\MotionRecorder`,**不要**放在 `Program Files`)。
2. 雙擊 `MotionRecorder.exe`。整個 `MotionRecorder` 資料夾要一起搬移,不能只複製 exe。
3. 第一次執行時,Windows SmartScreen 可能因為 exe 沒有數位簽章而提示,選「其他資訊」→「仍要執行」。

**方式二:從原始碼執行**

```powershell
pip install -r requirements.txt
python motion_recorder.py
```

**自行打包 exe**

```powershell
pip install pyinstaller
pyinstaller --noconfirm --onedir --windowed --name MotionRecorder --collect-all customtkinter motion_recorder.py
```

成品在 `dist\MotionRecorder\`。

### 操作流程

1. 先按「**預覽鏡頭**」確認取景,必要時調整「畫面旋轉」。
2. 勾選「啟用排程時段」並設定時段與星期;不勾選則為**持續偵測**。
3. 按「**開始監控**」(綠色)。偵測到移動會自動錄影,左上角顯示狀態,畫面下方的 Log 即時更新。
4. 按「**停止監控**」(紅色)。程式會先把進行中的錄影存檔,再回到待機。

### 設定說明

| 欄位 | 說明 |
| --- | --- |
| 排程時段 | 開始 ~ 結束(`HH:MM`)與星期;結束早於開始 = 跨午夜;最多 5 組 |
| 攝影機編號 | 多支攝影機時選擇哪一支(0 開始) |
| 靈敏度門檻 (變動%) | 畫面變動面積佔比達此值才算移動;越小越敏感,預設 0.5 |
| 停止後續錄 (秒) | 移動停止後再多錄幾秒,預設 5 |
| 預錄 (秒) | 移動發生前先保留幾秒畫面,預設 2 |
| 畫面旋轉 | 預覽與錄影檔都會套用 |
| 儲存資料夾 | 錄影檔位置,預設為程式旁的 `recordings` |

設定會在按下「開始監控」時存入 `config.json`(語言切換則立即儲存)。

### 產生的檔案

都建立在程式(exe 或 `.py`)所在的資料夾:

| 檔案 | 內容 |
| --- | --- |
| `recordings\motion_YYYYMMDD_HHMMSS.mp4` | 錄影檔(mp4v 編碼) |
| `motion_log.txt` | 事件紀錄 |
| `config.json` | 使用者設定 |

Log 範例:

```
2026-10-29 08:52:07 | Monitoring started | Always on
2026-10-29 08:52:07 | Detection on | Camera 0
2026-10-29 08:52:11 | Recording started | motion_20261029_085211.mp4
2026-10-29 08:52:12 | Recording ended | Motion stopped | Length 1 s | motion_20261029_085211.mp4
```

> Log 以**寫入當下的語言**記錄,切換語言前寫入的舊紀錄不會被翻譯。

### 注意事項

- 攝影機預設解析度通常是 640×480,錄影檔大小與此相關。
- 時段之外鏡頭會關閉;要看取景請先停止監控,改用「預覽鏡頭」。
- 若偵測到誤觸發(光線變化、風吹窗簾)請調高靈敏度門檻;抓不到小動作則調低。
- **隱私與法規**:錄影可能拍到人員。使用前請確認符合所在地區關於錄影、監控與個人資料的法律規定,並於必要場合告知被拍攝者。

### 授權

本專案以 [MIT License](LICENSE) 授權,Copyright (c) 2026 Chen Tai Lin。

---

## English

A Windows desktop app that does **motion-detection recording** with your local webcam. Set one or more detection schedules (with weekdays); when motion is detected it records automatically, and every recording start and end is written to a log. The UI switches between **中文 / English** with one click.

**Version** v2 · **Date** 2026-10-29 · **Author** Chen Tai Lin

### Features

- **Motion-triggered recording**: detects motion by frame differencing, starts recording on motion, and keeps recording for a configurable number of seconds after motion stops.
- **Multiple schedules**: up to 5 time ranges, each with its own Monday–Sunday selection. An end time earlier than the start time means **overnight** (it belongs to the day it *starts*). Outside the schedule the camera is off and a large **countdown** to the next detection window is shown.
- **Every recording is logged**: `motion_log.txt` records monitoring start/stop, detection on/off, and recording start/end (with duration and file name).
- **Pre-record**: the seconds just before the motion are saved too.
- **Camera preview**: no recording and not bound by the schedule — handy for aiming the camera.
- **Pause / Resume**: keeps the camera open but pauses detection and recording.
- **Rotation**: none / left 90° / right 90° / 180°.
- **Recording management**: lists all recordings; play or delete them, or delete old files by age (with confirmation).
- **Timestamp overlay**: date and time are drawn at the top-right of the image (preview and recordings).
- **Bilingual UI**: the yellow button at the top-right toggles `ENG` / `中文`. Chinese is the default on first run, and your choice is remembered.

### Requirements

- Windows 10 / 11 (64-bit)
- A webcam
- Python 3.10+ to run from source (developed on Python 3.13)

> The app opens the camera through DirectShow and uses Windows' `os.startfile`, so it is **Windows-only**.

### Getting started

**Option 1: the packaged exe**

1. Download and unzip `MotionRecorder_v2.zip` to a writable location (e.g. `C:\MotionRecorder`, **not** `Program Files`).
2. Double-click `MotionRecorder.exe`. Keep the whole `MotionRecorder` folder together — do not copy the exe alone.
3. On first launch, Windows SmartScreen may warn because the exe is not code-signed. Choose "More info" → "Run anyway".

**Option 2: run from source**

```powershell
pip install -r requirements.txt
python motion_recorder.py
```

**Build the exe yourself**

```powershell
pip install pyinstaller
pyinstaller --noconfirm --onedir --windowed --name MotionRecorder --collect-all customtkinter motion_recorder.py
```

The result is in `dist\MotionRecorder\`.

### Workflow

1. Click **Camera preview** to check the view; adjust **Rotation** if needed.
2. Tick **Enable schedule** and set the time ranges and weekdays; leave it unticked for **always-on detection**.
3. Click **Start monitoring** (green). Motion triggers recording automatically; the badge at the top-left shows the state and the log updates live.
4. Click **Stop monitoring** (red). The app finishes saving any recording in progress, then returns to idle.

### Settings

| Field | Description |
| --- | --- |
| Schedule | Start ~ end (`HH:MM`) plus weekdays; end earlier than start = overnight; up to 5 |
| Camera index | Which camera to use when you have several (starts at 0) |
| Sensitivity (change %) | Percentage of the frame that must change to count as motion; lower = more sensitive; default 0.5 |
| Keep recording after stop (s) | Extra seconds recorded after motion stops; default 5 |
| Pre-record (s) | Seconds of footage kept from before the motion; default 2 |
| Rotation | Applied to both the preview and the recordings |
| Save folder | Where recordings go; default is `recordings` next to the program |

Settings are saved to `config.json` when you press **Start monitoring** (the language is saved immediately when toggled).

### Files created

All are created in the folder that contains the program (exe or `.py`):

| File | Contents |
| --- | --- |
| `recordings\motion_YYYYMMDD_HHMMSS.mp4` | Recordings (mp4v codec) |
| `motion_log.txt` | Event log |
| `config.json` | User settings |

Sample log:

```
2026-10-29 08:52:07 | Monitoring started | Always on
2026-10-29 08:52:07 | Detection on | Camera 0
2026-10-29 08:52:11 | Recording started | motion_20261029_085211.mp4
2026-10-29 08:52:12 | Recording ended | Motion stopped | Length 1 s | motion_20261029_085211.mp4
```

> Log lines are written in the language **active at the time**; entries written before you switch languages are not translated.

### Notes

- The default camera resolution is usually 640×480, which also determines recording size.
- The camera is off outside the schedule; to check the view, stop monitoring and use **Camera preview**.
- If you get false triggers (lighting changes, curtains in the wind), raise the sensitivity threshold; if small movements are missed, lower it.
- **Privacy and legal**: recordings may capture people. Make sure your use complies with the laws on recording, surveillance and personal data where you are, and inform people being recorded where required.

### License

Released under the [MIT License](LICENSE). Copyright (c) 2026 Chen Tai Lin.
