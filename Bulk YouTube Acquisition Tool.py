# Bulk YouTube Acquisition Tool
# Developer: Joshua Brooks
# Version: 1.2.1
# Last update: 2/13/2026

import os
import hashlib
import datetime
import threading
import queue
import json
import shutil
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
import tkinter as tk
from tkinter import ttk, messagebox, filedialog
from yt_dlp import YoutubeDL

settingFile = "settings.json"
ui_queue = queue.Queue()
logLock = threading.Lock()

def load_settings():
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

def downloadThumbnail(thumbnail_url, save_path):
    try:
        with urllib.request.urlopen(thumbnail_url, timeout=15) as response:
            data = response.read()
            with open(save_path, "wb") as f:
                f.write(data)
        return True
    except:
        return False

def checkIPaddress():
    sources = [
        "https://api.ipify.org",
        "https://checkip.amazonaws.com"
    ]
    ips = []
    for url in sources:
        try:
            with urllib.request.urlopen(url, timeout=5) as r:
                ips.append(r.read().decode().strip())
        except:
            ips.append("ERROR")
    return ips

def createHTMLlog(log_path, case, ip1, ip2, ip_status): #HTML Report
    with open(log_path, "w", encoding="utf-8") as log:
        log.write(f"""<!DOCTYPE html>
<html>
<head>
<meta charset="UTF-8">
<title>Case Report - {case}</title>
<style>
body {{ font-family: Arial; background:#f4f4f4; padding:20px; }}
h1 {{ color:#333; }}
table {{ width:100%; border-collapse:collapse; background:white; }}
th, td {{ border:1px solid #ccc; padding:8px; text-align:left; }}
th {{ background:#222; color:white; }}
.verified {{ color:green; font-weight:bold; }}
.failed {{ color:red; font-weight:bold; }}
.hash {{ font-family:monospace; font-size:12px; }}
.meta {{ margin-bottom:20px; padding:10px; background:white; border:1px solid #ccc; }}
</style>
</head>
<body>
<h1>Bulk YouTube Acquisition Report</h1>

<div class="meta">
<strong>Case:</strong> {case}<br>
<strong>Start UTC:</strong> {datetime.datetime.utcnow().isoformat()}<br>
<strong>Public IP 1 by https://api.ipify.org:</strong> {ip1}<br>
<strong>Public IP 2 by https://checkip.amazonaws.com:</strong> {ip2}<br>
<strong>IP Verification:</strong> {ip_status}
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
""")

def closeHTMLlog(log_path):
    with open(log_path, "a", encoding="utf-8") as log:
        log.write(f"""
</table>
<br><br>
<strong>End UTC:</strong> {datetime.datetime.utcnow().isoformat()}
</body>
</html>
""")

def processVideo(url, videoDir, thumbDir, logFile, case):

    def hook(d):
        if d["status"] == "downloading":
            percent = d.get("_percent_str", "0%").replace("%", "").strip()
            try:
                percent = float(percent)
            except:
                percent = 0
            ui_queue.put((url, "PROGRESS", percent))
    try:
        ydl_opts = {
            "outtmpl": os.path.join(videoDir, f"{case}_%(title)s.%(ext)s"),
            "progress_hooks": [hook],
            "quiet": True,
            "no_warnings": True,
        }
        with YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            temp_path = ydl.prepare_filename(info)

        videoTitle = info.get("title", "UNKNOWN_TITLE")
        videoID = info.get("id", "unknownid")
        thumbnailURL = info.get("thumbnail")

        # Thumbnail
        thumbFilename = f"{videoID}_thumbnail.jpg"
        thumbPath = os.path.join(thumbDir, thumbFilename)

        thumbnailHash = "N/A"
        if thumbnailURL:
            if downloadThumbnail(thumbnailURL, thumbPath):
                thumbnailHash = sha256Hash(thumbPath)

        # Video Hash Verification
        hash1 = sha256Hash(temp_path)
        finalPath = os.path.join(videoDir, os.path.basename(temp_path))
        shutil.move(temp_path, finalPath)
        hash2 = sha256Hash(finalPath)

        status = "VERIFIED" if hash1 == hash2 else "HASH_MISMATCH"
        css_class = "verified" if status == "VERIFIED" else "failed"

        with logLock:
            with open(logFile, "a", encoding="utf-8") as log:
                log.write(f"""
<tr>
<td>{datetime.datetime.utcnow().isoformat()}</td>
<td><img src="Thumbnails/{thumbFilename}" width="160"></td>
<td>{videoTitle}</td>
<td><a href="{url}" target="_blank">{url}</a></td>
<td class="{css_class}">{status}</td>
<td class="hash">{hash2}</td>
<td class="hash">{thumbnailHash}</td>
</tr>
""")

        ui_queue.put((url, "DONE", hash2))

    except Exception as e:
        with logLock:
            with open(logFile, "a", encoding="utf-8") as log:
                log.write(f"""
<tr>
<td>{datetime.datetime.utcnow().isoformat()}</td>
<td>N/A</td>
<td>UNKNOWN_TITLE</td>
<td>{url}</td>
<td class="failed">FAILED</td>
<td>{str(e)}</td>
<td>N/A</td>
</tr>
""")
        ui_queue.put((url, "FAILED", str(e)))



