"""移動偵測錄影 / Motion Detection Recording

使用本機 Web Cam,在設定的時段內偵測移動並自動錄影,
每次錄影開始 / 結束都會寫入 log。支援中文 / English 介面切換。
"""
import json
import math
import os
import re
import sys
import threading
import time
from collections import deque
from datetime import datetime, time as dtime, timedelta
from tkinter import messagebox

import customtkinter as ctk
import cv2
from PIL import Image

APP_VERSION = "2"
BUILD_DATE = "2026-10-29"
AUTHOR = "Chen Tai Lin"
MAX_SCHEDULES = 5

APP_DIR = os.path.dirname(sys.executable if getattr(sys, "frozen", False) else os.path.abspath(__file__))
CONFIG_PATH = os.path.join(APP_DIR, "config.json")
DEFAULTS = {
    "language": "zh",
    "camera_index": 0,
    "schedule_enabled": False,
    # 多排程:days 為 0~6 (週一~週日);跨午夜的時段歸屬於「開始」那一天
    "schedules": [{"start": "22:00", "end": "06:00", "days": [0, 1, 2, 3, 4, 5, 6]}],
    "sensitivity": 0.5,      # 畫面變動面積佔比 (%),越小越敏感
    "post_seconds": 5,       # 移動停止後再多錄幾秒
    "pre_seconds": 2,        # 移動前預錄幾秒
    "rotation": "none",      # none / left / right / r180
    "output_dir": os.path.join(APP_DIR, "recordings"),
}
FPS = 20
# 旋轉選項 (逆時針 = 左轉)
ROT_KEYS = ["none", "left", "right", "r180"]
ROT_CV = {
    "none": None,
    "left": cv2.ROTATE_90_COUNTERCLOCKWISE,
    "right": cv2.ROTATE_90_CLOCKWISE,
    "r180": cv2.ROTATE_180,
}
OLD_ROT_NAMES = {"不旋轉": "none", "左轉90度": "left", "右轉90度": "right", "旋轉180度": "r180"}   # 舊版設定檔
TIME_RE = re.compile(r"^([01]?\d|2[0-3]):([0-5]\d)$")

# ---------- 多語系 (中文, English) ----------
LANG = "zh"
STR = {
    "app_title": ("移動偵測錄影", "Motion Detection Recording"),
    "app_sub": ("Motion Detection Recording", "Webcam motion-triggered recorder"),
    "nav_monitor": ("  ◉   即時監控", "  ◉   Live Monitor"),
    "nav_files": ("  ▶   錄影檔", "  ▶   Recordings"),
    "nav_about": ("  ⓘ   關於", "  ⓘ   About"),
    # 設定卡片
    "settings": ("⚙  錄影設定", "⚙  Recording Settings"),
    "sched_enable": ("啟用排程時段 (取消 = 持續偵測)", "Enable schedule (uncheck = always detect)"),
    "sched_add": ("＋ 新增時段", "＋ Add schedule"),
    "sched_full": ("已達上限", "Limit reached"),
    "sched_hint": ("結束早於開始 = 跨午夜", "End before start = overnight"),
    "cam_index": ("攝影機編號", "Camera index"),
    "sens": ("靈敏度門檻 (變動%)", "Sensitivity (change %)"),
    "post": ("停止後續錄 (秒)", "Keep recording after stop (s)"),
    "pre": ("預錄 (秒)", "Pre-record (s)"),
    "rotation": ("畫面旋轉", "Rotation"),
    "rot_none": ("不旋轉", "No rotation"),
    "rot_left": ("左轉90度", "Rotate left 90°"),
    "rot_right": ("右轉90度", "Rotate right 90°"),
    "rot_r180": ("旋轉180度", "Rotate 180°"),
    "save_dir": ("儲存資料夾", "Save folder"),
    "open": ("開啟", "Open"),
    "purge_btn": ("清空舊檔 (依保留天數)", "Delete old files (by age)"),
    "preview_btn": ("預覽鏡頭 (調整角度用)", "Camera preview (for aiming)"),
    "preview_stop": ("停止預覽", "Stop preview"),
    "pause": ("暫停", "Pause"),
    "resume": ("繼續", "Resume"),
    "start_btn": ("▶  開始監控", "▶  Start monitoring"),
    "stop_btn": ("■  停止監控", "■  Stop monitoring"),
    "count": ("本次錄影次數", "Recordings this session"),
    # 狀態 (Worker.status 存的是 key)
    "st_idle": ("未啟動", "Idle"),
    "st_wait": ("等待排程時段", "Waiting for schedule"),
    "st_camfail": ("無法開啟攝影機,5 秒後重試", "Camera unavailable, retrying in 5 s"),
    "st_preview": ("預覽中 (不錄影)", "Preview (not recording)"),
    "st_rec": ("偵測中 (錄影中)", "Detecting (recording)"),
    "st_nomotion": ("偵測中 (無移動)", "Detecting (no motion)"),
    "st_paused": ("已暫停", "Paused"),
    "st_standby": ("待機", "Standby"),
    # 影像區
    "ph_preview": ("預覽 (監控中才顯示)", "Preview (shown while monitoring)"),
    "ph_starting": ("攝影機啟動中...", "Starting camera..."),
    "ph_outside": ("攝影機已關閉 (目前在排程時段外)\n需看取景請先停止監控,改用「預覽鏡頭」",
                   "Camera is off (outside scheduled hours)\nTo check the view, stop monitoring and use \"Camera preview\""),
    "ph_outside_short": ("攝影機已關閉 (目前在排程時段外)", "Camera is off (outside scheduled hours)"),
    "countdown": ("倒數計時", "Countdown"),
    "bd_rec": ("錄影中", "Recording"),
    "bd_detect": ("偵測中", "Detecting"),
    "bd_preview": ("預覽", "Preview"),
    "bd_paused": ("已暫停", "Paused"),
    # Log
    "log_title": ("▤  錄影 Log", "▤  Recording Log"),
    "log_clear": ("清空日誌", "Clear log"),
    "log_clear_title": ("清空日誌", "Clear log"),
    "log_clear_ask": ("確定要清空日誌嗎?\n(motion_log.txt 內容也會一併清除)", "Clear the log?\n(motion_log.txt will be emptied too)"),
    "ev_mon_start": ("監控開始", "Monitoring started"),
    "ev_always": ("持續偵測", "Always on"),
    "ev_schedule": ("排程 {s}", "Schedule {s}"),
    "ev_det_on": ("偵測啟動", "Detection on"),
    "ev_det_off": ("偵測結束", "Detection off"),
    "ev_rec_start": ("錄影開始", "Recording started"),
    "ev_rec_end": ("錄影結束", "Recording ended"),
    "ev_error": ("錯誤", "Error"),
    "ev_pause": ("偵測暫停", "Detection paused"),
    "ev_resume": ("偵測繼續", "Detection resumed"),
    "ev_mon_stop": ("監控停止", "Monitoring stopped"),
    "ev_purge": ("清除舊檔", "Old files deleted"),
    "d_camera": ("攝影機 {n}", "Camera {n}"),
    "d_left_window": ("已離開排程時段,釋放攝影機", "Left schedule window, camera released"),
    "d_reconnect": ("攝影機讀取失敗,重新連線", "Camera read failed, reconnecting"),
    "d_length": ("長度 {s} 秒", "Length {s} s"),
    "d_purged": ("刪除 {n} 個超過 {d} 天的錄影檔", "Deleted {n} recordings older than {d} days"),
    "r_motion_stop": ("移動停止", "Motion stopped"),
    "r_window_end": ("排程時段結束", "Schedule window ended"),
    "r_cam_fail": ("攝影機讀取失敗", "Camera read failed"),
    "r_prog_stop": ("程式停止", "Stopped"),
    "r_paused": ("已暫停", "Paused"),
    "weekday_prefix": ("週", ""),
    # 錄影檔頁
    "files_title": ("錄影檔", "Recordings"),
    "files_summary": ("共 {n} 個檔案,{mb:.1f} MB", "{n} files, {mb:.1f} MB"),
    "files_open": ("開啟資料夾", "Open folder"),
    "files_refresh": ("重新整理", "Refresh"),
    "files_none": ("尚無錄影檔", "No recordings yet"),
    "play": ("播放", "Play"),
    "delete": ("刪除", "Delete"),
    "del_busy_t": ("無法刪除", "Cannot delete"),
    "del_busy": ("此檔案正在錄影中。", "This file is currently being recorded."),
    "del_ask_t": ("刪除錄影檔", "Delete recording"),
    "del_ask": ("確定要刪除?\n{f}", "Delete this file?\n{f}"),
    "del_fail": ("刪除失敗", "Delete failed"),
    "purge_title": ("清空舊檔", "Delete old files"),
    "purge_ask_days": ("保留最近幾天的錄影?\n(更早的 .mp4 會被刪除)", "Keep recordings from the last how many days?\n(Older .mp4 files will be deleted)"),
    "input_err_t": ("輸入錯誤", "Invalid input"),
    "input_err": ("請輸入 1 以上的整數天數。", "Enter a whole number of days (1 or more)."),
    "purge_none": ("沒有超過 {d} 天的錄影檔。", "No recordings older than {d} days."),
    "purge_confirm": ("將刪除 {n} 個超過 {d} 天的錄影檔 ({mb:.1f} MB)。\n此動作無法復原,確定嗎?",
                      "This will delete {n} recordings older than {d} days ({mb:.1f} MB).\nThis cannot be undone. Continue?"),
    # 關於
    "about_version": ("版次", "Version"),
    "about_date": ("日期", "Date"),
    "about_author": ("作者", "Author"),
    "about_desc": ("使用本機 Web Cam 於排程時段內偵測移動並自動錄影,每次錄影的開始與結束都會記錄於 log。",
                   "Uses the local webcam to detect motion within scheduled hours and record automatically. "
                   "Every recording start and end is written to the log."),
    # 對話框 / 錯誤
    "wait_title": ("請稍候", "Please wait"),
    "saving": ("存檔中，請稍待...", "Saving, please wait..."),
    "cfg_err": ("設定錯誤", "Invalid settings"),
    "err_time": ("時間格式錯誤: {v!r} (請用 HH:MM)", "Invalid time: {v!r} (use HH:MM)"),
    "err_sched_n": ("第 {i} 個時段: {e}", "Schedule {i}: {e}"),
    "err_days": ("第 {i} 個時段至少要勾選一個星期。", "Schedule {i}: select at least one weekday."),
    "err_num": ("攝影機編號、靈敏度、續錄秒數、預錄秒數必須是數字。", "Camera index, sensitivity, and seconds must be numbers."),
    "err_neg": ("數值不可為負數,靈敏度須大於 0。", "Values cannot be negative; sensitivity must be above 0."),
}
WEEKDAYS = {"zh": list("一二三四五六日"), "en": ["Mo", "Tu", "We", "Th", "Fr", "Sa", "Su"]}


