# Bulk YouTube Acquisition Tool
# Developer: Joshua C Brooks
# Github https://github.com/MyStiKal-SOul/TubeHoarder
# Version: 2.0.0
# Last update: 2/14/2026

import os
import sys
import hashlib
import datetime
import threading
import queue
import json
import shutil
import urllib.request
import webbrowser
from concurrent.futures import ThreadPoolExecutor, as_completed

import tkinter as tk
from tkinter import ttk, messagebox, filedialog

try:
    import pyi_splash  # type: ignore
except Exception:
    pyi_splash = None

from yt_dlp import YoutubeDL

settingFile = "settings.json"
UIQueue = queue.Queue()
logLock = threading.Lock()

def utcStamp() -> str:
    return datetime.datetime.utcnow().strftime("%Y-%m-%d %H:%M:%SZ")

def getBasePath():
    if hasattr(sys, "_MEIPASS"):
        return sys._MEIPASS
    return os.path.abspath(".")

def rsrc(name: str) -> str:
    return os.path.join(getBasePath(), name)

def ffmpegPath():
    base = getBasePath()
    bundled = os.path.join(base, "ffmpeg")

    if os.path.exists(os.path.join(bundled, "ffmpeg.exe")):
        return bundled

    if shutil.which("ffmpeg"):
        return None

    return False

def loadSettings():
    if os.path.exists(settingFile):
        with open(settingFile, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}

def saveSetting(data):
    with open(settingFile, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4)


def sha256Hash(path, chunk=8192):
    sha = hashlib.sha256()
    with open(path, "rb") as f:
        while block := f.read(chunk):
            sha.update(block)
    return sha.hexdigest()

def downloadThumbnail(thumbnailUrl, savePath):
    try:
        with urllib.request.urlopen(thumbnailUrl, timeout=15) as response:
            with open(savePath, "wb") as f:
                f.write(response.read())
        return True
    except Exception:
        return False

def checkIPaddress():
    sources = [
        "https://api.ipify.org",
        "https://checkip.amazonaws.com",
    ]
    ips = []
    for url in sources:
        try:
            with urllib.request.urlopen(url, timeout=5) as r:
                ips.append(r.read().decode().strip())
        except Exception:
            ips.append("ERROR")
    return ips

def createHTMLlog(logPath, case, ip1, ip2, ipStatus):
    with open(logPath, "w", encoding="utf-8") as log:
        log.write(
            f"""<!DOCTYPE html>
<html>
<head>
<meta charset="UTF-8">
<title>Case Report - {case}</title>
<style>
body {{ font-family: Arial; background:#111; color:#eee; padding:20px; }}
table {{ width:100%; border-collapse:collapse; background:#1b1b1b; }}
th, td {{ border:1px solid #333; padding:8px; vertical-align:top; }}
th {{ background:#e53935; color:white; }}
a {{ color:#ffd166; }}
.verified {{ color:#66ff99; font-weight:bold; }}
.failed {{ color:#ff5c5c; font-weight:bold; }}
.hash {{ font-family:monospace; font-size:12px; word-break:break-all; }}
.meta {{ margin-bottom:20px; padding:12px; background:#1b1b1b; border:1px solid #333; border-radius:8px; }}
.small {{ color:#bdbdbd; font-size:12px; }}
</style>
</head>
<body>
<h1>Bulk YouTube Acquisition Report</h1>

<div class="meta">
<strong>Case:</strong> {case}<br>
<strong>Start (UTC):</strong> {utcStamp()}<br>
<strong>Public IP by https://api.ipify.org:</strong> {ip1}<br>
<strong>Public IP by https://checkip.amazonaws.com:</strong> {ip2}<br>
<strong>IP Verification:</strong> {ipStatus}
</div>

<table>
<tr>
<th>Timestamp (UTC)</th>
<th>Thumbnail</th>
<th>Video Title</th>
<th>Source URL</th>
<th>Status</th>
<th>Video SHA256</th>
</tr>
"""
        )

def closeHTMLlog(logPath):
    with open(logPath, "a", encoding="utf-8") as log:
        log.write(
            f"""
</table>
<br><br>
<strong>End (UTC):</strong> {utcStamp()}
</body>
</html>
"""
        )

def toRelHref(targetPath: str, base_dir: str) -> str:
    rel = os.path.relpath(targetPath, start=base_dir)
    return rel.replace("\\", "/")

