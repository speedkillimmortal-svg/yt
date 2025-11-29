#!/usr/bin/env python3
"""
FAST Kill Compilation Script (4K WebM VP9, 1.25x, BGM 50/50)
-------------------------------------------------------------------
Workflow:
1. Split input video into ~6-minute parts (fast, no re-encode)
2. Detect 'ENEMY DOWNED' in each part using EasyOCR (PARALLELIZED)
3. Extract kill clips (lossless copy, original resolution)
4. Merge all clips into one WebM
5. Apply 1.25× speed + Mix BGM in ONE PASS (OPTIMIZED - 50% faster encoding!)
   - VP9 encoding for optimal YouTube 4K quality
   - 50% game audio / 50% background music

Output:  output/final_with_bgm.webm   (4K VP9 + Opus, YouTube-optimized)
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
import concurrent.futures
import multiprocessing

# --- OCR / OpenCV setup ---
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

# Global reader variable (initialized lazily in workers)
reader = None

def init_reader():
    global reader
    if reader is None:
        print(f"[INFO] Initializing EasyOCR (MPS: {use_mps}) in process {os.getpid()}...")
        reader = easyocr.Reader(['en'], gpu=use_mps)

# === CONFIG ===
KILL_KEYWORDS = ["ENEMY DOWNED"]
PRE_SEC = 5
POST_SEC = 5
OCR_INTERVAL = 1.0
OCR_RESIZE = 0.6
PART_SECONDS = 360   # 6 minutes
COOLDOWN = PRE_SEC + POST_SEC  # cooldown between detections


def get_video_duration(path):
    try:
        r = subprocess.run(
            ['ffprobe', '-v', 'error', '-show_entries', 'format=duration',
             '-of', 'default=nokey=1:noprint_wrappers=1', path],
            capture_output=True, text=True, check=True
        )
        return float(r.stdout.strip())
    except Exception:
        return 0.0


# -------------------------------------------------------
# 1) SPLIT INPUT INTO ~6-MINUTE PARTS (NO RE-ENCODING)
# -------------------------------------------------------
def split_video(input_path, part_secs=PART_SECONDS):
    duration = get_video_duration(input_path)
    if duration <= 0:
        print("[ERROR] Could not read duration from input.")
        sys.exit(1)

    parts = []
    index = 0
    start = 0.0

    print(f"[SPLIT] Total duration: {duration:.1f}s, part size: {part_secs}s")

    while start < duration:
        index += 1
        out_file = f"part_{index}.webm"
        length = min(part_secs, duration - start)

        cmd = [
            "ffmpeg", "-nostdin", "-loglevel", "error", "-y",
            "-ss", f"{start:.3f}",
            "-t", f"{length:.3f}",
            "-i", input_path,
            "-c", "copy",
            out_file
        ]
        subprocess.run(cmd, check=True)
        parts.append(out_file)

        print(f"[SPLIT] Created {out_file} (start={start:.1f}s, len={length:.1f}s)")
        start += part_secs

    return parts


# -------------------------------------------------------
# 2) OCR KILL DETECTION FOR ONE PART
# -------------------------------------------------------
def ocr_frame(region_bgr):
    global reader
    if reader is None:
        init_reader()
        
    if OCR_RESIZE != 1.0:
        region_bgr = cv2.resize(region_bgr, None, fx=OCR_RESIZE, fy=OCR_RESIZE)
    try:
        text_list = reader.readtext(region_bgr, detail=0)
        return " ".join(text_list).strip()
    except Exception:
        return ""


def find_and_extract(video_path, out_dir):
    # Ensure reader is initialized in this process
    init_reader()
    
    os.makedirs(out_dir, exist_ok=True)

    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        print(f"[ERROR] Cannot open {video_path}")
        return []

    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    frame_count = cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0
    duration = frame_count / fps if fps > 0 else 0.0

    print(f"[OCR] {video_path} | dur={duration:.1f}s, fps={fps:.1f} (PID: {os.getpid()})")

    ret, frame = cap.read()
    if not ret:
        cap.release()
        return []

    h, w = frame.shape[:2]

    # Your original ROI: top-right HUD
    x1, x2 = int(w * 0.70), w
    y1, y2 = 0, int(h * 0.30)

    found_times = []
    last_time = -9999.0
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
            low = text.lower()
            if any(kw.lower() in low for kw in KILL_KEYWORDS):
                if sec - last_time > COOLDOWN:
                    print(f"[FOUND] Kill in {os.path.basename(video_path)} at {sec:.2f}s")
                    found_times.append(sec)
                    last_time = sec

        sec += OCR_INTERVAL

    cap.release()

    # --- Extract kill clips (lossless copy, same resolution) ---
    extracted = []
    for i, t in enumerate(found_times, 1):
        start = max(0.0, t - PRE_SEC)
        length = PRE_SEC + POST_SEC
        out = os.path.join(out_dir, f"{os.path.basename(video_path)}_clip{i:03d}.webm")

        cmd = [
            "ffmpeg", "-nostdin", "-loglevel", "error", "-y",
            "-ss", f"{start:.3f}",
            "-t", f"{length:.3f}",
            "-i", video_path,
            "-c", "copy",
            out
        ]
        subprocess.run(cmd, check=True)
        extracted.append(out)
        print(f"[CLIP] {out}  ({start:.2f}s → {start+length:.2f}s)")

    return extracted


# Wrapper for process pool
def process_part(args):
    p, outdir = args
    clips_dir = os.path.join(outdir, f"clips_{os.path.splitext(os.path.basename(p))[0]}")
    return find_and_extract(p, clips_dir)


# -------------------------------------------------------
# 3) MERGE ALL KILL CLIPS (RE-ENCODE TO FIX SYNC)
# -------------------------------------------------------
def merge_clips(clips, output):
    """
    Merge clips with re-encoding to ensure perfect sync.
    Using CFR (constant frame rate) to eliminate timestamp discontinuities
    that cause audio-video drift in concatenated clips.
    """
    if not clips:
        return False

    list_file = "merge_list.txt"
    with open(list_file, "w") as f:
        for c in clips:
            f.write(f"file '{os.path.abspath(c)}'\n")

    print("[MERGE] Re-encoding clips to ensure perfect A/V sync...")
    
    # Re-encode with CFR (Constant Frame Rate) to fix sync issues
    # This eliminates timestamp discontinuities from concatenated clips
    cmd = [
        "ffmpeg", "-nostdin", "-loglevel", "error", "-y",
        "-f", "concat", "-safe", "0",
        "-i", list_file,
        # Force constant frame rate and proper sync
        "-vsync", "cfr",              # Constant frame rate (critical for sync)
        "-r", "60",                   # Force 60 fps (adjust if your game uses different fps)
        "-async", "1",                # Audio sync method (resample to match video)
        # Use high-quality VP9 settings for intermediate file
        "-c:v", "libvpx-vp9",
        "-crf", "15",                 # Near-lossless for intermediate
        "-b:v", "0",                  # Let CRF control bitrate
        "-cpu-used", "2",             # Better quality (slower than 4)
        "-row-mt", "1",
        "-c:a", "libopus",
        "-b:a", "320k",               # Max audio quality
        output
    ]
    subprocess.run(cmd, check=True)
    os.remove(list_file)
    print(f"[MERGED] → {output}")
    return True


# -------------------------------------------------------
# 4) APPLY 1.25x SPEED + MIX BGM (COMBINED, SINGLE PASS)
# -------------------------------------------------------
def apply_speed_and_bgm(input_path, output_path, music_dir="background_musics"):
    """
    OPTIMIZED: Combines 1.25x speed-up and BGM mixing in ONE re-encode pass.
    This saves ~50% encoding time compared to doing them separately.
    Uses VP9/WebM for optimal YouTube 4K quality.
    """
    duration = get_video_duration(input_path)
    if duration <= 0:
        print("[ERROR] Cannot read duration for speed-up.")
        return

    # Check for background music
    musics = glob.glob(os.path.join(music_dir, "*.mp3")) + \
             glob.glob(os.path.join(music_dir, "*.wav"))

    if not musics:
        print(f"[WARN] No background music in {music_dir}, applying 1.25x speed only.")
        # No BGM: just speed up
        print("[STEP] Applying 1.25× speed + Sharpening (VP9/WebM for YouTube 4K)...")
        
        cmd = [
            "ffmpeg", "-nostdin", "-y",
            "-i", input_path,
            "-filter_complex", 
            "[0:v]setpts=PTS/1.25,unsharp=luma_msize_x=5:luma_msize_y=5:luma_amount=1.0:chroma_msize_x=5:chroma_msize_y=5:chroma_amount=0.0[v];[0:a]atempo=1.25[a]",
            "-map", "[v]", "-map", "[a]",
            # Sync safeguards
            "-vsync", "cfr",              # Force constant frame rate
            "-max_muxing_queue_size", "9999",  # Prevent buffer issues
            # Video encoding (MAX QUALITY)
            "-c:v", "libvpx-vp9",         # VP9 for YouTube 4K
            "-b:v", "0",                  # Constrained Quality mode
            "-crf", "18",                 # Near-lossless for VP9 4K
            "-cpu-used", "1",             # High quality (slower)
            "-row-mt", "1",               # Enable row-based multithreading
            # Audio encoding
            "-c:a", "libopus",            # Opus audio (best for WebM)
            "-b:a", "320k",               # Max quality audio
            output_path
        ]
    else:
        # With BGM: speed up + mix in one pass
        track = random.choice(musics)
        print(f"[OPTIMIZED] Applying 1.25× speed + Sharpening + mixing BGM (VP9/WebM for YouTube 4K)...")
        print(f"[BGM] Using: {os.path.basename(track)} (70% game / 30% BGM)")
        
        cmd = [
            "ffmpeg", "-nostdin", "-y",
            "-stream_loop", "-1", "-i", track,    # Input 0: BGM (looped)
            "-i", input_path,                      # Input 1: Raw compilation
            "-filter_complex",
            # Speed up video and audio from input 1 + Sharpen Video
            "[1:v]setpts=PTS/1.25,unsharp=luma_msize_x=5:luma_msize_y=5:luma_amount=1.0:chroma_msize_x=5:chroma_msize_y=5:chroma_amount=0.0[v];"
            "[1:a]atempo=1.25[game_fast];"
            # Mix BGM (input 0) with sped-up game audio at 70/30
            "[0:a]volume=0.3[bgm];"
            "[game_fast]volume=0.7[game];"
            "[bgm][game]amix=inputs=2:duration=shortest:normalize=0[a]",
            "-map", "[v]", "-map", "[a]",
            # Sync safeguards
            "-vsync", "cfr",              # Force constant frame rate
            "-max_muxing_queue_size", "9999",  # Prevent buffer issues
            # Video encoding (MAX QUALITY)
            "-c:v", "libvpx-vp9",         # VP9 for YouTube 4K
            "-b:v", "0",                  # Constrained Quality mode
            "-crf", "18",                 # Near-lossless for VP9 4K
            "-cpu-used", "1",             # High quality (slower)
            "-row-mt", "1",               # Enable row-based multithreading
            # Audio encoding
            "-c:a", "libopus",            # Opus audio (best for WebM)
            "-b:a", "320k",               # Max quality audio
            "-shortest",                  # Stop when shortest input ends
            output_path
        ]

    # Progress tracking
    process = subprocess.Popen(cmd, stderr=subprocess.PIPE, universal_newlines=True)
    time_pattern = re.compile(r'time=(\d+):(\d+):([\d.]+)')
    start_time = time.time()

    for line in process.stderr:
        m = time_pattern.search(line)
        if not m:
            continue
        h, m_min, s = m.groups()
        seconds = int(h) * 3600 + int(m_min) * 60 + float(s)
        # The new duration will be duration / 1.25
        target_duration = duration / 1.25
        progress = min(seconds / target_duration, 1.0)
        elapsed = time.time() - start_time
        est_total = elapsed / progress if progress > 0 else 0
        eta = max(est_total - elapsed, 0)

        bar_len = 30
        filled = int(bar_len * progress)
        bar = "#" * filled + "-" * (bar_len - filled)

        sys.stdout.write(
            f"\r[ENCODING] |{bar}| {progress*100:5.1f}%  "
            f"ETA: {eta/60:5.1f}m  Elapsed: {elapsed/60:5.1f}m"
        )
        sys.stdout.flush()

    process.wait()
    sys.stdout.write("\n[ENCODING COMPLETE] → {}\n".format(output_path))
    sys.stdout.flush()

    if process.returncode != 0:
        raise RuntimeError("[ERROR] Encoding failed.")


# -------------------------------------------------------
# MAIN PIPELINE
# -------------------------------------------------------
def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("-i", "--input", required=True, help="Input 4K WebM (game recording)")
    parser.add_argument("-o", "--outdir", default="output", help="Output folder")
    args = parser.parse_args()

    input_path = os.path.abspath(args.input)
    outdir = os.path.abspath(args.outdir)
    os.makedirs(outdir, exist_ok=True)

    # 1) Split into ~6-minute parts
    print("\n=== SPLITTING INPUT ===")
    parts = split_video(input_path)

    # 2) Process each part: find kills + extract clips (PARALLEL)
    print(f"\n=== PROCESSING {len(parts)} PARTS (PARALLEL) ===")
    all_clips = []
    
    # Prepare arguments for workers
    worker_args = [(p, outdir) for p in parts]
    
    # Use ProcessPoolExecutor
    # Limit max_workers to 2 to prevent memory exhaustion (EasyOCR + PyTorch is heavy)
    max_workers = 2
    print(f"[INFO] Using {max_workers} parallel workers for OCR to save RAM.")
    
    with concurrent.futures.ProcessPoolExecutor(max_workers=max_workers) as executor:
        results = executor.map(process_part, worker_args)
        
        for i, clips in enumerate(results):
            all_clips.extend(clips)
            # Delete part after processing
            try:
                os.remove(parts[i])
            except Exception:
                pass

    if not all_clips:
        print("[INFO] No kills detected. Nothing to compile.")
        return

    # 3) Merge all clips
    merged = os.path.join(outdir, "compilation_raw.webm")
    ok = merge_clips(all_clips, merged)
    if not ok or not os.path.exists(merged):
        print("[ERROR] Merging clips failed.")
        return

    # 4) Apply 1.25× speed + Mix BGM in ONE PASS (OPTIMIZED)
    final = os.path.join(outdir, "final_with_bgm.webm")
    apply_speed_and_bgm(merged, final)

    if not os.path.exists(final):
        print(f"[ERROR] Final output not found: {final}")
        return

    print(f"\n✅ DONE → {final}")
    gc.collect()


if __name__ == "__main__":
    # Required for multiprocessing on some platforms (though 'spawn' is default on Mac)
    multiprocessing.set_start_method('spawn', force=True)
    main()