def tr(key, **kw):
    s = STR[key][0 if LANG == "zh" else 1]
    return s.format(**kw) if kw else s


def set_lang(lang):
    global LANG
    LANG = lang if lang in ("zh", "en") else "zh"


def weekday_labels():
    return WEEKDAYS[LANG]


# 配色
C_HEADER, C_SIDEBAR, C_ACTIVE = "#12407a", "#0e3568", "#2f6fe4"
C_BG, C_CARD, C_BORDER = "#e8eef7", "#ffffff", "#d6dfeb"
C_GREEN, C_RED, C_BLUE, C_GRAY, C_ORANGE = "#2e9e5b", "#d93636", "#2f80ed", "#8a97a8", "#e8912d"
C_TEXT, C_MUTED = "#1f2d3d", "#6b7a8d"
C_STATUS_BG, C_BADGE_BG = "#e3f1ea", "#1b2430"   # 呼吸燈淡出時的底色
C_LANG = "#ffd54a"                                # 語言切換鈕 (黃字)
FONT_FAMILY = "Microsoft JhengHei UI"


def F(size=13, bold=False):
    return ctk.CTkFont(family=FONT_FAMILY, size=size, weight="bold" if bold else "normal")


def mix(c_from, c_to, k):
    """兩個 #rrggbb 顏色線性混合,k=0 為 c_from,k=1 為 c_to。"""
    a = [int(c_from[i:i + 2], 16) for i in (1, 3, 5)]
    b = [int(c_to[i:i + 2], 16) for i in (1, 3, 5)]
    return "#" + "".join(f"{round(x + (y - x) * k):02x}" for x, y in zip(a, b))


def breath(period=1.6, floor=0.2):
    """呼吸燈亮度 floor~1,以時間為基準的正弦波。"""
    return floor + (1 - floor) * (0.5 + 0.5 * math.sin(time.time() * 2 * math.pi / period))


def parse_hhmm(s):
    m = TIME_RE.match(s.strip())
    if not m:
        raise ValueError(tr("err_time", v=s))
    return dtime(int(m.group(1)), int(m.group(2)))


def _match(now, s):
    """now (datetime) 是否落在單一排程 s 內。start == end 視為整天;end < start 視為跨午夜。"""
    t, today = now.time(), now.weekday()
    st, en, days = parse_hhmm(s["start"]), parse_hhmm(s["end"]), s["days"]
    if st == en:
        return today in days
    if st < en:
        return today in days and st <= t < en
    return (today in days and t >= st) or ((today - 1) % 7 in days and t < en)


def schedule_active(now, schedules):
    return any(_match(now, s) for s in schedules)


def next_start(now, schedules):
    """距離現在最近的下一次「開始」時間;沒有任何有效排程時回傳 None。"""
    best = None
    for s in schedules:
        st = parse_hhmm(s["start"])
        for d in range(8):
            day = now.date() + timedelta(days=d)
            if day.weekday() in s["days"]:
                dt = datetime.combine(day, st)
                if dt > now:
                    if best is None or dt < best:
                        best = dt
                    break
    return best