def processVideo(url, videoDir, thumbDir, logFile, case):
    def hook(d):
        if d.get("status") == "downloading":
            percent = d.get("_percent_str", "0%").replace("%", "").strip()
            try:
                percent = float(percent)
            except Exception:
                percent = 0.0
            UIQueue.put((url, "PROGRESS", percent))
        elif d.get("status") == "finished":
            UIQueue.put((url, "MERGING", 99.0))

    try:
        ffmpegStatus = ffmpegPath()

        ydlOpts = {
            "outtmpl": os.path.join(videoDir, f"{case}_%(title)s.%(ext)s"),
            "progress_hooks": [hook],
            "quiet": True,
            "no_warnings": True,
        }

        if ffmpegStatus is False:
            ydlOpts["format"] = "best"
        else:
            ydlOpts["format"] = "bestvideo+bestaudio/best"
            ydlOpts["merge_output_format"] = "mp4"
            if ffmpegStatus:
                ydlOpts["ffmpeg_location"] = ffmpegStatus

        with YoutubeDL(ydlOpts) as ydl:
            info = ydl.extract_info(url, download=True)
            temp_path = ydl.prepare_filename(info)

        videoTitle = info.get("title", "UNKNOWN_TITLE")
        videoID = info.get("id", "unknownid")
        thumbnailURL = info.get("thumbnail")

        thumbFilename = f"{videoID}_thumbnail.jpg"
        thumbPath = os.path.join(thumbDir, thumbFilename)

        if thumbnailURL:
            downloadThumbnail(thumbnailURL, thumbPath)


        hash1 = sha256Hash(temp_path) # Hash b4 move (source temp path)

        finalPath = os.path.join(videoDir, os.path.basename(temp_path))
        shutil.move(temp_path, finalPath)

        hash2 = sha256Hash(finalPath)

        status = "VERIFIED" if hash1 == hash2 else "HASH_MISMATCH"
        css_class = "verified" if status == "VERIFIED" else "failed"

        report_dir = os.path.dirname(logFile)
        video_href = toRelHref(finalPath, report_dir)

        with logLock:
            with open(logFile, "a", encoding="utf-8") as log:
                log.write(
                    f"""
<tr>
<td>{utcStamp()}</td>
<td><img src="Thumbnails/{thumbFilename}" width="160"></td>
<td><a href="{video_href}" target="_blank">{videoTitle}</a><div class="small">({os.path.basename(finalPath)})</div></td>
<td><a href="{url}" target="_blank">{url}</a></td>
<td class="{css_class}">{status}</td>
<td class="hash">{hash2}</td>
</tr>
"""
                )

        UIQueue.put((url, "DONE", hash2))

    except Exception as e:
        with logLock:
            with open(logFile, "a", encoding="utf-8") as log:
                log.write(
                    f"""
<tr>
<td>{utcStamp()}</td>
<td>N/A</td>
<td>UNKNOWN_TITLE</td>
<td>{url}</td>
<td class="failed">FAILED</td>
<td>{str(e)}</td>
</tr>
"""
                )
        UIQueue.put((url, "FAILED", str(e)))

