#!/usr/bin/env python3
"""
Kill Compilation Script with 1.25x Speed (BGM mixed after speedup)
-------------------------------------------------------------------
Workflow:
1. Detect 'ENEMY DOWNED' using EasyOCR.
2. Extract kill clips (lossless).
3. Merge clips.
4. Apply 1.25× speedup (video + game audio only).
5. Mix background music at normal pitch and save final 4K WebM.

Output: final_with_bgm.webm (4K VP9 + Opus)
"""

import os
import sys
import subprocess
import argparse
import shutil
import random
import glob
import gc
import time
import re

# OCR setup
try:
    import cv2
except Exception:
    print("[ERROR] Install OpenCV: python3 -m pip install opencv-python-headless")
    sys.exit(1)

try:
    import torch
    use_mps = torch.backends.mps.is_available()
except Exception:
    use_mps = False
import easyocr
reader = easyocr.Reader(['en'], gpu=use_mps)

# === CONFIG ===
KILL_KEYWORDS = ["ENEMY DOWNED"]
PRE_SEC = 5
POST_SEC = 5
OCR_INTERVAL = 1.0
OCR_RESIZE = 0.6


def get_video_duration(path):
    try:
        r = subprocess.run([
            'ffprobe', '-v', 'error', '-show_entries', 'format=duration',
            '-of', 'default=noprint_wrappers=1:nokey=1', path
        ], capture_output=True, text=True, check=True)
        return float(r.stdout.strip())
    except Exception:
        return None


def ocr_frame(region_bgr):
    if OCR_RESIZE != 1.0:
        region_bgr = cv2.resize(region_bgr, None, fx=OCR_RESIZE, fy=OCR_RESIZE)
    try:
        results = reader.readtext(region_bgr, detail=0)
        return " ".join(results).strip()
    except Exception:
        return ""


def find_and_extract(video_path, out_dir, pre=PRE_SEC, post=POST_SEC):
    os.makedirs(out_dir, exist_ok=True)
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        print(f"[ERROR] cannot open {video_path}")
        return []
    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
    duration = frame_count / fps if frame_count else get_video_duration(video_path) or 0
    print(f"[INFO] Scanning {video_path} (dur={duration:.1f}s, fps={fps:.1f})")

    ret, frame = cap.read()
    if not ret:
        cap.release()
        return []
    h, w = frame.shape[:2]
    x1, x2 = int(w * 0.70), w
    y1, y2 = 0, int(h * 0.30)

    found_times = []
    last_found = -1e9
    sec = 0.0
    while sec < duration:
        cap.set(cv2.CAP_PROP_POS_MSEC, sec * 1000)
        ret, frame = cap.read()
        if not ret:
            sec += OCR_INTERVAL
            continue
        region = frame[y1:y2, x1:x2]
        text = ocr_frame(region)
        if text:
            for kw in KILL_KEYWORDS:
                if kw.lower() in text.lower() and sec - last_found > (pre + post):
                    found_times.append(sec)
                    last_found = sec
                    print(f"[FOUND] '{kw}' at {sec:.2f}s")
        sec += OCR_INTERVAL

    cap.release()

    extracted = []
    for i, t in enumerate(found_times, start=1):
        start = max(0.0, t - pre)
        length = pre + post
        out_file = os.path.join(out_dir, f"downed_clip_{i:03d}.webm")
        cmd = [
            'ffmpeg', '-nostdin', '-y', '-i', video_path,
            '-ss', str(start), '-t', str(length),
            '-c', 'copy', out_file
        ]
        try:
            subprocess.run(cmd, check=True, capture_output=True)
            extracted.append(out_file)
        except subprocess.CalledProcessError:
            print(f"[WARN] Failed to extract clip {i}")
    return extracted


def merge_clips_together(clips, out_path):
    if not clips:
        print("[SKIP] no clips to merge")
        return False
    os.makedirs(os.path.dirname(out_path) or '.', exist_ok=True)
    list_file = os.path.join(os.path.dirname(out_path), 'concat_list.txt')
    with open(list_file, 'w') as f:
        for c in clips:
            f.write(f"file '{os.path.abspath(c)}'\n")
    cmd = ['ffmpeg', '-nostdin', '-y', '-f', 'concat', '-safe', '0',
           '-i', list_file, '-c', 'copy', out_path]
    try:
        subprocess.run(cmd, check=True)
        os.remove(list_file)
        print(f"[MERGED] → {out_path}")
        return True
    except subprocess.CalledProcessError:
        print("[WARN] concat-copy failed.")
        return False