def describe_schedules(schedules):
    parts = []
    for s in schedules:
        base = f"{s['start']}~{s['end']}"
        if len(s["days"]) < 7:
            names = weekday_labels()
            sep = "" if LANG == "zh" else ","
            base += f"({tr('weekday_prefix')}{sep.join(names[d] for d in sorted(s['days']))})"
        parts.append(base)
    return ("、" if LANG == "zh" else "; ").join(parts)


class Logger:
    def __init__(self, path, sink=None):
        self.path, self.sink = path, sink
        self.lock = threading.Lock()

    def write(self, event_key, detail=""):
        """event_key 為 STR 的 key;以目前語言寫入。"""
        line = f"{datetime.now():%Y-%m-%d %H:%M:%S} | {tr(event_key)}" + (f" | {detail}" if detail else "")
        with self.lock:
            with open(self.path, "a", encoding="utf-8") as f:
                f.write(line + "\n")
        if self.sink:
            self.sink(line)


class Worker(threading.Thread):
    """攝影機擷取 + 移動偵測 + 錄影,獨立執行緒。status 存的是 STR 的 key。"""

    def __init__(self, cfg, logger):
        super().__init__(daemon=True)
        self.cfg, self.log = cfg, logger
        self.stop_evt = threading.Event()
        self.frame = None       # 給 UI 預覽 (BGR)
        self.status = "st_standby"
        self.recording = False
        self.paused = False
        self.rec_count = 0      # 本次監控的錄影次數

    def run(self):
        cfg = self.cfg
        os.makedirs(cfg["output_dir"], exist_ok=True)
        cap = None
        try:
            while not self.stop_evt.is_set():
                active = cfg.get("preview_only") or (not cfg["schedule_enabled"]) or schedule_active(datetime.now(), cfg["schedules"])
                if not active:
                    if cap is not None:
                        cap.release()
                        cap = None
                        self.frame = None
                        if not cfg.get("preview_only"):
                            self.log.write("ev_det_off", tr("d_left_window"))
                    self.status = "st_wait"
                    self.stop_evt.wait(1)
                    continue
                if cap is None:
                    cap = cv2.VideoCapture(cfg["camera_index"], cv2.CAP_DSHOW)
                    if not cap.isOpened():
                        cap.release()
                        cap = None
                        self.status = "st_camfail"
                        self.stop_evt.wait(5)
                        continue
                    if not cfg.get("preview_only"):
                        self.log.write("ev_det_on", tr("d_camera", n=cfg["camera_index"]))
                    self._detect_loop(cap)
                    cap.release()
                    cap = None
                    self.frame = None
        finally:
            if cap is not None:
                cap.release()

    def _detect_loop(self, cap):
        cfg = self.cfg
        bg = None
        warmup = 0
        pre = deque(maxlen=max(1, int(cfg["pre_seconds"] * FPS)))
        writer = None
        last_motion = 0.0
        rec_start = 0.0
        rec_path = ""
        frame_interval = 1.0 / FPS
        last_t = 0.0
        fails = 0

        def stop_rec(reason_key):
            nonlocal writer
            if writer is not None:
                writer.release()
                writer = None
                self.recording = False
                self.log.write("ev_rec_end", f"{tr(reason_key)} | {tr('d_length', s=f'{time.time() - rec_start:.0f}')} | {os.path.basename(rec_path)}")

        try:
            while not self.stop_evt.is_set():
                preview = cfg.get("preview_only")
                if not preview and cfg["schedule_enabled"] and not schedule_active(datetime.now(), cfg["schedules"]):
                    stop_rec("r_window_end")
                    return
                ok, frame = cap.read()
                if not ok:
                    fails += 1
                    if fails > 30:
                        stop_rec("r_cam_fail")
                        self.log.write("ev_error", tr("d_reconnect"))
                        return
                    time.sleep(0.05)
                    continue
                fails = 0
                rot = ROT_CV.get(cfg["rotation"])
                if rot is not None:
                    frame = cv2.rotate(frame, rot)
                now = time.time()
                if now - last_t < frame_interval:
                    continue
                last_t = now

                shown = frame.copy()
                stamp = f"{datetime.now():%Y-%m-%d %H:%M:%S}"
                (tw, _), _ = cv2.getTextSize(stamp, cv2.FONT_HERSHEY_SIMPLEX, 0.7, 2)
                cv2.putText(shown, stamp, (shown.shape[1] - tw - 10, 25), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 255), 2)

                if self.paused and not preview:
                    # 暫停:鏡頭保持開啟,但不偵測也不錄影
                    stop_rec("r_paused")
                    bg, warmup = None, 0
                    pre.clear()
                    self.frame = shown
                    self.status = "st_paused"
                    continue

                gray = cv2.GaussianBlur(cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY), (21, 21), 0)
                if bg is None or bg.shape != gray.shape:
                    bg = gray.astype("float")
                cv2.accumulateWeighted(gray, bg, 0.05)
                warmup += 1
                moving = False
                if warmup > FPS and not preview:  # 前 1 秒暖機,避免自動曝光造成誤判
                    diff = cv2.absdiff(gray, cv2.convertScaleAbs(bg))
                    mask = cv2.dilate(cv2.threshold(diff, 25, 255, cv2.THRESH_BINARY)[1], None, iterations=2)
                    ratio = cv2.countNonZero(mask) * 100.0 / mask.size
                    moving = ratio >= cfg["sensitivity"]

                if moving:
                    last_motion = now
                    if writer is None:
                        h, w = shown.shape[:2]
                        rec_path = os.path.join(cfg["output_dir"], f"motion_{datetime.now():%Y%m%d_%H%M%S}.mp4")
                        writer = cv2.VideoWriter(rec_path, cv2.VideoWriter_fourcc(*"mp4v"), FPS, (w, h))
                        rec_start = now
                        self.recording = True
                        self.rec_count += 1
                        self.log.write("ev_rec_start", os.path.basename(rec_path))
                        for f in pre:
                            writer.write(f)
                        pre.clear()
                if writer is not None:
                    writer.write(shown)
                    if now - last_motion > cfg["post_seconds"]:
                        stop_rec("r_motion_stop")
                else:
                    pre.append(shown)

                self.frame = shown
                if preview:
                    self.status = "st_preview"
                else:
                    self.status = "st_rec" if self.recording else "st_nomotion"
        finally:
            stop_rec("r_prog_stop")


class Spin(ctk.CTkFrame):
    """數字輸入框 + 上下調整鈕。"""

    def __init__(self, master, var, lo, hi, step, digits=0):
        super().__init__(master, fg_color="transparent")
        self.var, self.lo, self.hi, self.step, self.digits = var, lo, hi, step, digits
        ctk.CTkEntry(self, textvariable=var, width=74, height=30, fg_color="white", border_color=C_BORDER, font=F(13)).pack(side="left")
        btns = ctk.CTkFrame(self, fg_color="transparent")
        btns.pack(side="left", padx=(2, 0))
        for txt, d in (("▲", 1), ("▼", -1)):
            ctk.CTkButton(btns, text=txt, width=22, height=15, corner_radius=3, font=F(8), fg_color="#eef2f8",
                          text_color=C_MUTED, hover_color="#dbe3ee", command=lambda d=d: self._bump(d)).pack(pady=0)

    def _bump(self, d):
        try:
            v = float(self.var.get())
        except ValueError:
            v = self.lo
        v = min(self.hi, max(self.lo, v + d * self.step))
        self.var.set(f"{v:.{self.digits}f}")


