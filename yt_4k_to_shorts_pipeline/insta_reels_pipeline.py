#!/usr/bin/env python3
"""
🎥 Instagram Reels Pipeline (4K → 1080x1920)
- Extracts “ENEMY DOWNED” kills
- Merges clips globally
- Converts to vertical .mp4 (H.264 hardware-accelerated)
- Cleans temporary folders
"""

import os, sys, gc, cv2, ffmpeg, shutil, random, subprocess
from concurrent.futures import ThreadPoolExecutor

KILL_KEYWORDS = ["ENEMY DOWNED"]
PRE_SEC, POST_SEC = 5, 5
OCR_INTERVAL = 1.0
OCR_RESIZE = 0.6
MAX_THREADS = 2
COOLDOWN_SEC = PRE_SEC + POST_SEC
TARGET_W, TARGET_H = 1080, 1920

# === OCR ===
use_mps = False
try:
    import torch
    use_mps = torch.backends.mps.is_available()
except Exception:
    torch = None
import easyocr
reader = easyocr.Reader(['en'], gpu=use_mps)
print(f"[INFO] EasyOCR ready (MPS GPU: {use_mps})")

# === Helpers ===
def ocr_frame(region):
    if OCR_RESIZE != 1.0:
        region = cv2.resize(region, None, fx=OCR_RESIZE, fy=OCR_RESIZE)
    return " ".join(reader.readtext(region, detail=0)).strip()

def get_duration(path):
    try:
        out = subprocess.run([
            "ffprobe", "-v", "error", "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1", path
        ], capture_output=True, text=True, check=True)
        return float(out.stdout.strip())
    except Exception:
        return 0

def split_video(input_path, part_len=360, out_dir="parts"):
    os.makedirs(out_dir, exist_ok=True)
    dur = get_duration(input_path)
    n = int(dur // part_len) + (1 if dur % part_len > 0 else 0)
    files = []
    for i in range(n):
        start = i * part_len
        end = min(part_len, dur - start)
        out_path = os.path.join(out_dir, f"part{i+1}.webm")
        subprocess.run([
            "ffmpeg", "-nostdin", "-loglevel", "error", "-y",
            "-i", input_path, "-ss", str(start), "-t", str(end),
            "-c", "copy", out_path
        ])
        files.append(out_path)
    return files

def find_and_extract(video_path, out_dir):
    os.makedirs(out_dir, exist_ok=True)
    cap = cv2.VideoCapture(video_path)
    fps = cap.get(cv2.CAP_PROP_FPS) or 30
    dur = (cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0) / fps
    print(f"[SCAN] {video_path}: {dur:.1f}s")

    ret, frame = cap.read()
    if not ret:
        return []
    h, w = frame.shape[:2]
    roi = (int(w * 0.7), 0, w, int(h * 0.25))
    found, last = [], -1e9
    sec = 0
    while sec < dur:
        cap.set(cv2.CAP_PROP_POS_MSEC, sec * 1000)
        ret, frame = cap.read()
        if not ret:
            sec += OCR_INTERVAL
            continue
        text = ocr_frame(frame[0:int(h*0.25), int(w*0.7):w])
        if any(kw.lower() in text.lower() for kw in KILL_KEYWORDS) and sec - last > COOLDOWN_SEC:
            found.append(sec)
            last = sec
            print(f"[FOUND] at {sec:.1f}s")
        sec += OCR_INTERVAL
    cap.release()

    clips = []
    for i, t in enumerate(found, 1):
        start = max(0, t - PRE_SEC)
        out = os.path.join(out_dir, f"clip_{i}.webm")
        (
            ffmpeg
            .input(video_path, ss=start, t=PRE_SEC + POST_SEC)
            .output(out, c="copy", loglevel="error")
            .run(overwrite_output=True)
        )
        clips.append(out)
    return clips

def merge_clips(clips, out_dir):
    os.makedirs(out_dir, exist_ok=True)
    merged = []
    for i in range(0, len(clips), 3):
        grp = clips[i:i+3]
        if not grp: continue
        out_file = os.path.join(out_dir, f"merged_{i//3+1}.webm")
        with open("merge_list.txt", "w") as f:
            for c in grp:
                f.write(f"file '{os.path.abspath(c)}'\n")
        subprocess.run(["ffmpeg", "-f", "concat", "-safe", "0", "-i", "merge_list.txt", "-c", "copy", "-y", out_file])
        merged.append(out_file)
    os.remove("merge_list.txt")
    return merged

def convert_to_reel(input_path, output_path, script_dir):
    logo = os.path.join(script_dir, "channel_logo.jpg")
    icon = os.path.join(script_dir, "generic_icon.png")
    bgm_dir = os.path.join(script_dir, "background_musics")

    music_files = [os.path.join(bgm_dir, f) for f in os.listdir(bgm_dir) if f.endswith((".mp3", ".wav"))] if os.path.exists(bgm_dir) else []
    music = random.choice(music_files) if music_files else None

    filters = "crop=in_h*9/16:in_h:(in_w-out_w)/2:0,scale=1080:1920"

    cmd = [
        "ffmpeg", "-i", input_path,
    ]
    if music:
        cmd += ["-i", music, "-shortest", "-filter_complex", filters]
    else:
        cmd += ["-vf", filters]
    cmd += [
        "-c:v", "h264_videotoolbox", "-b:v", "6M", "-maxrate", "8M", "-bufsize", "12M",
        "-c:a", "aac", "-b:a", "128k", "-movflags", "+faststart", "-y", output_path
    ]
    subprocess.run(cmd, check=True)
    print(f"[REEL DONE] {output_path}")

def main():
    script = os.path.dirname(os.path.abspath(__file__))
    vid = os.path.join(script, "input.webm")
    if not os.path.exists(vid):
        print("[ERROR] input.webm missing!")
        sys.exit(1)

    parts = split_video(vid)
    clips = []
    for p in parts:
        clips += find_and_extract(p, os.path.join(script, "Downed", os.path.splitext(os.path.basename(p))[0]))
        os.remove(p)

    merged = merge_clips(clips, os.path.join(script, "Merged"))
    out_dir = os.path.join(script, "insta_reels")
    os.makedirs(out_dir, exist_ok=True)

    for f in merged:
        base = os.path.splitext(os.path.basename(f))[0]
        out = os.path.join(out_dir, f"{base}_reel.mp4")
        convert_to_reel(f, out, script)

    shutil.rmtree(os.path.join(script, "Downed"), ignore_errors=True)
    shutil.rmtree(os.path.join(script, "Merged"), ignore_errors=True)
    gc.collect()
    print(f"\n✅ All Insta Reels ready in: {out_dir}")

if __name__ == "__main__":
    main()
