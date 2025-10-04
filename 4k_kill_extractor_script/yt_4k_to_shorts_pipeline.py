"""
Full 4K Kill Extractor to Shorts/Reels Pipeline
- Step 1: Extracts and merges kill clips from input.webm (using main.py logic)
- Step 2: Converts all merged clips in Merged_All_Parts to vertical 1080x1920 .webm (using convert_for_shorts.py logic)
- Final outputs are in output_clips/
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
        print(f"[INFO] Creating part: {out_file} (start={start:.2f}s, len={part_length:.2f}s)")
        subprocess.run(cmd, check=True)
        part_files.append(out_file)
    return part_files

def merge_clips_together(clip_files, merged_output_path):
    if len(clip_files) < 2:
        print(f"[SKIP] Not enough clips to merge in {os.path.dirname(merged_output_path)}")
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
    print(f"[MERGED] -> {merged_output_path}")
    os.remove(list_file)

def find_and_extract(video_path, output_dir):
    os.makedirs(output_dir, exist_ok=True)
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        print(f"[ERROR] Cannot open {video_path}")
        return []
    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
    duration = frame_count / fps if fps else 0
    print(f"[INFO] Processing {video_path} | FPS={fps:.2f}, frames={frame_count}, duration={duration:.2f}s")
    ret, frame = cap.read()
    if not ret:
        print("[WARN] Could not read first frame.")
        return []
    h, w = frame.shape[:2]
    x1, x2 = int(w * 0.70), w
    y1, y2 = 0, int(h * 0.25)
    feed_box = (x1, y1, x2, y2)
    found_times = []
    last_found = -1e9
    sec = 0.0
    executor = ThreadPoolExecutor(max_workers=MAX_THREADS)
    while sec < duration:
        cap.set(cv2.CAP_PROP_POS_MSEC, sec * 1000)
        ret, frame = cap.read()
        if not ret:
            sec += OCR_INTERVAL
            continue
        x1, y1, x2, y2 = feed_box
        region = frame[y1:y2, x1:x2]
        text = executor.submit(ocr_frame, region).result()
        if text:
            for kw in KILL_KEYWORDS:
                if kw.lower() in text.lower():
                    if sec - last_found > COOLDOWN_SEC:
                        found_times.append(sec)
                        last_found = sec
                        print(f"[FOUND] '{kw}' at {sec:.2f}s text={text}")
        sec += OCR_INTERVAL
    cap.release()
    executor.shutdown(wait=True)
    extracted_files = []
    if found_times:
        import re
        part_match = re.search(r'part(\d+)\\?.webm', os.path.basename(video_path))
        part_num = part_match.group(1) if part_match else 'X'
        for idx, ft in enumerate(found_times, start=1):
            start = max(0.0, ft - PRE_SEC)
            clip_len = PRE_SEC + POST_SEC
            out_file = os.path.join(output_dir, f"downed_clip_part_{part_num}_{idx}.webm")
            print(f"[EXTRACT] {out_file} start={start:.2f}s dur={clip_len:.2f}s")
            (
                ffmpeg
                .input(video_path, ss=start, t=clip_len)
                .output(out_file, c="copy")
                .global_args("-nostdin", "-loglevel", "error")
                .run(overwrite_output=True)
            )
            extracted_files.append(out_file)
            print(f"[SAVED] {out_file}")
    else:
        print(f"[INFO] No '{KILL_KEYWORDS[0]}' found in {video_path}")
    return extracted_files

def merge_pairs_and_store_all(parts_clips, merged_root):
    os.makedirs(merged_root, exist_ok=True)
    merged_all = []
    for part_idx, clip_list in enumerate(parts_clips, start=1):
        if not clip_list:
            continue
        print(f"\n[MERGE] Processing part {part_idx} merges...")
        merged_part_dir = os.path.join(merged_root, f"part{part_idx}")
        os.makedirs(merged_part_dir, exist_ok=True)
        i = 0
        temp_merges = []
        while i < len(clip_list):
            if i + 1 < len(clip_list):
                merged_out = os.path.join(merged_part_dir, f"merged_{part_idx}_{i//2+1}.webm")
                merge_clips_together([clip_list[i], clip_list[i+1]], merged_out)
                temp_merges.append(merged_out)
                i += 2
            else:
                if temp_merges:
                    print("[MERGE-ODD] Merging leftover with last merged batch...")
                    merge_clips_together([temp_merges[-1], clip_list[i]], temp_merges[-1])
                else:
                    single_copy = os.path.join(merged_part_dir, f"merged_{part_idx}_single.webm")
                    merge_clips_together([clip_list[i]], single_copy)
                i += 1
        merged_all.extend(temp_merges)
    print(f"\n[INFO] Total merged clips across all parts: {len(merged_all)}")
    return merged_all

# === Shorts Conversion ===
def is_video_file(filename):
    return filename.lower().endswith(('.mp4', '.mov', '.avi', '.mkv', '.webm'))

def pick_random_music(background_music_dir):
    if not os.path.exists(background_music_dir):
        return None
    music_files = [f for f in os.listdir(background_music_dir) if f.lower().endswith(('.mp3', '.wav', '.aac', '.m4a'))]
    if not music_files:
        return None
    return os.path.join(background_music_dir, random.choice(music_files))

def convert_to_vertical_webm(input_path, output_path, script_dir):
    TARGET_WIDTH = 1080
    TARGET_HEIGHT = 1920
    bottom_bar_height = 200
    video_height = TARGET_HEIGHT - bottom_bar_height
    icon_path = os.path.join(script_dir, 'generic_icon.png')
    logo_path = os.path.join(script_dir, 'channel_logo.jpg')
    background_music_dir = os.path.join(script_dir, 'background_musics')
    music_path = pick_random_music(background_music_dir)
    video = (
        ffmpeg
        .input(input_path)
        .filter('scale', -1, video_height)
        .filter('crop', f"if(gt(in_w,{TARGET_WIDTH}),{TARGET_WIDTH},in_w)", video_height, '(in_w-out_w)/2', 0)
        .filter('pad', TARGET_WIDTH, TARGET_HEIGHT, 0, 0, color='black')
    )
    if os.path.exists(icon_path):
        video = video.overlay(
            ffmpeg.input(icon_path).filter('scale', TARGET_WIDTH, bottom_bar_height),
            x=0,
            y=TARGET_HEIGHT - bottom_bar_height
        )
    if os.path.exists(logo_path):
        video = video.overlay(
            ffmpeg.input(logo_path).filter('scale', 180, 180),
            x=f'{TARGET_WIDTH}-180-20',
            y=f'{TARGET_HEIGHT}-180-10'
        )
    vp9_settings = dict(
        vcodec='libvpx-vp9',
        acodec='libopus',
        crf=32,
        **{"b:v": "0"},
        audio_bitrate='128k',
        **{"deadline": "realtime", "cpu-used": "4"},
        pix_fmt='yuv420p'
    )
    if music_path:
        music_input = ffmpeg.input(music_path, stream_loop=-1)
        out = (
            ffmpeg
            .output(
                video,
                music_input.audio,
                output_path,
                shortest=None,
                **vp9_settings
            )
            .global_args('-nostdin', '-loglevel', 'error')
            .overwrite_output()
        )
    else:
        out = (
            ffmpeg
            .output(
                video,
                output_path,
                **vp9_settings
            )
            .global_args('-nostdin', '-loglevel', 'error')
            .overwrite_output()
        )
    out.run()

def main_pipeline():
    script_dir = os.path.dirname(os.path.abspath(__file__))
    video_path = os.path.join(script_dir, "input.webm")
    if not os.path.exists(video_path):
        print("[ERROR] input.webm not found in script folder.")
        sys.exit(1)
    print("[INFO] Splitting video into parts...")
    parts = split_video_into_parts(video_path, num_parts=NUM_PARTS, output_prefix=os.path.join(script_dir, "part"))
    print(f"[INFO] Parts created: {parts}")
    parts_clips = []
    for i, part in enumerate(parts, start=1):
        print(f"\n[INFO] Processing part {i}/{len(parts)} : {part}")
        out_dir = os.path.join(script_dir, "Downed_clips", f"part{i}")
        clips = find_and_extract(part, out_dir)
        parts_clips.append(clips)
    merged_root = os.path.join(script_dir, "Merged_All_Parts")
    merge_pairs_and_store_all(parts_clips, merged_root)
    # === Shorts Conversion ===
    output_dir = os.path.join(script_dir, "output_clips")
    os.makedirs(output_dir, exist_ok=True)
    for root, dirs, files in os.walk(merged_root):
        for fname in files:
            if is_video_file(fname):
                in_path = os.path.join(root, fname)
                base, _ = os.path.splitext(fname)
                out_path = os.path.join(output_dir, f"{base}_vertical4k.webm")
                print(f'Converting {fname} → {out_path}')
                convert_to_vertical_webm(in_path, out_path, script_dir)
                print(f'Saved: {out_path}')
    print("[DONE] Pipeline complete. All outputs in output_clips/")

if __name__ == "__main__":
    try:
        main_pipeline()
        gc.collect()
        sys.exit(0)
    except Exception as e:
        print(f'[FATAL ERROR] {e}')
        sys.exit(1)