class ScheduleRow(ctk.CTkFrame):
    """一個排程時段:開始 ~ 結束 + 週一~週日勾選。"""

    def __init__(self, master, sched, on_delete):
        super().__init__(master, fg_color="transparent")
        self.v_start = ctk.StringVar(value=sched["start"])
        self.v_end = ctk.StringVar(value=sched["end"])
        self.days = set(sched["days"])
        ek = dict(width=52, height=26, fg_color="white", border_color=C_BORDER, font=F(12), justify="center")
        ctk.CTkEntry(self, textvariable=self.v_start, **ek).pack(side="left")
        ctk.CTkLabel(self, text="~", font=F(12), text_color=C_MUTED, width=14).pack(side="left")
        ctk.CTkEntry(self, textvariable=self.v_end, **ek).pack(side="left", padx=(0, 6))
        self.chips = []
        for i, ch in enumerate(weekday_labels()):
            b = ctk.CTkButton(self, text=ch, width=25, height=24, corner_radius=5, font=F(10, True), command=lambda i=i: self._toggle(i))
            b.pack(side="left", padx=1)
            self.chips.append(b)
        self.btn_del = ctk.CTkButton(self, text="✕", width=22, height=24, corner_radius=5, font=F(12, True), fg_color="transparent",
                                     text_color=C_MUTED, hover_color="#fbe3e3", command=lambda: on_delete(self))
        self.btn_del.pack(side="left", padx=(6, 0))
        self._paint()

    def relabel(self):
        for b, ch in zip(self.chips, weekday_labels()):
            b.configure(text=ch)

    def _toggle(self, i):
        self.days.symmetric_difference_update({i})
        self._paint()

    def _paint(self):
        for i, b in enumerate(self.chips):
            if i in self.days:
                b.configure(fg_color=C_ACTIVE, hover_color="#1f66c9", text_color="white")
            else:
                b.configure(fg_color="#eef2f8", hover_color="#dbe3ee", text_color=C_MUTED)

    def set_deletable(self, ok):
        self.btn_del.configure(state="normal" if ok else "disabled")

    def get(self):
        return {"start": self.v_start.get().strip(), "end": self.v_end.get().strip(), "days": sorted(self.days)}