def apply_speedup_webm(input_path, output_path):
    print(f"[STEP] Applying 1.25× speed (video + game audio only)...")
    duration = get_video_duration(input_path)
    cmd = [
        "ffmpeg", "-nostdin", "-y",
        "-i", input_path,
        "-filter_complex", "[0:v]setpts=PTS/1.25[v];[0:a]atempo=1.25[a]",
        "-map", "[v]", "-map", "[a]",
        "-c:v", "libvpx-vp9",
        "-crf", "20", "-b:v", "0",
        "-threads", "8",
        "-row-mt", "1",
        "-tile-columns", "2",
        "-tile-rows", "1",
        "-speed", "8",
        "-cpu-used", "8",
        "-quality", "good",
        "-auto-alt-ref", "1",
        "-c:a", "libopus",
        "-b:a", "192k",
        output_path
    ]

    process = subprocess.Popen(cmd, stderr=subprocess.PIPE, universal_newlines=True)
    pattern = re.compile(r'time=(\d+):(\d+):([\d.]+)')
    start_time = time.time()

    for line in process.stderr:
        match = pattern.search(line)
        if match:
            h, m, s = match.groups()
            seconds = int(h) * 3600 + int(m) * 60 + float(s)
            progress = min(seconds / duration, 1.0)
            elapsed = time.time() - start_time
            est_total = elapsed / progress if progress > 0 else 0
            eta = max(est_total - elapsed, 0)
            sys.stdout.write(
                f"\r[ENCODING] {progress*100:5.1f}%  |  "
                f"ETA: {eta/60:5.1f} min  |  Elapsed: {elapsed/60:5.1f} min"
            )
            sys.stdout.flush()

    process.wait()
    sys.stdout.write("\n[ENCODING COMPLETE] Speedup done → {}\n".format(output_path))
    sys.stdout.flush()


def add_background_music(input_video, output_video, music_dir="background_musics"):
    musics = glob.glob(os.path.join(music_dir, "*.mp3")) + glob.glob(os.path.join(music_dir, "*.wav"))
    if not musics:
        print(f"[WARN] No background music found in {music_dir}, copying original video")
        shutil.copy2(input_video, output_video)
        return
    bg_music = random.choice(musics)
    print(f"[INFO] Mixing background track (post-speedup): {os.path.basename(bg_music)}")

    cmd = [
        "ffmpeg", "-nostdin", "-y",
        "-stream_loop", "-1", "-i", bg_music,
        "-i", input_video,
        "-filter_complex",
        "[0:a]volume=0.5[a1];[1:a]volume=0.5[a2];"
        "[a1][a2]amix=inputs=2:normalize=0",
        "-c:v", "copy",
        "-c:a", "libopus",
        "-b:a", "192k",
        "-shortest",
        output_video
    ]
    subprocess.run(cmd, check=True)
    print(f"[FINAL MIX] BGM mixed → {output_video}")


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--input', '-i', required=True)
    p.add_argument('--outdir', '-o', default='output')
    args = p.parse_args()

    script_dir = os.path.abspath(os.path.dirname(__file__))
    input_path = os.path.join(script_dir, args.input)
    out_root = os.path.join(script_dir, args.outdir)
    os.makedirs(out_root, exist_ok=True)

    print(f"[STEP] Detecting kills in {args.input}")
    downed_dir = os.path.join(out_root, 'Downed_clips')
    merged_dir = os.path.join(out_root, 'Merged')
    os.makedirs(downed_dir, exist_ok=True)
    os.makedirs(merged_dir, exist_ok=True)

    clips = find_and_extract(input_path, downed_dir)
    if not clips:
        print("[INFO] No kills found.")
        return

    merged_out = os.path.join(merged_dir, 'compilation_raw.webm')
    if not merge_clips_together(clips, merged_out):
        print("[ERROR] Merging failed.")
        return

    # Step 1: Apply speedup first
    fast_out = os.path.join(out_root, 'compilation_fast.webm')
    apply_speedup_webm(merged_out, fast_out)

    # Step 2: Mix BGM at normal tempo
    final_out = os.path.join(out_root, 'final_with_bgm.webm')
    add_background_music(fast_out, final_out)

    print(f"\n✅ [DONE] Final 4K compilation ready: {final_out}")
    gc.collect()


if __name__ == '__main__':
    main()
