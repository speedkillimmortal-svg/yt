#!/usr/bin/env python3
"""
Full 4K Kill Extractor to Shorts/Reels Pipeline (Optimized Final Version)
- Extracts "ENEMY DOWNED" clips from input.webm.
- Merges all extracted clips globally (not part-wise) into pairs.
- Converts merged clips into vertical 1080x1920 .webm (YouTube Shorts) and .mp4 (Insta Reels).
- Automatically cleans all temporary files/folders after execution.
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

# === USER CONFIGURATION ===
KILL_KEYWORDS = ["ENEMY DOWNED"]
PRE_SEC = 5
POST_SEC = 5
NUM_PARTS = 4
OCR_INTERVAL = 1.0
OCR_RESIZE = 0.6
MAX_THREADS = 2
COOLDOWN_SEC = PRE_SEC + POST_SEC
TARGET_WIDTH = 1080
TARGET_HEIGHT = 1920

# === OCR Setup ===
use_mps = False
try:
    import torch
    use_mps = torch.backends.mps.is_available()
except Exception:
    torch = None
import easyocr
reader = easyocr.Reader(['en'], gpu=use_mps)
print(f"[INFO] EasyOCR initialized (MPS GPU available: {use_mps})")

# === Utility Functions ===
def ocr_frame(region_bgr):
    if OCR_RESIZE != 1.0:
        region_bgr = cv2.resize(region_bgr, None, fx=OCR_RESIZE, fy=OCR_RESIZE)
    results = reader.readtext(region_bgr, detail=0)
    return " ".join(results).strip()

def get_video_duration(input_path):
    try:
        result = subprocess.run([
            "ffprobe", "-v", "error", "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1", input_path
        ], capture_output=True, text=True, check=True)
        return float(result.stdout.strip())
    except Exception as e:
        print(f"[ERROR] ffprobe failed: {e}")
        return None

def split_video_into_parts(input_path, num_parts=NUM_PARTS, output_prefix="part"):
    duration = get_video_duration(input_path)
    if not duration:
        return []
    part_length = duration / num_parts
    part_files = []
    for i in range(num_parts):
        start = i * part_length
        out_file = f"{output_prefix}{i+1}.webm"
        cmd = [
            "ffmpeg", "-nostdin", "-loglevel", "error", "-y",
            "-i", input_path, "-ss", str(start), "-t", str(part_length),
            "-c", "copy", out_file
        ]
        subprocess.run(cmd, check=True)
        part_files.append(out_file)
        print(f"[INFO] Created part: {out_file} (start={start:.2f}s, len={part_length:.2f}s)")
    return part_files

def merge_clips_together(clip_files, merged_output_path):
    # Handle empty list
    if not clip_files:
        print(f"[SKIP] No clips to merge → {merged_output_path}")
        return

    # If only one clip, copy it (preserve original streams/quality)
    if len(clip_files) == 1:
        src = clip_files[0]
        try:
            os.makedirs(os.path.dirname(merged_output_path), exist_ok=True)
            shutil.copy2(src, merged_output_path)
            print(f"[COPIED] single clip -> {merged_output_path}")
        except Exception as e:
            print(f"[ERROR] copying single clip: {e}")
        return
    list_file = os.path.join(os.path.dirname(merged_output_path), "merge_list.txt")
    with open(list_file, "w") as f:
        for c in clip_files:
            f.write(f"file '{os.path.abspath(c)}'\n")
    cmd = [
        "ffmpeg", "-f", "concat", "-safe", "0", "-i", list_file,
        "-c", "copy", "-y", merged_output_path
    ]
    subprocess.run(cmd, check=True)
    os.remove(list_file)
    print(f"[MERGED] {merged_output_path}")

def find_and_extract(video_path, output_dir):
    os.makedirs(output_dir, exist_ok=True)
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        print(f"[ERROR] Cannot open {video_path}")
        return []
    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
    duration = frame_count / fps
    print(f"[INFO] Processing {video_path} | FPS={fps:.1f}, Duration={duration:.1f}s")

    ret, frame = cap.read()
    if not ret:
        return []
    h, w = frame.shape[:2]
    x1, x2 = int(w * 0.70), w
    y1, y2 = 0, int(h * 0.25)
    feed_box = (x1, y1, x2, y2)

    found_times, last_found = [], -1e9
    executor = ThreadPoolExecutor(max_workers=MAX_THREADS)
    sec = 0.0
    while sec < duration:
        cap.set(cv2.CAP_PROP_POS_MSEC, sec * 1000)
        ret, frame = cap.read()
        if not ret:
            sec += OCR_INTERVAL
            continue
        region = frame[y1:y2, x1:x2]
        text = executor.submit(ocr_frame, region).result()
        if text:
            for kw in KILL_KEYWORDS:
                if kw.lower() in text.lower() and sec - last_found > COOLDOWN_SEC:
                    found_times.append(sec)
                    last_found = sec
                    print(f"[FOUND] '{kw}' at {sec:.2f}s")
        sec += OCR_INTERVAL

    cap.release()
    executor.shutdown(wait=True)
    extracted_files = []

    if found_times:
        for idx, ft in enumerate(found_times, start=1):
            start = max(0.0, ft - PRE_SEC)
            clip_len = PRE_SEC + POST_SEC
            out_file = os.path.join(output_dir, f"downed_clip_{idx}.webm")
            (
                ffmpeg
                .input(video_path, ss=start, t=clip_len)
                .output(out_file, c="copy", loglevel="error")
                .run(overwrite_output=True)
            )
            extracted_files.append(out_file)
    return extracted_files

def merge_all_globally(all_clips, merged_root):
    os.makedirs(merged_root, exist_ok=True)
    merged_outputs = []
    # Merge in groups of 3 to form ~30s clips (if each clip is ~10s)
    idx = 0
    group_count = 0
    while idx < len(all_clips):
        group = all_clips[idx:idx+3]
        group_count += 1
        merged_out = os.path.join(merged_root, f"merged_shorts_{group_count}.webm")
        merge_clips_together(group, merged_out)
        merged_outputs.append(merged_out)
        idx += 3
    print(f"[INFO] Total merged global clips: {len(merged_outputs)}")
    return merged_outputs

# === Shorts Conversion ===
def is_video_file(filename):
    return filename.lower().endswith(('.mp4', '.mov', '.avi', '.mkv', '.webm'))

# --- Background music pool (non-repeating) ---
# Global pool that will be initialized once per run and then consumed without repeats
MUSIC_POOL = []

def init_music_pool(background_music_dir):
    """Populate and shuffle the MUSIC_POOL from the given directory."""
    global MUSIC_POOL
    MUSIC_POOL = []
    if not os.path.exists(background_music_dir):
        return
    files = [f for f in os.listdir(background_music_dir) if f.lower().endswith(('.mp3', '.wav', '.aac', '.m4a'))]
    if not files:
        return
    random.shuffle(files)
    MUSIC_POOL = [os.path.join(background_music_dir, f) for f in files]

def pick_music():
    """Return the next music path from the pool (non-repeating). Returns None if pool exhausted."""
    global MUSIC_POOL
    if not MUSIC_POOL:
        return None
    return MUSIC_POOL.pop()

def convert_to_vertical_webm(input_path, output_path, script_dir):
    icon_path = os.path.join(script_dir, 'generic_icon.png')
    logo_path = os.path.join(script_dir, 'channel_logo.jpg')
    background_music_dir = os.path.join(script_dir, 'background_musics')
    # pick a non-repeating music track from the global pool (initialized in main)
    music_path = pick_music()

    video = (
        ffmpeg
        .input(input_path)
        .filter('scale', -1, TARGET_HEIGHT - 200)
        .filter('crop', f"if(gt(in_w,{TARGET_WIDTH}),{TARGET_WIDTH},in_w)", TARGET_HEIGHT - 200, '(in_w-out_w)/2', 0)
        .filter('pad', TARGET_WIDTH, TARGET_HEIGHT, 0, 0, color='black')
    )

    if os.path.exists(icon_path):
        video = video.overlay(
            ffmpeg.input(icon_path).filter('scale', 300, 200),
            x=0,
            y=TARGET_HEIGHT - 200
        )
    if os.path.exists(logo_path):
        video = video.overlay(
            ffmpeg.input(logo_path).filter('scale', 180, 180),
            x=f'{TARGET_WIDTH}-200',
            y=f'{TARGET_HEIGHT}-190'
        )

    vp9_settings = dict(
        vcodec='libvpx-vp9',
        acodec='libopus',
        crf=30,
        **{"b:v": "0"},
        audio_bitrate='128k',
        **{"deadline": "realtime", "cpu-used": "4"},
        pix_fmt='yuv420p'
    )

    if music_path:
        out = ffmpeg.output(video, ffmpeg.input(music_path, stream_loop=-1).audio, output_path, shortest=None, **vp9_settings)
    else:
        out = ffmpeg.output(video, output_path, **vp9_settings)
    out.global_args('-nostdin', '-loglevel', 'error').overwrite_output().run()

def convert_webm_to_mp4(input_folder, output_folder, label):
    if not os.path.exists(output_folder):
        os.makedirs(output_folder)
    for file in os.listdir(input_folder):
        if file.lower().endswith('.webm'):
            input_path = os.path.join(input_folder, file)
            output_path = os.path.join(output_folder, os.path.splitext(file)[0] + ".mp4")
            crop_filter = "crop=in_h*9/16:in_h:(in_w-out_w)/2:0,scale=1080:1920"
            subprocess.run([
                "ffmpeg", "-i", input_path, "-vf", crop_filter,
                "-c:v", "h264_videotoolbox", "-b:v", "6M", "-maxrate", "8M",
                "-bufsize", "12M", "-c:a", "aac", "-b:a", "128k",
                "-movflags", "+faststart", "-y", output_path
            ], check=True)
    print(f"[DONE] {label} conversion complete → {output_folder}")

# === MAIN PIPELINE ===
def main_pipeline():
    script_dir = os.path.dirname(os.path.abspath(__file__))
    video_path = os.path.join(script_dir, "input.webm")
    if not os.path.exists(video_path):
        print("[ERROR] input.webm not found.")
        sys.exit(1)

    print("[INFO] Splitting video into parts...")
    parts = split_video_into_parts(video_path, num_parts=NUM_PARTS, output_prefix=os.path.join(script_dir, "part"))

    all_extracted = []
    for i, part in enumerate(parts, start=1):
        print(f"\n[INFO] Processing part {i}/{len(parts)}")
        out_dir = os.path.join(script_dir, "Downed_clips", f"part{i}")
        clips = find_and_extract(part, out_dir)
        all_extracted.extend(clips)
        os.remove(part)  # delete part immediately to save space

    if not all_extracted:
        print("[INFO] No ENEMY DOWNED events found.")
        return

    merged_root = os.path.join(script_dir, "Merged_All_Parts")
    merged_outputs = merge_all_globally(all_extracted, merged_root)

    youtube_shorts_dir = os.path.join(script_dir, "youtube_shorts")
    os.makedirs(youtube_shorts_dir, exist_ok=True)

    # initialize music pool (non-repeating) for this run
    background_music_dir = os.path.join(script_dir, 'background_musics')
    init_music_pool(background_music_dir)

    for file in merged_outputs:
        base = os.path.splitext(os.path.basename(file))[0]
        out_path = os.path.join(youtube_shorts_dir, f"{base}_vertical4k.webm")
        convert_to_vertical_webm(file, out_path, script_dir)

    reels_dir = os.path.join(script_dir, "insta_reels")
    convert_webm_to_mp4(youtube_shorts_dir, reels_dir, label="Insta Reels")

    # Cleanup all temporary files/folders
    for folder in ["Downed_clips", "Merged_All_Parts"]:
        shutil.rmtree(os.path.join(script_dir, folder), ignore_errors=True)
    for fname in os.listdir(script_dir):
        if fname.startswith("part") and fname.endswith(".webm"):
            try:
                os.remove(os.path.join(script_dir, fname))
            except Exception:
                pass

    gc.collect()
    print("\n✅ [DONE] All outputs saved in:")
    print(f"   - YouTube Shorts: {youtube_shorts_dir}")
    print(f"   - Insta Reels: {reels_dir}")

if __name__ == "__main__":
    try:
        main_pipeline()
        sys.exit(0)
    except Exception as e:
        print(f"[FATAL ERROR] {e}")
        gc.collect()
        sys.exit(1)