class App(ctk.CTk):
    def __init__(self):
        ctk.set_appearance_mode("light")
        super().__init__(fg_color=C_BG)
        self.geometry("1200x960")
        self.minsize(1060, 820)

        self.cfg = dict(DEFAULTS)
        try:
            with open(CONFIG_PATH, encoding="utf-8") as f:
                loaded = json.load(f)
            if "schedules" not in loaded and "start_time" in loaded:   # 舊版單一時段設定
                loaded["schedules"] = [{"start": loaded["start_time"], "end": loaded.get("end_time", "06:00"), "days": list(range(7))}]
            self.cfg.update(loaded)
        except (OSError, ValueError, KeyError):
            pass
        for k in ("start_time", "end_time"):
            self.cfg.pop(k, None)
        if not isinstance(self.cfg["schedules"], list) or not self.cfg["schedules"]:
            self.cfg["schedules"] = DEFAULTS["schedules"]
        self.cfg["rotation"] = OLD_ROT_NAMES.get(self.cfg["rotation"], self.cfg["rotation"])
        if self.cfg["rotation"] not in ROT_KEYS:
            self.cfg["rotation"] = "none"
        set_lang(self.cfg.get("language", "zh"))   # 首次使用預設中文

        self.worker = None
        self._img = None
        self._i18n = []        # (widget, key) 語言切換時重設文字
        self.logger = Logger(os.path.join(APP_DIR, "motion_log.txt"), self._log_sink)

        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(1, weight=1)
        self._build_header()
        self._build_sidebar()
        self.pages = {}
        host = ctk.CTkFrame(self, fg_color="transparent")
        host.grid(row=1, column=1, sticky="nsew", padx=14, pady=14)
        host.grid_columnconfigure(0, weight=1)
        host.grid_rowconfigure(0, weight=1)
        for name, builder in (("monitor", self._build_monitor), ("files", self._build_files), ("about", self._build_about)):
            page = ctk.CTkFrame(host, fg_color="transparent")
            page.grid(row=0, column=0, sticky="nsew")
            builder(page)
            self.pages[name] = page
        self._show_page("monitor")
        self._load_log_tail()
        self._apply_lang()
        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self.after(100, self._tick)

    # ---------- 多語系 ----------
    def _T(self, cls, parent, key, **kw):
        """建立帶文字的元件,並登記到語言切換清單。"""
        w = cls(parent, text=tr(key), **kw)
        self._i18n.append((w, key))
        return w

    def _toggle_lang(self):
        set_lang("en" if LANG == "zh" else "zh")
        try:   # 只更新語言欄位,其餘設定保持原樣
            try:
                with open(CONFIG_PATH, encoding="utf-8") as f:
                    data = json.load(f)
            except (OSError, ValueError):
                data = {}
            data["language"] = LANG
            with open(CONFIG_PATH, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except OSError:
            pass
        self._apply_lang()

    def _apply_lang(self):
        self.title(f"{tr('app_title')} v{APP_VERSION}")
        for w, key in self._i18n:
            w.configure(text=tr(key))
        self.btn_lang.configure(text="ENG" if LANG == "zh" else "中文")
        for r in self.sched_rows:
            r.relabel()
        self._refresh_sched_buttons()
        cur = self._rot_key()
        self.opt_rot.configure(values=[tr("rot_" + k) for k in ROT_KEYS])
        self.v_rot.set(tr("rot_" + cur))
        self._sync_buttons()
        if not (self.worker and self.worker.is_alive()):
            self._set_status("st_idle", C_GRAY)
            self._show_message(tr("ph_preview"))
        self._refresh_files()

    def _rot_key(self):
        shown = self.v_rot.get()
        for k in ROT_KEYS:
            # 目前語言 / 另一語言的名稱都接受 (切換語言前後皆可對應)
            if shown in STR["rot_" + k]:
                return k
        return "none"

    # ---------- 版面 ----------
    def _build_header(self):
        bar = ctk.CTkFrame(self, fg_color=C_HEADER, corner_radius=0, height=66)
        bar.grid(row=0, column=0, columnspan=2, sticky="ew")
        bar.grid_propagate(False)
        logo = ctk.CTkFrame(bar, fg_color="white", corner_radius=10, width=42, height=42)
        logo.place(x=16, rely=0.5, anchor="w")
        ctk.CTkLabel(logo, text="◉", font=F(24, True), text_color=C_HEADER).place(relx=.5, rely=.5, anchor="center")
        self._T(ctk.CTkLabel, bar, "app_title", font=F(21, True), text_color="white").place(x=70, y=8)
        self._T(ctk.CTkLabel, bar, "app_sub", font=F(11), text_color="#b9cdea").place(x=71, y=38)
        self.btn_lang = ctk.CTkButton(bar, text="ENG", width=76, height=34, font=F(17, True), fg_color="transparent",
                                      hover_color="#1b4a86", text_color=C_LANG, command=self._toggle_lang)
        self.btn_lang.place(relx=1.0, x=-16, rely=0.5, anchor="e")

    def _build_sidebar(self):
        side = ctk.CTkFrame(self, fg_color=C_SIDEBAR, corner_radius=0, width=160)
        side.grid(row=1, column=0, sticky="ns")
        side.grid_propagate(False)
        self.nav = {}
        for i, (key, label) in enumerate((("monitor", "nav_monitor"), ("files", "nav_files"), ("about", "nav_about"))):
            b = self._T(ctk.CTkButton, side, label, anchor="w", height=42, corner_radius=8, font=F(14),
                        fg_color="transparent", hover_color="#1b4a86", text_color="white",
                        command=lambda k=key: self._show_page(k))
            b.pack(fill="x", padx=8, pady=(14 if i == 0 else 3, 0))
            self.nav[key] = b

    def _add_sched(self, sched=None):
        if len(self.sched_rows) >= MAX_SCHEDULES:
            return
        sched = sched or {"start": "08:00", "end": "17:00", "days": list(range(7))}
        r = ScheduleRow(self.sched_box, sched, self._del_sched)
        r.pack(fill="x", pady=2)
        self.sched_rows.append(r)
        self._refresh_sched_buttons()

    def _del_sched(self, row):
        if len(self.sched_rows) <= 1:
            return
        self.sched_rows.remove(row)
        row.destroy()
        self._refresh_sched_buttons()

    def _refresh_sched_buttons(self):
        for r in self.sched_rows:
            r.set_deletable(len(self.sched_rows) > 1)
        if hasattr(self, "btn_add"):
            full = len(self.sched_rows) >= MAX_SCHEDULES
            self.btn_add.configure(state="disabled" if full else "normal", text=tr("sched_full" if full else "sched_add"))

    def _show_page(self, key):
        self.pages[key].tkraise()
        for k, b in self.nav.items():
            b.configure(fg_color=C_ACTIVE if k == key else "transparent")
        if key == "files":
            self._refresh_files()

    def _card(self, master, **kw):
        return ctk.CTkFrame(master, fg_color=C_CARD, corner_radius=12, border_width=1, border_color=C_BORDER, **kw)

    def _build_monitor(self, page):
        c = self.cfg
        page.grid_columnconfigure(1, weight=1)
        page.grid_rowconfigure(0, weight=1)
        self.v_sched = ctk.BooleanVar(value=c["schedule_enabled"])
        self.v_cam = ctk.StringVar(value=str(c["camera_index"]))
        self.v_sens = ctk.StringVar(value=f"{c['sensitivity']:g}")
        self.v_post = ctk.StringVar(value=str(c["post_seconds"]))
        self.v_pre = ctk.StringVar(value=str(c["pre_seconds"]))
        self.v_rot = ctk.StringVar(value=tr("rot_" + c["rotation"]))
        self.v_dir = ctk.StringVar(value=c["output_dir"])

        # ---- 左欄 ----
        left = ctk.CTkFrame(page, fg_color="transparent", width=382)
        left.grid(row=0, column=0, sticky="ns", padx=(0, 12))
        left.pack_propagate(False)
        card = self._card(left)
        card.pack(fill="x")
        card.grid_columnconfigure(0, weight=1)
        self._T(ctk.CTkLabel, card, "settings", font=F(16, True), text_color=C_TEXT).grid(
            row=0, column=0, columnspan=2, sticky="w", padx=14, pady=(12, 4))
        self._T(ctk.CTkCheckBox, card, "sched_enable", variable=self.v_sched, font=F(12), text_color=C_TEXT,
                checkbox_width=18, checkbox_height=18).grid(row=1, column=0, columnspan=2, sticky="w", padx=14, pady=(0, 4))

        def row(r, key, widget):
            self._T(ctk.CTkLabel, card, key, font=F(13), text_color=C_TEXT).grid(row=r, column=0, sticky="w", padx=(14, 0), pady=3)
            widget.grid(row=r, column=1, sticky="e", padx=(0, 14), pady=3)

        # 多排程:每列 = 開始~結束 + 星期勾選
        self.sched_box = ctk.CTkFrame(card, fg_color="transparent")
        self.sched_box.grid(row=2, column=0, columnspan=2, sticky="ew", padx=12)
        self.sched_rows = []
        for s in c["schedules"][:MAX_SCHEDULES]:
            self._add_sched(s)
        addrow = ctk.CTkFrame(card, fg_color="transparent")
        addrow.grid(row=3, column=0, columnspan=2, sticky="ew", padx=14, pady=(2, 2))
        self.btn_add = ctk.CTkButton(addrow, text=tr("sched_add"), width=110, height=26, font=F(12), fg_color="#e6effc", text_color="#1d4f9a",
                                     hover_color="#d3e3fa", command=self._add_sched)
        self.btn_add.pack(side="left")
        self._T(ctk.CTkLabel, addrow, "sched_hint", font=F(11), text_color=C_MUTED).pack(side="left", padx=8)
        self._refresh_sched_buttons()
        row(5, "cam_index", Spin(card, self.v_cam, 0, 9, 1))
        row(6, "sens", Spin(card, self.v_sens, 0.05, 50, 0.1, digits=2))
        row(7, "post", Spin(card, self.v_post, 0, 300, 1))
        row(8, "pre", Spin(card, self.v_pre, 0, 10, 1))
        self.opt_rot = ctk.CTkOptionMenu(card, variable=self.v_rot, values=[tr("rot_" + k) for k in ROT_KEYS], width=150, height=30,
                                         font=F(13), dropdown_font=F(13), fg_color="white", text_color=C_TEXT, button_color="#eef2f8",
                                         button_hover_color="#dbe3ee", command=self._on_rotation)
        row(9, "rotation", self.opt_rot)
        self._T(ctk.CTkLabel, card, "save_dir", font=F(12, True), text_color=C_TEXT).grid(
            row=10, column=0, columnspan=2, sticky="w", padx=14, pady=(8, 0))
        drow = ctk.CTkFrame(card, fg_color="transparent")
        drow.grid(row=11, column=0, columnspan=2, sticky="ew", padx=14, pady=2)
        drow.grid_columnconfigure(0, weight=1)
        ctk.CTkEntry(drow, textvariable=self.v_dir, height=30, fg_color="white", border_color=C_BORDER, font=F(12)).grid(row=0, column=0, sticky="ew")
        self._T(ctk.CTkButton, drow, "open", width=50, height=30, font=F(12), fg_color="#eef2f8", text_color=C_TEXT, hover_color="#dbe3ee",
                command=lambda: os.startfile(self._ensure_dir())).grid(row=0, column=1, padx=(4, 0))
        soft = dict(height=32, font=F(13), fg_color="#e6effc", text_color="#1d4f9a", hover_color="#d3e3fa", border_width=1, border_color="#bcd2f3")
        self._T(ctk.CTkButton, card, "purge_btn", command=self._purge_old, **soft).grid(
            row=13, column=0, columnspan=2, sticky="ew", padx=14, pady=(6, 2))
        self.btn_prev = ctk.CTkButton(card, text=tr("preview_btn"), command=self._toggle_preview, **soft)
        self.btn_prev.grid(row=14, column=0, columnspan=2, sticky="ew", padx=14, pady=(2, 12))

        stat = ctk.CTkFrame(left, fg_color="#e3f1ea", corner_radius=10, height=46)
        stat.pack(fill="x", pady=(10, 0))
        stat.pack_propagate(False)
        self.dot_status = ctk.CTkLabel(stat, text="●", font=F(14), text_color=C_GRAY)
        self.dot_status.pack(side="left", padx=(12, 4))
        self.lbl_status = ctk.CTkLabel(stat, text=tr("st_idle"), font=F(13, True), text_color=C_TEXT)
        self.lbl_status.pack(side="left")
        self.btn_pause = ctk.CTkButton(stat, text=tr("pause"), width=70, height=28, corner_radius=14, font=F(12, True),
                                       border_width=1, command=self._toggle_pause)
        self.btn_pause.pack(side="right", padx=10)
        self.btn = ctk.CTkButton(left, text=tr("start_btn"), height=44, corner_radius=8, font=F(15, True), text_color="white",
                                 text_color_disabled="#e8e8e8", command=self._toggle)
        self.btn.pack(fill="x", pady=(10, 0))
        cnt = self._card(left)
        cnt.pack(fill="x", pady=(10, 0))
        self._T(ctk.CTkLabel, cnt, "count", font=F(14, True), text_color=C_TEXT).pack(side="left", padx=14, pady=12)
        self.lbl_count = ctk.CTkLabel(cnt, text="0", font=F(20, True), text_color=C_TEXT)
        self.lbl_count.pack(side="right", padx=18)
        self._sync_buttons()

        # ---- 右欄 ----
        right = ctk.CTkFrame(page, fg_color="transparent")
        right.grid(row=0, column=1, sticky="nsew")
        right.grid_columnconfigure(0, weight=1)
        right.grid_rowconfigure(0, weight=3)
        right.grid_rowconfigure(1, weight=2)
        self.video = ctk.CTkFrame(right, fg_color="#0b0f14", corner_radius=12, border_width=3, border_color="#2f6fe4")
        self.video.grid(row=0, column=0, sticky="nsew", pady=(0, 12))
        self.video.pack_propagate(False)
        self._blank = ctk.CTkImage(Image.new("RGB", (1, 1)), size=(1, 1))
        self.lbl_video = ctk.CTkLabel(self.video, text="", image=self._blank, font=F(14), text_color="#9aa7b8")
        self.lbl_video.pack(expand=True)
        self.lbl_cd = ctk.CTkLabel(self.video, text="", font=F(46, True), text_color="#35d07f")
        self.badge = ctk.CTkFrame(self.video, fg_color="#1b2430", corner_radius=8)
        self.badge_dot = ctk.CTkLabel(self.badge, text="●", font=F(24), text_color=C_RED)
        self.badge_dot.pack(side="left", padx=(14, 4), pady=6)
        self.badge_txt = ctk.CTkLabel(self.badge, text="", font=F(24, True), text_color="white")
        self.badge_txt.pack(side="left", padx=(0, 14))
        self.lbl_res = ctk.CTkLabel(self.video, text="", font=F(12, True), text_color="white", fg_color="#1b2430", corner_radius=6)

        logcard = self._card(right)
        logcard.grid(row=1, column=0, sticky="nsew")
        logcard.grid_columnconfigure(0, weight=1)
        logcard.grid_rowconfigure(1, weight=1)
        self._T(ctk.CTkLabel, logcard, "log_title", font=F(16, True), text_color=C_TEXT).grid(row=0, column=0, sticky="w", padx=14, pady=(10, 2))
        self._T(ctk.CTkButton, logcard, "log_clear", width=100, height=28, font=F(12), command=self._clear_log, fg_color="#eef2f8",
                text_color=C_TEXT, hover_color="#dbe3ee").grid(row=0, column=1, padx=12, pady=(10, 2))
        self.logbox = ctk.CTkScrollableFrame(logcard, fg_color="transparent")
        self.logbox.grid(row=1, column=0, columnspan=2, sticky="nsew", padx=6, pady=(0, 8))

    def _build_files(self, page):
        page.grid_columnconfigure(0, weight=1)
        page.grid_rowconfigure(1, weight=1)
        top = ctk.CTkFrame(page, fg_color="transparent")
        top.grid(row=0, column=0, sticky="ew", pady=(0, 10))
        self._T(ctk.CTkLabel, top, "files_title", font=F(20, True), text_color=C_TEXT).pack(side="left")
        self.lbl_files = ctk.CTkLabel(top, text="", font=F(13), text_color=C_MUTED)
        self.lbl_files.pack(side="left", padx=14)
        for key, cmd in (("files_open", lambda: os.startfile(self._ensure_dir())), ("files_refresh", self._refresh_files)):
            self._T(ctk.CTkButton, top, key, width=120, height=32, font=F(13), command=cmd, fg_color=C_ACTIVE).pack(side="right", padx=(8, 0))
        card = self._card(page)
        card.grid(row=1, column=0, sticky="nsew")
        card.grid_columnconfigure(0, weight=1)
        card.grid_rowconfigure(0, weight=1)
        self.filelist = ctk.CTkScrollableFrame(card, fg_color="transparent")
        self.filelist.grid(row=0, column=0, sticky="nsew", padx=6, pady=6)
        self.filelist.grid_columnconfigure(0, weight=1)

    def _build_about(self, page):
        card = self._card(page)
        card.pack(anchor="nw", fill="x")
        self._T(ctk.CTkLabel, card, "app_title", font=F(24, True), text_color=C_TEXT).pack(anchor="w", padx=24, pady=(22, 0))
        self._T(ctk.CTkLabel, card, "app_sub", font=F(13), text_color=C_MUTED).pack(anchor="w", padx=24)
        for key, val in (("about_version", f"v{APP_VERSION}"), ("about_date", BUILD_DATE), ("about_author", AUTHOR)):
            r = ctk.CTkFrame(card, fg_color="transparent")
            r.pack(anchor="w", padx=24, pady=(14, 0))
            self._T(ctk.CTkLabel, r, key, width=80, anchor="w", font=F(15), text_color=C_MUTED).pack(side="left")
            ctk.CTkLabel(r, text=val, font=F(16, True), text_color=C_TEXT).pack(side="left")
        self._T(ctk.CTkLabel, card, "about_desc", font=F(13), text_color=C_TEXT, wraplength=620, justify="left").pack(
            anchor="w", padx=24, pady=(18, 22))

    # ---------- Log ----------
    def _log_sink(self, line):
        self.after(0, self._append_log, line)

    def _append_log(self, line):
        parts = line.split(" | ")
        event = parts[1] if len(parts) > 1 else ""
        green = {STR[k][i] for k in ("ev_rec_start", "ev_rec_end") for i in (0, 1)}
        red = {STR["ev_error"][0], STR["ev_error"][1]}
        color = C_GREEN if event in green else C_RED if event in red else C_BLUE
        r = ctk.CTkFrame(self.logbox, fg_color="transparent")
        r.pack(fill="x")
        ctk.CTkLabel(r, text="●", font=F(11), text_color=color, width=18).pack(side="left")
        ctk.CTkLabel(r, text=line, font=F(12), text_color=C_TEXT, anchor="w").pack(side="left", padx=4, pady=1)
        kids = self.logbox.winfo_children()
        for old in kids[:-300]:
            old.destroy()
        self.after(80, self._scroll_log)

    def _scroll_log(self):
        """捲到最新一筆;內容不滿一頁時回到頂端 (避免捲過頭而顯示空白)。"""
        try:
            self.logbox.update_idletasks()
            canvas = self.logbox._parent_canvas
            bbox = canvas.bbox("all")
            full = bbox and (bbox[3] - bbox[1]) > canvas.winfo_height()
            canvas.yview_moveto(1.0 if full else 0.0)
        except Exception:
            pass

    def _load_log_tail(self):
        try:
            with open(self.logger.path, encoding="utf-8") as f:
                for line in f.readlines()[-50:]:
                    self._append_log(line.rstrip())
        except OSError:
            pass

    def _clear_log(self):
        if not messagebox.askyesno(tr("log_clear_title"), tr("log_clear_ask")):
            return
        with self.logger.lock:
            open(self.logger.path, "w", encoding="utf-8").close()
        for w in self.logbox.winfo_children():
            w.destroy()

    # ---------- 錄影檔 ----------
    def _ensure_dir(self):
        d = self.v_dir.get()
        os.makedirs(d, exist_ok=True)
        return d

    def _list_recordings(self):
        d = self.v_dir.get()
        try:
            names = [n for n in os.listdir(d) if n.lower().endswith(".mp4")]
        except OSError:
            return []
        items = []
        for n in names:
            p = os.path.join(d, n)
            try:
                st = os.stat(p)
            except OSError:
                continue
            items.append((p, st.st_mtime, st.st_size))
        return sorted(items, key=lambda x: x[1], reverse=True)

    def _refresh_files(self):
        for w in self.filelist.winfo_children():
            w.destroy()
        items = self._list_recordings()
        total = sum(i[2] for i in items) / 1048576
        self.lbl_files.configure(text=tr("files_summary", n=len(items), mb=total))
        if not items:
            ctk.CTkLabel(self.filelist, text=tr("files_none"), font=F(14), text_color=C_MUTED).grid(row=0, column=0, pady=30)
        for i, (p, mt, size) in enumerate(items[:300]):
            r = ctk.CTkFrame(self.filelist, fg_color="#f5f8fc" if i % 2 == 0 else "transparent", corner_radius=6)
            r.grid(row=i, column=0, sticky="ew", pady=1)
            r.grid_columnconfigure(0, weight=1)
            ctk.CTkLabel(r, text=os.path.basename(p), font=F(13), text_color=C_TEXT, anchor="w").grid(row=0, column=0, sticky="w", padx=10, pady=6)
            ctk.CTkLabel(r, text=f"{datetime.fromtimestamp(mt):%Y-%m-%d %H:%M:%S}", font=F(12), text_color=C_MUTED).grid(row=0, column=1, padx=8)
            ctk.CTkLabel(r, text=f"{size / 1048576:.1f} MB", font=F(12), text_color=C_MUTED, width=70, anchor="e").grid(row=0, column=2, padx=8)
            ctk.CTkButton(r, text=tr("play"), width=60, height=28, font=F(12), fg_color=C_ACTIVE, command=lambda p=p: os.startfile(p)).grid(row=0, column=3, padx=4)
            ctk.CTkButton(r, text=tr("delete"), width=60, height=28, font=F(12), fg_color=C_RED, hover_color="#b82c2c",
                          command=lambda p=p: self._delete_file(p)).grid(row=0, column=4, padx=(0, 8))

    def _delete_file(self, path):
        if self.worker and self.worker.recording and abs(os.path.getmtime(path) - time.time()) < 5:
            messagebox.showinfo(tr("del_busy_t"), tr("del_busy"))
            return
        if messagebox.askyesno(tr("del_ask_t"), tr("del_ask", f=os.path.basename(path))):
            try:
                os.remove(path)
            except OSError as e:
                messagebox.showerror(tr("del_fail"), str(e))
            self._refresh_files()

    def _purge_old(self):
        dlg = ctk.CTkInputDialog(text=tr("purge_ask_days"), title=tr("purge_title"))
        ans = dlg.get_input()
        if ans is None:
            return
        try:
            days = int(ans)
            if days < 1:
                raise ValueError
        except ValueError:
            messagebox.showerror(tr("input_err_t"), tr("input_err"))
            return
        cutoff = time.time() - days * 86400
        old = [i for i in self._list_recordings() if i[1] < cutoff]
        if not old:
            messagebox.showinfo(tr("purge_title"), tr("purge_none", d=days))
            return
        mb = sum(i[2] for i in old) / 1048576
        if not messagebox.askyesno(tr("purge_title"), tr("purge_confirm", n=len(old), d=days, mb=mb)):
            return
        n = 0
        for p, _, _ in old:
            try:
                os.remove(p)
                n += 1
            except OSError:
                pass
        self.logger.write("ev_purge", tr("d_purged", n=n, d=days))
        self._refresh_files()

    # ---------- 控制 ----------
    def _collect_cfg(self):
        schedules = []
        for i, r in enumerate(self.sched_rows, 1):
            s = r.get()
            try:
                parse_hhmm(s["start"])
                parse_hhmm(s["end"])
            except ValueError as e:
                raise ValueError(tr("err_sched_n", i=i, e=e))
            if not s["days"]:
                raise ValueError(tr("err_days", i=i))
            schedules.append(s)
        try:
            cam, post, pre = int(self.v_cam.get()), int(self.v_post.get()), int(self.v_pre.get())
            sens = float(self.v_sens.get())
        except ValueError:
            raise ValueError(tr("err_num"))
        if sens <= 0 or post < 0 or pre < 0 or cam < 0:
            raise ValueError(tr("err_neg"))
        return {
            "language": LANG,
            "camera_index": cam,
            "schedule_enabled": self.v_sched.get(),
            "schedules": schedules,
            "sensitivity": sens,
            "post_seconds": post,
            "pre_seconds": pre,
            "rotation": self._rot_key(),
            "output_dir": self.v_dir.get(),
        }

    def _on_rotation(self, _value=None):
        if self.worker and self.worker.is_alive():
            self.worker.cfg["rotation"] = self._rot_key()

    def _sync_buttons(self):
        """依目前狀態 (閒置 / 監控中 / 預覽中) 重設三顆按鈕的文字與樣式。"""
        w = self.worker if (self.worker and self.worker.is_alive()) else None
        preview = bool(w and w.cfg.get("preview_only"))
        monitoring = bool(w and not preview)
        if monitoring:
            self.btn.configure(text=tr("stop_btn"), fg_color=C_RED, hover_color="#b82c2c", state="normal")
        elif preview:
            self.btn.configure(text=tr("start_btn"), fg_color="#9db7a8", hover_color="#9db7a8", state="disabled")
        else:
            self.btn.configure(text=tr("start_btn"), fg_color=C_GREEN, hover_color="#237a46", state="normal")
        self.btn_prev.configure(text=tr("preview_stop" if preview else "preview_btn"), state="disabled" if monitoring else "normal")
        self._style_pause(enabled=monitoring, paused=bool(w and w.paused))

    def _style_pause(self, enabled, paused=False):
        if not enabled:
            self.btn_pause.configure(text=tr("pause"), state="disabled", fg_color="transparent", border_color="#b9c4d0", text_color_disabled="#9aa7b8")
        elif paused:
            self.btn_pause.configure(text=tr("resume"), state="normal", fg_color=C_ORANGE, hover_color="#cf7a1c", border_color=C_ORANGE, text_color="white")
        else:
            self.btn_pause.configure(text=tr("pause"), state="normal", fg_color="white", hover_color="#fdeedb", border_color=C_ORANGE, text_color="#c2700f")

    def _toggle_pause(self):
        w = self.worker
        if w and w.is_alive() and not w.cfg.get("preview_only"):
            w.paused = not w.paused
            self._style_pause(enabled=True, paused=w.paused)
            self.logger.write("ev_pause" if w.paused else "ev_resume")

    def _toggle_preview(self):
        if self.worker and self.worker.is_alive():
            self._stop()
            return
        try:
            cfg = self._collect_cfg()
        except ValueError as e:
            messagebox.showerror(tr("cfg_err"), str(e))
            return
        cfg["preview_only"] = True
        self.worker = Worker(cfg, self.logger)
        self.worker.start()
        self._sync_buttons()

    def _toggle(self):
        if self.worker and self.worker.is_alive():
            self._stop()
            return
        try:
            self.cfg = self._collect_cfg()
        except ValueError as e:
            messagebox.showerror(tr("cfg_err"), str(e))
            return
        with open(CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(self.cfg, f, ensure_ascii=False, indent=2)
        self.logger.write("ev_mon_start", tr("ev_schedule", s=describe_schedules(self.cfg["schedules"])) if self.cfg["schedule_enabled"] else tr("ev_always"))
        self.worker = Worker(self.cfg, self.logger)
        self.worker.start()
        self._sync_buttons()

    def _stop(self, done=None):
        """通知背景執行緒停止,等它存完檔再還原 UI;等待期間顯示提示視窗。"""
        w = self.worker
        if not w:
            self._reset_ui()
            if done:
                done()
            return
        w.stop_evt.set()
        self.btn.configure(state="disabled")
        self.btn_prev.configure(state="disabled")
        self.btn_pause.configure(state="disabled")
        self.btn_lang.configure(state="disabled")

        popup = ctk.CTkToplevel(self, fg_color="white")
        popup.title(tr("wait_title"))
        popup.resizable(False, False)
        popup.transient(self)
        ctk.CTkLabel(popup, text=tr("saving"), font=F(16, True), text_color=C_TEXT).pack(padx=50, pady=32)
        popup.protocol("WM_DELETE_WINDOW", lambda: None)
        self.update_idletasks()
        popup.update_idletasks()
        pw, ph = max(popup.winfo_reqwidth(), 280), max(popup.winfo_reqheight(), 96)
        popup.geometry(f"{pw}x{ph}+{self.winfo_rootx() + (self.winfo_width() - pw) // 2}+{self.winfo_rooty() + self.winfo_height() // 3}")
        popup.after(120, lambda: (popup.lift(), popup.focus(), popup.grab_set()))

        def poll():
            if w.is_alive():
                self.after(100, poll)
                return
            popup.destroy()
            if not w.cfg.get("preview_only"):
                self.logger.write("ev_mon_stop")
            self.worker = None
            self.btn_lang.configure(state="normal")
            self._reset_ui()
            if done:
                done()

        poll()

    def _reset_ui(self):
        self._sync_buttons()
        self._set_status("st_idle", C_GRAY)
        self._show_message(tr("ph_preview"))

    # ---------- 畫面更新 ----------
    def _set_status(self, key, color):
        self.lbl_status.configure(text=tr(key))
        self.dot_status.configure(text_color=color)

    def _show_message(self, msg):
        self.lbl_video.configure(image=self._blank, text=msg)
        self.badge.place_forget()
        self.lbl_res.place_forget()
        self.lbl_cd.place_forget()

    def _show_countdown(self, schedules):
        """排程時段外:以綠色大字顯示距離下一次偵測啟動 (所有時段中最近的一個) 的倒數。"""
        now = datetime.now()
        nxt = next_start(now, schedules)
        if nxt is None:
            self._show_message(tr("ph_outside_short"))
            return
        secs = int((nxt - now).total_seconds())
        h, rem = divmod(secs, 3600)
        m, s = divmod(rem, 60)
        self._show_message(tr("ph_outside"))
        self.lbl_cd.configure(text=f"{tr('countdown')} {h:02d}:{m:02d}:{s:02d}")
        self.lbl_cd.place(relx=0.5, rely=0.36, anchor="center")

    def _tick(self):
        w = self.worker
        if w and w.is_alive():
            st = w.status
            color = mix(C_STATUS_BG, C_RED, breath()) if w.recording else C_GREEN if st in ("st_nomotion", "st_rec", "st_preview") else C_ORANGE
            self._set_status(st, color)
            self.lbl_count.configure(text=str(w.rec_count))
            fr = w.frame
            if fr is not None:
                self._show_frame(fr, w)
            elif st == "st_wait":
                self._show_countdown(w.cfg["schedules"])
            else:
                self._show_message(tr("ph_starting"))
        self.after(66, self._tick)

    def _show_frame(self, fr, w):
        h, wd = fr.shape[:2]
        bw, bh = max(self.video.winfo_width() - 16, 100), max(self.video.winfo_height() - 16, 100)
        scale = min(bw / wd, bh / h)
        size = (max(int(wd * scale), 1), max(int(h * scale), 1))
        img = Image.fromarray(cv2.cvtColor(fr, cv2.COLOR_BGR2RGB))
        self._img = ctk.CTkImage(img, size=size)
        self.lbl_video.configure(image=self._img, text="")
        self.lbl_cd.place_forget()   # 有即時畫面時不顯示倒數
        if w.cfg.get("preview_only"):
            dot, txt = C_BLUE, tr("bd_preview")
        elif w.paused:
            dot, txt = C_ORANGE, tr("bd_paused")
        elif w.recording:
            dot, txt = mix(C_BADGE_BG, C_RED, breath()), tr("bd_rec")
        else:
            dot, txt = C_GREEN, tr("bd_detect")
        self.badge_dot.configure(text_color=dot)
        self.badge_txt.configure(text=txt)
        self.badge.place(x=14, y=14)
        self.lbl_res.configure(text=f" {wd}×{h} ")
        self.lbl_res.place(x=14, rely=1.0, y=-14, anchor="sw")

    def _on_close(self):
        self._stop(done=self.destroy)


if __name__ == "__main__":
    App().mainloop()