class App: #GUI

    def __init__(self, root):
        self.root = root
        self.root.title("Forensic YouTube Acquisition Suite")
        self.root.geometry("1000x650")

        self.settings = load_settings()
        self.executor = None
        self.futures = []

        self.buildUI()
        self.updatingUI()

    def buildUI(self):

        ttk.Label(self.root, text="Case Number:").pack()
        self.caseEntry = ttk.Entry(self.root)
        self.caseEntry.insert(0, self.settings.get("case", "CASE001"))
        self.caseEntry.pack(fill="x", padx=10)

        ttk.Label(self.root, text="Threads (1-32):").pack()
        self.threadPicker = tk.Spinbox(self.root, from_=1, to=32)
        self.threadPicker.pack()
        self.threadPicker.delete(0, "end")
        self.threadPicker.insert(0, self.settings.get("threads", 4))

        ttk.Label(self.root, text="Case Destination Folder:").pack()
        folderFrame = ttk.Frame(self.root)
        folderFrame.pack(fill="x", padx=10)

        self.destinationEntry = ttk.Entry(folderFrame)
        self.destinationEntry.pack(side="left", fill="x", expand=True)
        self.destinationEntry.insert(0, self.settings.get("destination", os.getcwd()))

        ttk.Button(folderFrame, text="Browse", command=self.pickFolder).pack(side="right")

        ttk.Label(self.root, text="URLs (video / playlist / channel):").pack()
        self.urlText = tk.Text(self.root, height=6)
        self.urlText.pack(fill="x", padx=10)

        ttk.Button(self.root, text="Start Case Acquisition", command=self.startCase).pack(pady=10)

        self.tree = ttk.Treeview(self.root, columns=("Status", "Info"), show="headings")
        self.tree.heading("Status", text="Status")
        self.tree.heading("Info", text="Progress / Hash")
        self.tree.pack(fill="both", expand=True, padx=10, pady=10)

    def pickFolder(self):
        folder = filedialog.askdirectory()
        if folder:
            self.destinationEntry.delete(0, "end")
            self.destinationEntry.insert(0, folder)

    def startCase(self):

        case = self.caseEntry.get().strip()
        threads = int(self.threadPicker.get())
        urls = [u.strip() for u in self.urlText.get("1.0", "end").split("\n") if u.strip()]

        if not urls:
            messagebox.showerror("Error", "No URLs entered.")
            return

        destination_root = self.destinationEntry.get().strip()

        saveSetting({
            "case": case,
            "threads": threads,
            "destination": destination_root
        })

        base = os.path.join(destination_root, case)
        video_dir = os.path.join(base, "Videos")
        thumb_dir = os.path.join(base, "Thumbnails")

        os.makedirs(video_dir, exist_ok=True)
        os.makedirs(thumb_dir, exist_ok=True)

        log_file = os.path.join(base, f"{case}_report.html")

        ip1, ip2 = checkIPaddress()
        ip_status = "VERIFIED" if ip1 == ip2 and ip1 != "ERROR" else "MISMATCH"

        createHTMLlog(log_file, case, ip1, ip2, ip_status)

        self.executor = ThreadPoolExecutor(max_workers=threads)

        for url in urls:
            self.tree.insert("", "end", iid=url, values=("Queued", "0%"))
            future = self.executor.submit(processVideo, url, video_dir, thumb_dir, log_file, case)
            self.futures.append(future)

        def finalize():
            for _ in as_completed(self.futures):
                pass
            closeHTMLlog(log_file)

        threading.Thread(target=finalize, daemon=True).start()

    def updatingUI(self):
        try:
            while True:
                data = ui_queue.get_nowait()
                url = data[0]
                if data[1] == "PROGRESS":
                    self.tree.item(url, values=("DOWNLOADING", f"{data[2]}%"))
                elif data[1] == "DONE":
                    self.tree.item(url, values=("VERIFIED", data[2]))
                elif data[1] == "FAILED":
                    self.tree.item(url, values=("FAILED", data[2]))
        except queue.Empty:
            pass

        self.root.after(300, self.updatingUI)

if __name__ == "__main__":
    root = tk.Tk()
    app = App(root)
    root.mainloop()
