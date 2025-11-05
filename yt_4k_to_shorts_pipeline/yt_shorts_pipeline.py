#!/usr/bin/env python3
"""
⚡ Optimized YouTube Shorts Creator (Mac Ready)
- Extracts "ENEMY DOWNED" clips from input.webm
- Merges all found clips
- Converts them into vertical 1080x1920 MP4 (YouTube Shorts ready)
- Adds logo + icon overlay
- Uses hardware encoding for speed
"""

import os
import sys
import gc
import shutil
import cv2
import ffmpeg
import subprocess
import random
from concurrent.futures import ThreadPoolExecutor

# === CONFIGURATION ===
KILL_KEYWORDS = ["ENEMY DOWNED"]
PRE_SEC = 5
POST_SEC = 5
OCR_INTERVAL = 1.0
OCR_RESIZE = 0.6
MAX_THREADS = 2
COOLDOWN_SEC = PRE_SEC + POST_SEC
TARGET_WIDTH = 1080
TARGET_HEIGHT = 1920

use_mps = False
try:
    import torch
    use_mps = torch.backends.mps.is_available()
except Exception:
    torch = None

import easyocr
reader = easyocr.Reader(['en'], gpu=use_mps)
print(f"[INFO] EasyOCR initialized (MPS GPU: {use_mps})")

# === Helper Functions ===
def ocr_frame(region_bgr):
    if OCR_RESIZE != 1.0:
        region_bgr = cv2.resize(region_bgr, None, fx=OCR_RESIZE, fy=OCR_RESIZE)
    results = reader.readtext(region_bgr, detail=0)
    return " ".join(results).strip()

def get_video_duration(input_path):
    result = subprocess.run([
        "ffprobe", "-v", "error", "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1", input_path
    ], capture_output=True, text=True)
    return float(result.stdout.strip())

def find_and_extract(video_path, output_dir):
    os.makedirs(output_dir, exist_ok=True)
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        print(f"[ERROR] Cannot open {video_path}")
        return []
    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    duration = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) / fps)
    print(f"[INFO] FPS={fps:.1f}, Duration={duration}s")

    ret, frame = cap.read()
    if not ret:
        return []
    h, w = frame.shape[:2]
    region = (int(w*0.7), 0, w, int(h*0.25))  # top-right
    found_times, last_found = [], -1e9
    sec = 0.0
    executor = ThreadPoolExecutor(max_workers=MAX_THREADS)

    while sec < duration:
        cap.set(cv2.CAP_PROP_POS_MSEC, sec * 1000)
        ret, frame = cap.read()
        if not ret:
            sec += OCR_INTERVAL
            continue
        rx1, ry1, rx2, ry2 = region
        text = executor.submit(ocr_frame, frame[ry1:ry2, rx1:rx2]).result()
        if any(kw.lower() in text.lower() for kw in KILL_KEYWORDS):
            if sec - last_found > COOLDOWN_SEC:
                found_times.append(sec)
                last_found = sec
                print(f"[FOUND] at {sec:.2f}s")
        sec += OCR_INTERVAL

    cap.release()
    executor.shutdown(wait=True)

    clips = []
    for i, t in enumerate(found_times):
        start = max(0, t - PRE_SEC)
        out = os.path.join(output_dir, f"downed_{i+1}.mp4")
        cmd = [
            "ffmpeg", "-nostdin", "-loglevel", "error", "-y",
            "-ss", str(start), "-t", str(PRE_SEC + POST_SEC),
            "-i", video_path, "-c", "copy", out
        ]
        subprocess.run(cmd)
        clips.append(out)
    return clips

def merge_clips(clip_list, output_path):
    if not clip_list:
        return
    list_file = "merge.txt"
    with open(list_file, "w") as f:
        for c in clip_list:
            f.write(f"file '{os.path.abspath(c)}'\n")
    subprocess.run(["ffmpeg", "-f", "concat", "-safe", "0", "-i", list_file,
                    "-c", "copy", "-y", output_path])
    os.remove(list_file)
    print(f"[MERGED] -> {output_path}")

def convert_to_vertical(input_path, output_path, script_dir):
    logo_path = os.path.join(script_dir, "channel_logo.jpg")
    icon_path = os.path.join(script_dir, "generic_icon.png")

    filters = [
        "scale=-1:1920",  # resize to height 1920
        "crop=1080:1920",  # center crop
    ]

    overlay_filters = []
    if os.path.exists(icon_path):
        overlay_filters.append(f"overlay=0:H-h")  # bottom-left
    if os.path.exists(logo_path):
        overlay_filters.append(f"overlay=W-w-20:H-h-20")  # bottom-right

    vf = ",".join(filters + overlay_filters)

    subprocess.run([
        "ffmpeg", "-nostdin", "-loglevel", "error", "-y",
        "-i", input_path,
        "-vf", vf,
        "-c:v", "h264_videotoolbox",
        "-b:v", "10M", "-maxrate", "12M", "-bufsize", "16M",
        "-c:a", "aac", "-b:a", "192k",
        "-movflags", "+faststart",
        output_path
    ])
    print(f"[DONE] {output_path}")

def main():
    script_dir = os.path.dirname(os.path.abspath(__file__))
    video_path = os.path.join(script_dir, "input.webm")
    if not os.path.exists(video_path):
        print("[ERROR] input.webm missing")
        sys.exit(1)

    extracted = find_and_extract(video_path, os.path.join(script_dir, "Downed_clips"))
    if not extracted:
        print("[INFO] No kills found.")
        return

    merged_path = os.path.join(script_dir, "merged_all.mp4")
    merge_clips(extracted, merged_path)

    shorts_dir = os.path.join(script_dir, "youtube_shorts")
    os.makedirs(shorts_dir, exist_ok=True)
    out_path = os.path.join(shorts_dir, "final_vertical_short.mp4")
    convert_to_vertical(merged_path, out_path, script_dir)

    shutil.rmtree(os.path.join(script_dir, "Downed_clips"), ignore_errors=True)
    os.remove(merged_path)
    gc.collect()

    print("\n✅ [ALL DONE] YouTube Shorts ready at:")
    print(out_path)

if __name__ == "__main__":
    main()
