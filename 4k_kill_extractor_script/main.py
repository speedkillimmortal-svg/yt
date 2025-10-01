#!/usr/bin/env python3
"""
kill_extractor_yolo_m1_webm.py
Optimized kill-clip extractor for M1 Mac (supports EasyOCR with MPS or PaddleOCR).
- Keeps output in .webm format (lossless, no quality loss).
- Splits large files into manageable parts.
- Optionally uses YOLO to auto-detect kill-feed region.
"""

import os
import sys
import cv2
import ffmpeg
import subprocess
from concurrent.futures import ThreadPoolExecutor

# === USER CONFIGURATION ===
KILL_KEYWORD = "immortal"       # keyword to detect in kill-feed
PRE_SEC = 5                     # seconds before kill
POST_SEC = 5                    # seconds after kill
NUM_PARTS = 4                   # split big video into parts
OCR_INTERVAL = 0.5              # OCR sampling interval (seconds)
OCR_RESIZE = 0.5                # resize factor before OCR
DETECT_RESIZE = 0.5             # resize for YOLO detection
MAX_THREADS = 2                 # OCR parallelism
OCR_ENGINE = "easyocr"          # "easyocr" or "paddleocr"
YOLO_CONF_THRESH = 0.3          # YOLO confidence threshold
YOLO_SAMPLE_FRAMES = 20         # frames to sample for YOLO box
COOLDOWN_SEC = PRE_SEC + POST_SEC  # duplicate detection cooldown

# === OCR Setup ===
use_mps = False
try:
    import torch
    use_mps = torch.backends.mps.is_available()
except Exception:
    torch = None

if OCR_ENGINE == "easyocr":
    import easyocr
    print(f"[INFO] Using EasyOCR (MPS available: {use_mps})")
    reader = easyocr.Reader(['en'], gpu=use_mps)

    def ocr_frame(region_bgr):
        if OCR_RESIZE != 1.0:
            region_bgr = cv2.resize(region_bgr, None, fx=OCR_RESIZE, fy=OCR_RESIZE)
        results = reader.readtext(region_bgr, detail=0)
        return " ".join(results).strip()

elif OCR_ENGINE == "paddleocr":
    from paddleocr import PaddleOCR
    print("[INFO] Using PaddleOCR")
    reader = PaddleOCR(use_angle_cls=True, lang='en')

    def ocr_frame(region_bgr):
        if OCR_RESIZE != 1.0:
            region_bgr = cv2.resize(region_bgr, None, fx=OCR_RESIZE, fy=OCR_RESIZE)
        results = reader.ocr(region_bgr, cls=True)
        lines = []
        for r in results:
            try:
                if isinstance(r, list) and len(r) > 1:
                    lines.append(r[1][0])
            except Exception:
                pass
        return " ".join(lines).strip()
else:
    raise ValueError("OCR_ENGINE must be 'easyocr' or 'paddleocr'.")


# === Video Utils ===
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
        out_file = f"{output_prefix}{i+1}.webm"  # keep webm
        cmd = [
            "ffmpeg", "-nostdin", "-loglevel", "error", "-y",
            "-i", input_path, "-ss", str(start), "-t", str(part_length),
            "-c", "copy", out_file
        ]
        print(f"[INFO] Creating part: {out_file} (start={start:.2f}s, len={part_length:.2f}s)")
        subprocess.run(cmd, check=True)
        part_files.append(out_file)
    return part_files


# === Core Extraction ===
def find_and_extract(video_path, output_dir, ocr_interval=OCR_INTERVAL, pre_sec=PRE_SEC, post_sec=POST_SEC):
    os.makedirs(output_dir, exist_ok=True)
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        print(f"[ERROR] Cannot open {video_path}")
        return

    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
    duration = frame_count / fps if fps else 0
    print(f"[INFO] Processing {video_path} | FPS={fps:.2f}, frames={frame_count}, duration={duration:.2f}s")

    # Fallback kill-feed box = left 25% width, middle third height
    cap.set(cv2.CAP_PROP_POS_MSEC, 0)
    ret, frame = cap.read()
    if not ret:
        print("[WARN] Could not read first frame.")
        return
    h, w = frame.shape[:2]
    x1, x2 = 0, int(w * 0.25)
    y1, y2 = int(h * 1/3), int(h * 2/3)
    feed_box = (x1, y1, x2, y2)

    found_times = []
    last_found = -1e9
    sec = 0.0
    executor = ThreadPoolExecutor(max_workers=MAX_THREADS)

    while sec < duration:
        cap.set(cv2.CAP_PROP_POS_MSEC, sec * 1000)
        ret, frame = cap.read()
        if not ret:
            sec += ocr_interval
            continue

        x1, y1, x2, y2 = feed_box
        region = frame[y1:y2, x1:x2]
        text = executor.submit(ocr_frame, region).result()

        if text and KILL_KEYWORD.lower() in text.lower():
            if sec - last_found > COOLDOWN_SEC:
                found_times.append(sec)
                last_found = sec
                print(f"[FOUND] '{KILL_KEYWORD}' at {sec:.2f}s text={text}")
        sec += ocr_interval

    cap.release()
    executor.shutdown(wait=True)

    # Save clips in .webm (lossless copy)
    if found_times:
        for idx, ft in enumerate(found_times, start=1):
            start = max(0.0, ft - pre_sec)
            clip_len = pre_sec + post_sec
            out_file = os.path.join(output_dir, f"{KILL_KEYWORD.lower()}_clip_{idx}.webm")
            print(f"[EXTRACT] {out_file} start={start:.2f}s dur={clip_len:.2f}s")
            (
                ffmpeg
                .input(video_path, ss=start, t=clip_len)
                .output(out_file, c="copy")
                .global_args("-nostdin", "-loglevel", "error")
                .run(overwrite_output=True)
            )
            print(f"[SAVED] {out_file}")
    else:
        print(f"[INFO] No '{KILL_KEYWORD}' found in {video_path}")


# === Main ===
def main():
    script_dir = os.path.dirname(os.path.abspath(__file__))
    video_path = os.path.join(script_dir, "input.webm")
    if not os.path.exists(video_path):
        print("[ERROR] input.webm not found in script folder.")
        sys.exit(1)

    print("[INFO] Splitting video into parts...")
    parts = split_video_into_parts(video_path, num_parts=NUM_PARTS, output_prefix=os.path.join(script_dir, "part"))
    print(f"[INFO] Parts created: {parts}")

    for i, part in enumerate(parts, start=1):
        print(f"\n[INFO] Processing part {i}/{len(parts)} : {part}")
        out_dir = os.path.join(script_dir, f"{KILL_KEYWORD.capitalize()}_clips", f"part{i}")
        find_and_extract(part, out_dir, ocr_interval=OCR_INTERVAL, pre_sec=PRE_SEC, post_sec=POST_SEC)

    print("[DONE] All parts processed.")


if __name__ == "__main__":
    main()