class App:

    BG = "#0E0E0E"
    PANEL = "#121212"
    PANEL2 = "#161616"
    FG = "#F2F2F2"
    MUTED = "#BDBDBD"
    ACCENT = "#E53935"
    ACCENT2 = "#FFD166"

    WIKI_URL = "https://github.com/MyStiKal-SOul/TubeHoarder/wiki"

    def __init__(self, root):
        self.root = root
        self.root.title("TubeHoarder — Bulk YouTube Acquisition Tool (2026)")
        self.root.geometry("1100x720")
        self.root.minsize(980, 640)
        self.root.configure(bg=self.BG)

        self.settings = loadSettings()
        self.executor = None
        self.futures = []
        self.total_items = 0
        self.done_items = 0
        self.failed_items = 0

        self._local_splash = None
        self._splash_img = None
        self.localSplash()

        self.setupTheme()
        self.loadBranding()
        self.buildUI()
        self.updatingUI()

        self.closeSplash()

    def setupTheme(self):
        style = ttk.Style()
        try:
            style.theme_use("clam")
        except Exception:
            pass

        style.configure(".", font=("Segoe UI", 10))
        style.configure("TFrame", background=self.BG)
        style.configure("Panel.TFrame", background=self.PANEL)
        style.configure("Panel2.TFrame", background=self.PANEL2)
        style.configure("TLabel", background=self.BG, foreground=self.FG)
        style.configure("Muted.TLabel", background=self.BG, foreground=self.MUTED)
        style.configure("Title.TLabel", background=self.BG, foreground=self.FG, font=("Segoe UI", 18, "bold"))
        style.configure("Badge.TLabel", background=self.BG, foreground=self.ACCENT2, font=("Segoe UI", 10, "bold"))

        style.configure("Accent.TButton", background=self.ACCENT, foreground="white", padding=(14, 10))
        style.map(
            "Accent.TButton",
            background=[("active", "#ff3b30"), ("pressed", "#c62828")],
            foreground=[("disabled", "#999")],
        )

        style.configure("TButton", padding=(10, 8))
        style.configure("TEntry", padding=6)
        style.configure("TSpinbox", padding=6)

        style.configure(
            "Treeview",
            background=self.BG,
            fieldbackground=self.BG,
            foreground=self.FG,
            rowheight=28,
            bordercolor="#1f1f1f",
            lightcolor="#1f1f1f",
            darkcolor="#1f1f1f",
        )
        style.configure(
            "Treeview.Heading",
            background=self.BG,
            foreground=self.FG,
            relief="flat",
            padding=8,
        )
        style.map("Treeview.Heading", background=[("active", self.PANEL)])

        style.configure("TProgressbar", troughcolor="#1f1f1f", background=self.ACCENT)

    def loadBranding(self):
        # Window icon
        ico = rsrc("TubeHoarder.ico")
        try:
            if os.path.exists(ico):
                self.root.iconbitmap(ico)
        except Exception:
            pass

        self.logo_img = None
        iconPath = rsrc("TubeHoarder_icon.png")

        try:
            if os.path.exists(iconPath):
                img = tk.PhotoImage(file=iconPath)

                # Resize cleanly for header
                while img.width() > 220:
                    img = img.subsample(2, 2)

                self.logo_img = img
        except Exception:
            self.logo_img = None

    def localSplash(self):
        if pyi_splash is not None:
            try:
                pyi_splash.update_text("Starting TubeHoarder…")
            except Exception:
                pass
            return

        splashPath = rsrc("TubeHoarder_splash.png")
        if not os.path.exists(splashPath):
            return

        try:
            top = tk.Toplevel(self.root)
            top.overrideredirect(True)
            top.attributes("-topmost", True)

            img = tk.PhotoImage(file=splashPath)
            self._splash_img = img

            w, h = img.width(), img.height()
            sw = top.winfo_screenwidth()
            sh = top.winfo_screenheight()
            x = (sw - w) // 2
            y = (sh - h) // 2
            top.geometry(f"{w}x{h}+{x}+{y}")

            lbl = tk.Label(top, image=img, bd=0, bg=self.BG)
            lbl.pack()

            self._local_splash = top
            top.update_idletasks()
        except Exception:
            self._local_splash = None

    def closeSplash(self):
        if pyi_splash is not None:
            try:
                pyi_splash.close()
            except Exception:
                pass

        if self._local_splash is not None:
            try:
                self._local_splash.destroy()
            except Exception:
                pass
            self._local_splash = None

    def buildUI(self):
        notebook = ttk.Notebook(self.root)
        notebook.pack(fill="both", expand=True)

        main = ttk.Frame(notebook)
        help_tab = ttk.Frame(notebook)

        notebook.add(main, text="Main")
        notebook.add(help_tab, text="Help")

        header = ttk.Frame(main)  # BG
        header.pack(fill="x", padx=14, pady=(14, 10))

        left = ttk.Frame(header)  # BG
        left.pack(side="left", fill="x", expand=True, padx=14, pady=12)

        if self.logo_img:
            self.header_img = self.logo_img
            tk.Label(left, image=self.header_img, bg=self.BG).pack(side="left", padx=(0, 18))

        title_box = ttk.Frame(left)  # BG
        title_box.pack(side="left", fill="x", expand=True)

        ttk.Label(title_box, text="TubeHoarder", style="Title.TLabel").pack(anchor="w")
        ttk.Label(
            title_box,
            text="Bulk YouTube Acquisition Tool • hoard responsibly",
            style="Muted.TLabel",
        ).pack(anchor="w", pady=(2, 0))

        right = ttk.Frame(header)  # BG
        right.pack(side="right", padx=14, pady=12)

        self.statusBadge = ttk.Label(right, text="IDLE", style="Badge.TLabel")
        self.statusBadge.pack(anchor="e")
        self.countLabel = ttk.Label(right, text="Queued: 0   Done: 0   Failed: 0", style="Muted.TLabel")
        self.countLabel.pack(anchor="e", pady=(4, 0))

        content = ttk.Frame(main)
        content.pack(fill="both", expand=True, padx=14, pady=(0, 14))

        left_panel = ttk.Frame(content, style="Panel.TFrame")
        left_panel.pack(side="left", fill="y", padx=(0, 10))

        right_panel = ttk.Frame(content, style="Panel.TFrame")
        right_panel.pack(side="right", fill="both", expand=True)

        pad = {"padx": 14, "pady": 8}

        ttk.Label(left_panel, text="Case Number:", style="Muted.TLabel").pack(anchor="w", **pad)
        self.caseEntry = ttk.Entry(left_panel)
        self.caseEntry.insert(0, self.settings.get("case", "CASE001"))
        self.caseEntry.pack(fill="x", padx=14)

        ttk.Label(left_panel, text="Threads (1–32):", style="Muted.TLabel").pack(anchor="w", **pad)
        self.threadPicker = tk.Spinbox(
            left_panel,
            from_=1,
            to=32,
            bg=self.PANEL2,
            fg=self.FG,
            insertbackground=self.FG,
            relief="flat",
        )
        self.threadPicker.pack(fill="x", padx=14)
        self.threadPicker.delete(0, "end")
        self.threadPicker.insert(0, self.settings.get("threads", 4))

        ttk.Label(left_panel, text="Case Destination Folder:", style="Muted.TLabel").pack(anchor="w", **pad)
        folderFrame = ttk.Frame(left_panel, style="Panel.TFrame")
        folderFrame.pack(fill="x", padx=14)

        self.destinationEntry = ttk.Entry(folderFrame)
        self.destinationEntry.pack(side="left", fill="x", expand=True)
        self.destinationEntry.insert(0, self.settings.get("destination", os.getcwd()))

        ttk.Button(folderFrame, text="Browse…", command=self.pickFolder).pack(side="right", padx=(8, 0))

        ttk.Label(left_panel, text="URLs (YouTube videos):", style="Muted.TLabel").pack(anchor="w", **pad)

        self.urlText = tk.Text(
            left_panel,
            height=10,
            bg=self.BG,
            fg=self.FG,
            insertbackground=self.FG,
            relief="flat",
            wrap="word",
        )
        self.urlText.pack(fill="both", expand=True, padx=14, pady=(0, 10))

        btnRow = ttk.Frame(left_panel, style="Panel.TFrame")
        btnRow.pack(fill="x", padx=14, pady=(0, 14))

        self.startBtn = ttk.Button(btnRow, text="🧲 Start Hoarding", style="Accent.TButton", command=self.startCase)
        self.startBtn.pack(side="left", fill="x", expand=True)

        ttk.Button(btnRow, text="Clear URLs", command=lambda: self.urlText.delete("1.0", "end")).pack(side="left", padx=8)

        topRight = ttk.Frame(right_panel, style="Panel.TFrame")
        topRight.pack(fill="x", padx=14, pady=(14, 8))

        ttk.Label(topRight, text="Acquisition Queue", style="Title.TLabel").pack(side="left")
        self.globalProgress = ttk.Progressbar(topRight, mode="determinate", maximum=100)
        self.globalProgress.pack(side="right", fill="x", expand=True, padx=(14, 0))

        treeFrame = ttk.Frame(right_panel, style="Panel.TFrame")
        treeFrame.pack(fill="both", expand=True, padx=14, pady=(0, 14))

        # Removed Format column
        self.tree = ttk.Treeview(treeFrame, columns=("Status", "Info"), show="headings")
        self.tree.heading("Status", text="Status")
        self.tree.heading("Info", text="Progress / Hash")
        self.tree.column("Status", width=160, anchor="w")
        self.tree.column("Info", width=660, anchor="w")

        vsb = ttk.Scrollbar(treeFrame, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=vsb.set)
        self.tree.pack(side="left", fill="both", expand=True)
        vsb.pack(side="right", fill="y")

        bottomBar = ttk.Frame(main, style="Panel.TFrame")
        bottomBar.pack(fill="x", padx=14, pady=(0, 14))

        self.footerLabel = ttk.Label(
            bottomBar,
            text="Tip: Paste multiple URLs (one per line). Best quality uses ffmpeg when available.",
            style="Muted.TLabel",
        )
        self.footerLabel.pack(side="left", padx=14, pady=10)

        help_outer = ttk.Frame(help_tab, style="Panel.TFrame")
        help_outer.pack(fill="both", expand=True, padx=14, pady=14)

        help_inner = ttk.Frame(help_outer)
        help_inner.pack(fill="both", expand=True, padx=18, pady=18)

        ttk.Label(help_inner, text="TubeHoarder Help", style="Title.TLabel").pack(anchor="w")
        ttk.Label(
            help_inner,
            text="Open the official wiki for usage, troubleshooting, and updates:",
            style="Muted.TLabel",
        ).pack(anchor="w", pady=(10, 12))

        ttk.Button(
            help_inner,
            text="📘 Open TubeHoarder Wiki",
            style="Accent.TButton",
            command=self.openWiki,
        ).pack(anchor="w")

        link = ttk.Label(help_inner, text=self.WIKI_URL, style="Muted.TLabel", cursor="hand2")
        link.pack(anchor="w", pady=(12, 0))
        link.bind("<Button-1>", lambda _e: self.openWiki())

    def openWiki(self):
        try:
            webbrowser.open(self.WIKI_URL, new=2)
        except Exception:
            messagebox.showerror("Error", f"Could not open:\n{self.WIKI_URL}")

    def pickFolder(self):
        folder = filedialog.askdirectory()
        if folder:
            self.destinationEntry.delete(0, "end")
            self.destinationEntry.insert(0, folder)

    def startCase(self):
        case = self.caseEntry.get().strip()
        if not case:
            messagebox.showerror("Error", "Case Number is required.")
            return

        try:
            threads = int(self.threadPicker.get())
            threads = max(1, min(32, threads))
        except Exception:
            threads = 4

        urls = [u.strip() for u in self.urlText.get("1.0", "end").split("\n") if u.strip()]
        if not urls:
            messagebox.showerror("Error", "No URLs entered.")
            return

        destination_root = self.destinationEntry.get().strip()
        if not destination_root:
            messagebox.showerror("Error", "Destination folder is required.")
            return

        saveSetting({"case": case, "threads": threads, "destination": destination_root})

        base = os.path.join(destination_root, case)
        video_dir = os.path.join(base, "Videos")
        thumb_dir = os.path.join(base, "Thumbnails")

        os.makedirs(video_dir, exist_ok=True)
        os.makedirs(thumb_dir, exist_ok=True)

        log_file = os.path.join(base, f"{case}_report.html")

        ip1, ip2 = checkIPaddress()
        ip_status = "VERIFIED" if ip1 == ip2 and ip1 != "ERROR" else "MISMATCH"

        createHTMLlog(log_file, case, ip1, ip2, ip_status)

        self.total_items = len(urls)
        self.done_items = 0
        self.failed_items = 0
        self.updateCounts()
        self.globalProgress["value"] = 0
        self.statusBadge.config(text="RUNNING")

        for item in self.tree.get_children():
            self.tree.delete(item)
        self.futures = []

        self.executor = ThreadPoolExecutor(max_workers=threads)

        for url in urls:
            self.tree.insert("", "end", iid=url, values=("Queued", "0%"))
            future = self.executor.submit(processVideo, url, video_dir, thumb_dir, log_file, case)
            self.futures.append(future)

        def finalize():
            for _ in as_completed(self.futures):
                pass
            closeHTMLlog(log_file)
            UIQueue.put(("__SYSTEM__", "FINISHED", log_file))

        threading.Thread(target=finalize, daemon=True).start()

    def updateCounts(self):
        queued = max(0, self.total_items - (self.done_items + self.failed_items))
        self.countLabel.config(text=f"Queued: {queued}   Done: {self.done_items}   Failed: {self.failed_items}")

        if self.total_items > 0:
            pct = (self.done_items + self.failed_items) / self.total_items * 100.0
            self.globalProgress["value"] = pct

    def updatingUI(self):
        try:
            while True:
                data = UIQueue.get_nowait()
                url = data[0]

                if url == "__SYSTEM__" and data[1] == "FINISHED":
                    self.statusBadge.config(text="DONE")
                    self.updateCounts()
                    report_path = data[2]
                    messagebox.showinfo("Case Complete", f"Finished! Report saved:\n{report_path}")
                    continue

                event = data[1]
                if event == "PROGRESS":
                    pct = float(data[2])
                    self.tree.item(url, values=("DOWNLOADING", f"{pct:.1f}%"))
                elif event == "MERGING":
                    pct = float(data[2])
                    self.tree.item(url, values=("MERGING", f"{pct:.1f}%"))
                elif event == "DONE":
                    self.done_items += 1
                    sha = data[2]
                    self.tree.item(url, values=("VERIFIED", sha))
                    self.updateCounts()
                elif event == "FAILED":
                    self.failed_items += 1
                    err = data[2]
                    self.tree.item(url, values=("FAILED", err))
                    self.updateCounts()

        except queue.Empty:
            pass

        self.root.after(250, self.updatingUI)


if __name__ == "__main__":
    root = tk.Tk()
    app = App(root)
    root.mainloop()
