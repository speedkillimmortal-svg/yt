#!/usr/bin/env python3
"""
kill_extractor_enemy_downed_only_merge_pairs.py
Optimized version:
- Detects "ENEMY DOWNED"
- Extracts clips
- Merges them pairwise per part
- If odd clips -> last 3 merged together
- Stores all merged clips in 'Merged_All_Parts'
"""

import os
import sys
import cv2
import ffmpeg
import subprocess
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
        part_match = re.search(r'part(\d+)\.webm', os.path.basename(video_path))
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

        # pairwise merge (1+2, 3+4, etc.)
        i = 0
        temp_merges = []
        while i < len(clip_list):
            if i + 1 < len(clip_list):
                merged_out = os.path.join(merged_part_dir, f"merged_{part_idx}_{i//2+1}.webm")
                merge_clips_together([clip_list[i], clip_list[i+1]], merged_out)
                temp_merges.append(merged_out)
                i += 2
            else:
                # odd clip remaining
                if temp_merges:
                    print("[MERGE-ODD] Merging leftover with last merged batch...")
                    merge_clips_together([temp_merges[-1], clip_list[i]], temp_merges[-1])
                else:
                    # only one clip total
                    single_copy = os.path.join(merged_part_dir, f"merged_{part_idx}_single.webm")
                    merge_clips_together([clip_list[i]], single_copy)
                i += 1

        merged_all.extend(temp_merges)

    print(f"\n[INFO] Total merged clips across all parts: {len(merged_all)}")
    return merged_all


def main():
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

    print("[DONE] All parts processed and merged.")


if __name__ == "__main__":
    import gc
    try:
        main()
        gc.collect()
        sys.exit(0)
    except Exception as e:
        print(f"[FATAL ERROR] {e}")
        sys.exit(1)
