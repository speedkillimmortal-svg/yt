#!/usr/bin/env python3
"""
Kill Compilation Script with Background Music Mix
-------------------------------------------------
- Detects 'ENEMY DOWNED' moments using EasyOCR.
- Extracts clips around detections.
- Merges all kill clips together.
- Adds random looping background music mixed 50/50 with original game sound.
- Output: lossless WebM (VP9 + Opus).

Usage:
    python compile_kills.py --input input.webm --outdir output --format webm
"""

import os
import sys
import subprocess
import argparse
import shutil
import random
import glob
import gc

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


# ---------- Utility functions ----------
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


# ---------- Clip detection & extraction ----------
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


# ---------- Merge ----------
def probe_props(path):
    try:
        r = subprocess.run([
            'ffprobe', '-v', 'error', '-select_streams', 'v:0',
            '-show_entries', 'stream=codec_name,width,height,pix_fmt,r_frame_rate',
            '-of', 'json', path
        ], capture_output=True, text=True, check=True)
        import json
        info = json.loads(r.stdout)
        streams = info.get('streams') or []
        if not streams:
            return None
        s = streams[0]
        return {
            'codec_name': s.get('codec_name'),
            'width': int(s.get('width') or 0),
            'height': int(s.get('height') or 0),
            'pix_fmt': s.get('pix_fmt'),
            'r_frame_rate': s.get('r_frame_rate')
        }
    except Exception:
        return None


def clips_compatible(paths):
    base = None
    for p in paths:
        pr = probe_props(p)
        if not pr:
            return False
        if base is None:
            base = pr
            continue
        for k in ('codec_name', 'width', 'height', 'pix_fmt', 'r_frame_rate'):
            if str(base.get(k)) != str(pr.get(k)):
                return False
    return True


def merge_clips_together(clips, out_path):
    if not clips:
        print("[SKIP] no clips to merge")
        return False
    os.makedirs(os.path.dirname(out_path) or '.', exist_ok=True)

    if len(clips) == 1:
        shutil.copy2(clips[0], out_path)
        print(f"[COPIED] single clip → {out_path}")
        return True

    # concat-copy if compatible
    if clips_compatible(clips):
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
            print("[WARN] concat-copy failed, normalizing...")

    # normalize
    norms = []
    try:
        for c in clips:
            base = os.path.splitext(os.path.basename(c))[0]
            norm = os.path.join(os.path.dirname(out_path), base + '_norm.webm')
            cmd = ['ffmpeg', '-nostdin', '-y', '-i', c,
                   '-c:v', 'libvpx-vp9', '-lossless', '1', '-b:v', '0',
                   '-c:a', 'copy', norm]
            subprocess.run(cmd, check=True)
            norms.append(norm)
        list_file = os.path.join(os.path.dirname(out_path), 'concat_list.txt')
        with open(list_file, 'w') as f:
            for n in norms:
                f.write(f"file '{os.path.abspath(n)}'\n")
        cmd = ['ffmpeg', '-nostdin', '-y', '-f', 'concat', '-safe', '0',
               '-i', list_file, '-c', 'copy', out_path]
        subprocess.run(cmd, check=True)
        os.remove(list_file)
        print(f"[MERGED - normalized] {out_path}")
        return True
    finally:
        for n in norms:
            if os.path.exists(n):
                os.remove(n)


# ---------- Background music mixing ----------
def add_background_music(merged_out, final_out, music_dir="background_musics"):
    """Add random looping background music mixed 50/50 with game audio"""
    os.makedirs(music_dir, exist_ok=True)
    musics = glob.glob(os.path.join(music_dir, "*.mp3")) + glob.glob(os.path.join(music_dir, "*.wav"))
    if not musics:
        print(f"[WARN] No background music found in {music_dir}, copying original video")
        shutil.copy2(merged_out, final_out)
        return

    bg_music = random.choice(musics)
    print(f"[INFO] Using background track: {os.path.basename(bg_music)}")

    cmd = [
        "ffmpeg", "-nostdin", "-y",
        "-stream_loop", "-1", "-i", bg_music,
        "-i", merged_out,
        "-filter_complex",
        "[0:a]volume=0.5[a1];[1:a]volume=0.5[a2];"
        "[a1][a2]amix=inputs=2:normalize=0",
        "-c:v", "copy",
        "-c:a", "libopus",
        "-b:a", "192k",
        "-shortest",
        final_out
    ]
    subprocess.run(cmd, check=True)
    print(f"[MIXED] Added background music → {final_out}")


# ---------- Main ----------
def main():
    p = argparse.ArgumentParser()
    p.add_argument('--input', '-i', default='input.webm')
    p.add_argument('--outdir', '-o', default='output')
    p.add_argument('--format', choices=['mp4', 'webm'], default='webm')
    p.add_argument('--pre', type=float, default=PRE_SEC)
    p.add_argument('--post', type=float, default=POST_SEC)
    args = p.parse_args()

    script_dir = os.path.abspath(os.path.dirname(__file__))
    input_path = args.input if os.path.isabs(args.input) else os.path.join(script_dir, args.input)
    if not os.path.exists(input_path):
        print(f"[ERROR] Input not found: {input_path}")
        sys.exit(1)

    out_root = os.path.join(script_dir, args.outdir)
    downed_dir = os.path.join(out_root, 'Downed_clips')
    merged_dir = os.path.join(out_root, 'Merged')
    os.makedirs(downed_dir, exist_ok=True)
    os.makedirs(merged_dir, exist_ok=True)

    clips = find_and_extract(input_path, downed_dir, pre=args.pre, post=args.post)
    if not clips:
        print("[INFO] No kills found.")
        return

    merged_out = os.path.join(merged_dir, 'compilation_temp.webm')
    ok = merge_clips_together(clips, merged_out)
    if not ok:
        print("[ERROR] Merging failed")
        return

    final_out = os.path.join(out_root, f"compilation.{args.format}")
    add_background_music(merged_out, final_out)

    print("\n[DONE] Final compilation saved to:", final_out)
    gc.collect()


if __name__ == '__main__':
    main()
