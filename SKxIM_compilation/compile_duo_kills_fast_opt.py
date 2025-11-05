#!/usr/bin/env python3
"""
compile_duo_kills_fast_opt.py
Fast dual-input kill extractor -> alternating compilation (macOS / M1 friendly).

Features:
- Pre-crops HUD ROI using ffmpeg (fast I/O, tiny frames for OCR).
- Uses PaddleOCR if available (fast). Falls back to EasyOCR.
- Batch OCR + frame-diff skipping to speed detection.
- Extracts clips (stream copy if possible; re-encodes to high quality VP9 fallback).
- Alternates clips between two inputs, merges 2-by-2 (test-mode).
- Mixes looped background music withif __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Fast duo kill extractor -> alternating compilation (WebM).")
    parser.add_argument("--speed", required=True, help="Speedkill input video path")
    parser.add_argument("--immortal", required=True, help="Immortal input video path")
    parser.add_argument("--outdir", default=OUT_DIR_DEFAULT, help="output folder")
    parser.add_argument("--pre", type=float, default=PRE_SEC, help="seconds before detected event")
    parser.add_argument("--post", type=float, default=POST_SEC, help="seconds after detected event")
    parser.add_argument("--ocr_interval", type=float, default=OCR_INTERVAL, help="seconds between OCR samples")
    parser.add_argument("--ocr_workers", type=int, default=MAX_OCR_WORKERS, help="OCR worker threads")
    parser.add_argument("--test", action="store_true", help="Test mode: process only one clip from each input")
    args = parser.parse_args()
    ap.add_argument("--test", action="store_true", help="Test mode: process only one clip from each input")io (50% game / 50% BGM).
- Outputs a high-quality WebM compilation.
"""

import os
import sys
import argparse
import subprocess
import shutil
import random
import math
import time
import gc
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

# ----------------- CONFIG -----------------
KILL_KEYWORDS = ["enemy downed", "ENEMY DOWNED", "Enemy Downed"]   # multiple case variants
PRE_SEC = 5
POST_SEC = 5
OCR_INTERVAL = 0.5            # sample more frequently (was 0.8)
OCR_RESIZE = 0.6              # increased for better text recognition (was 0.45)
FRAME_DIFF_THRESHOLD = 8.0    # more permissive frame diff threshold (was 6.0)
OCR_BATCH_SIZE = 4            # reduced batch size for more frequent checks (was 8)
MAX_OCR_WORKERS = 2
BGM_DIR = "background_musics"
OUT_DIR_DEFAULT = "output"
TMP_DIR = "tmp_fast"
ROI_NORM = (0.05, 0.60, 0.25, 0.35)  # updated ROI position based on debug images

# Test mode configs
SINGLE_CLIP_PREFIX = "test_clip"      # prefix for test mode clip files
TEST_MERGED_NAME = "test_merged.webm"  # name for test mode merged output
TEST_MODE = False             # Test mode flag (controlled by --test argument)

# VP9 settings for fallback re-encode (high quality)
VP9_CRF = 18
VP9_THREADS = 4

# ------------------------------------------

def run(cmd, check=True):
    return subprocess.run(cmd, capture_output=True, text=True, check=check)

def require_ffmpeg():
    try:
        run(["ffmpeg", "-version"])
    except Exception:
        print("[ERROR] ffmpeg not found in PATH. Install: brew install ffmpeg")
        sys.exit(1)

# --- OCR init: Use EasyOCR for better text detection ---
def init_ocr():
    try:
        import torch
        use_mps = torch.backends.mps.is_available()
    except Exception:
        use_mps = False
    try:
        import easyocr
        reader = easyocr.Reader(['en'], gpu=use_mps)
        print(f"[INFO] Using EasyOCR (MPS available: {use_mps})")
        return ("easyocr", reader)
    except Exception:
        print("[ERROR] EasyOCR not available. Install with: pip install easyocr")
        sys.exit(1)

# --- pre-crop HUD ROI into a small video to reduce I/O and OCR cost ---
def pre_crop_roi(src_video, out_roi_video, roi_norm=ROI_NORM):
    """
    Uses ffmpeg crop filter to produce a small ROI-only video for faster OCR.
    roi_norm = (y, x, h, w) normalized to video dims.
    """
    # probe resolution
    try:
        r = run(["ffprobe", "-v", "error", "-select_streams", "v:0",
                 "-show_entries", "stream=width,height", "-of", "default=noprint_wrappers=1:nokey=1", src_video])
        lines = [l.strip() for l in r.stdout.splitlines() if l.strip()]
        width = int(lines[0]); height = int(lines[1])
    except Exception:
        # fallback use 1920x1080
        width, height = 1920, 1080

    y, x, h, w = roi_norm
    crop_x = int(width * x)
    crop_y = int(height * y)
    crop_w = int(width * w)
    crop_h = int(height * h)
    os.makedirs(os.path.dirname(out_roi_video) or ".", exist_ok=True)

    vf = f"crop={crop_w}:{crop_h}:{crop_x}:{crop_y}"
    cmd = ["ffmpeg", "-nostdin", "-y", "-i", src_video, "-vf", vf, "-an", "-c:v", "libx264", "-crf", "28", out_roi_video]
    # produce small, low-quality ROI video for OCR only
    run(cmd)
    return out_roi_video

# --- OCR helper: optimized for EasyOCR ---
def ocr_on_image(ocr_type, ocr_reader, img_bgr):
    # img_bgr is an OpenCV BGR numpy image
    try:
        # Try to enhance contrast a bit for better text detection
        import cv2
        import numpy as np
        
        # Convert to grayscale and apply CLAHE
        gray = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2GRAY)
        clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8,8))
        enhanced = clahe.apply(gray)
        
        # Detect text with higher contrast threshold
        res = ocr_reader.readtext(enhanced, detail=0, contrast_ths=0.2, text_threshold=0.6)
        text = " ".join(res).strip()
        return text
    except Exception as e:
        print(f"[WARN] OCR error: {str(e)[:100]}")
        return ""

# --- detect kill timestamps using the pre-cropped ROI video ---
def detect_kills_from_roi(roi_video, ocr_type, ocr_reader, interval=OCR_INTERVAL, resize=OCR_RESIZE,
                          diff_thresh_pct=FRAME_DIFF_THRESHOLD, batch_size=OCR_BATCH_SIZE, keyword_list=KILL_KEYWORDS):
    print(f"[DEBUG] Starting detection with: interval={interval}s, resize={resize}, diff_thresh={diff_thresh_pct}%")
    print(f"[DEBUG] Looking for keywords: {keyword_list}")
    print(f"[DEBUG] Using OCR type: {ocr_type}")
    import cv2
    import numpy as np
    cap = cv2.VideoCapture(roi_video)
    if not cap.isOpened():
        print(f"[ERROR] cannot open ROI video {roi_video}")
        return []

    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
    duration = frame_count / fps if frame_count else None
    # sample every `interval` seconds by moving by frames
    step_frames = max(1, int(round(interval * fps)))

    # We'll iterate sequentially (fast), compute diff on downscaled grayscale ROI frames
    found_times = []
    last_found = -1e9

    # Precalculate frame indices to read
    total_frames = frame_count if frame_count else int(math.ceil((duration or 0) * fps))
    frame_indices = list(range(0, total_frames, step_frames))
    # Use batch OCR
    pending = []  # (time_sec, frame_img)
    prev_gray = None

    for idx in frame_indices:
        cap.set(cv2.CAP_PROP_POS_FRAMES, idx)
        ok, frame = cap.read()
        if not ok:
            continue
        # optionally downscale for diff
        small = cv2.resize(frame, (0,0), fx=0.5, fy=0.5, interpolation=cv2.INTER_AREA)
        gray = cv2.cvtColor(small, cv2.COLOR_BGR2GRAY)
        skip = False
        if prev_gray is not None:
            diff = cv2.absdiff(gray, prev_gray)
            mean_diff = float(diff.mean())
            mean_pct = (mean_diff / 255.0) * 100.0
            if mean_pct < diff_thresh_pct:
                skip = True
        prev_gray = gray

        if skip:
            continue

        # prepare full ROI frame (original roi video frame)
        # optionally resize for OCR to save cycles
        if resize != 1.0:
            ocr_img = cv2.resize(frame, (0,0), fx=resize, fy=resize, interpolation=cv2.INTER_AREA)
        else:
            ocr_img = frame

        sec = idx / fps
        pending.append((sec, ocr_img.copy()))

        # when batch ready -> run OCR
        if len(pending) >= batch_size:
            # run OCR in current thread (we can parallelize with ThreadPoolExecutor if needed)
            for sec_stamp, img in pending:
                text = ocr_on_image(ocr_type, ocr_reader, img)
                if text:
                    tl = text.lower()
                    for kw in keyword_list:
                        if kw in tl and (sec_stamp - last_found) > (PRE_SEC + POST_SEC - 0.5):
                            found_times.append(sec_stamp)
                            last_found = sec_stamp
                            print(f"[FOUND] ROI @ {sec_stamp:.2f}s -> '{kw}'")
                            break
            pending = []

    # final pending
    for sec_stamp, img in pending:
        text = ocr_on_image(ocr_type, ocr_reader, img)
        if text:
            tl = text.lower()
            for kw in KILL_KEYWORDS:
                if kw in tl and (sec_stamp - last_found) > (PRE_SEC + POST_SEC - 0.5):
                    found_times.append(sec_stamp)
                    last_found = sec_stamp
                    print(f"[FOUND] ROI @ {sec_stamp:.2f}s -> '{kw}'")
                    break

    cap.release()
    # Sort and unique-ish
    found_times = sorted(found_times)
    return found_times

# --- wrapper: detect kills in original video using ROI crop trick ---
def detect_kills(video_path, ocr_type, ocr_reader, roi_norm=ROI_NORM, tmp_root=TMP_DIR, **kwargs):
    os.makedirs(tmp_root, exist_ok=True)
    base = Path(video_path).stem
    roi_vid = os.path.join(tmp_root, f"{base}_roi.mp4")
    pre_crop_roi(video_path, roi_vid, roi_norm=roi_norm)
    times = detect_kills_from_roi(roi_vid, ocr_type, ocr_reader, **kwargs)
    # delete roi video after detection to save space
    try:
        os.remove(roi_vid)
    except Exception:
        pass
    return times

# --- extract clips from original full-resolution file ---
def extract_clips(video_path, timestamps, out_dir, pre=PRE_SEC, post=POST_SEC):
    os.makedirs(out_dir, exist_ok=True)
    extracted = []

    # Check if source is HDR by probing color metadata
    is_hdr = False
    try:
        r = run([
            "ffprobe",
            "-v", "error",
            "-select_streams", "v:0",
            "-show_entries", "stream=color_space,color_transfer,color_primaries,pix_fmt",
            "-of", "default=noprint_wrappers=1:nokey=1",
            video_path
        ])
        vals = [l.strip().lower() for l in r.stdout.splitlines() if l.strip()]
        # Check for HDR indicators in metadata
        if any("bt2020" in v or "pq" in v or "smpte2084" in v or "2100" in v or "10le" in v for v in vals):
            is_hdr = True
            print(f"[INFO] Detected HDR content in {os.path.basename(video_path)} - will normalize to SDR")
    except Exception:
        pass

    for i, t in enumerate(timestamps, start=1):
        start = max(0.0, t - pre)
        dur = pre + post
        out_path = os.path.join(out_dir, f"{Path(video_path).stem}_clip_{i:03d}.webm")

        # Always normalize color to ensure consistency
        vf_filters = []
        
        # More conservative HDR to SDR conversion
        if is_hdr:
            vf_filters.extend([
                # Initial HDR to linear conversion
                "zscale=t=linear:npl=100:pin=bt2020:tin=smpte2084",
                # Tonemap with more conservative settings
                "zscale=t=linear:p=bt709:m=bt709",
                "tonemap=tonemap=hable:desat=0:peak=100:threshold=0.7",
                # Finalize color space conversion
                "zscale=t=bt709:m=bt709:r=tv",
                "format=yuv420p"
            ])
        else:
            # For SDR, ensure consistent color space
            vf_filters.extend([
                "zscale=p=bt709:t=bt709:m=bt709",
                "format=yuv420p"
            ])

        # Build ffmpeg command with color normalization
        cmd = [
            "ffmpeg", "-nostdin", "-y",
            "-ss", f"{start:.3f}",
            "-t", f"{dur:.3f}",
            "-i", video_path,
            "-vf", ",".join(vf_filters),
            "-c:v", "libvpx-vp9",
            "-crf", str(VP9_CRF),
            "-b:v", "0",
            "-pix_fmt", "yuv420p",
            "-color_primaries", "bt709",
            "-color_trc", "bt709",
            "-colorspace", "bt709",
            "-c:a", "libopus",
            "-b:a", "128k",
            out_path
        ]
        
        try:
            run(cmd)
            extracted.append(out_path)
            print(f"[EXTRACT - normalized] {os.path.basename(out_path)} ({start:.1f}s → {start+dur:.1f}s)")
        except subprocess.CalledProcessError as e:
            print(f"[ERROR] extraction failed for {os.path.basename(video_path)} at {t}: {e}")
            continue

    return extracted

# --- interleave two lists alternately ---
def interleave_lists(a, b):
    out = []
    la, lb = len(a), len(b)
    i = 0
    while i < la or i < lb:
        if i < la:
            out.append(a[i])
        if i < lb:
            out.append(b[i])
        i += 1
    return out

# --- concat-copy if compatible else normalize & concat ---
def concat_copy_if_compatible(clips, out_path):
    os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
    if not clips:
        return False
    if len(clips) == 1:
        shutil.copy2(clips[0], out_path)
        print(f"[COPIED] {os.path.basename(out_path)}")
        return True
    # write list
    list_file = os.path.join(os.path.dirname(out_path), "concat_list.txt")
    with open(list_file, "w", encoding="utf-8") as f:
        for p in clips:
            f.write(f"file '{os.path.abspath(p)}'\n")
    try:
        run(["ffmpeg", "-nostdin", "-y", "-f", "concat", "-safe", "0", "-i", list_file, "-c", "copy", out_path])
        os.remove(list_file)
        print(f"[MERGED] -> {os.path.basename(out_path)}")
        return True
    except subprocess.CalledProcessError:
        # fallback re-encode to normalized lossless-ish VP9, then concat copy
        norms = []
        try:
            for p in clips:
                norm = os.path.splitext(p)[0] + "_norm.webm"
                run(["ffmpeg", "-nostdin", "-y", "-i", p, "-c:v", "libvpx-vp9", "-lossless", "1", "-b:v", "0",
                     "-c:a", "libopus", "-b:a", "128k", norm])
                norms.append(norm)
            with open(list_file, "w", encoding="utf-8") as f:
                for n in norms:
                    f.write(f"file '{os.path.abspath(n)}'\n")
            run(["ffmpeg", "-nostdin", "-y", "-f", "concat", "-safe", "0", "-i", list_file, "-c", "copy", out_path])
            os.remove(list_file)
            for n in norms:
                try: os.remove(n)
                except: pass
            print(f"[MERGED - normalized] -> {os.path.basename(out_path)}")
            return True
        except Exception as e:
            print("[ERROR] merge fallback failed:", e)
            return False

# --- loop & mix bgm with game audio (50/50) producing WebM (video copied if possible) ---
def mix_bgm_with_game(src_webm, bgm_path, out_webm, game_vol=0.5, bgm_vol=0.5):
    tmp_dir = os.path.dirname(out_webm) or "."
    os.makedirs(tmp_dir, exist_ok=True)
    duration = None
    try:
        r = run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                 "-of", "default=noprint_wrappers=1:nokey=1", src_webm])
        duration = float(r.stdout.strip())
    except Exception:
        duration = None

    if duration is None:
        print("[WARN] cannot determine duration for mixing; skipping mix")
        shutil.copy2(src_webm, out_webm)
        return True

    tmp_bgm = os.path.join(tmp_dir, "bgm_looped.opus")
    try:
        # create looped opus file of precise length
        run(["ffmpeg", "-nostdin", "-y", "-stream_loop", "-1", "-i", bgm_path,
             "-t", f"{duration:.3f}", "-vn", "-c:a", "libopus", "-b:a", "128k", tmp_bgm])
    except subprocess.CalledProcessError as e:
        print("[ERROR] failed to create looped bgm:", e.stderr[:200])
        return False

    # mix with amix and set volumes; keep video stream if possible (copy)
    # If src has non-opus audio, ffmpeg will transcode audio to opus
    filter_complex = f"[0:a]volume={game_vol}[ga];[1:a]volume={bgm_vol}[ba];[ga][ba]amix=inputs=2:dropout_transition=0:normalize=0[mixout]"
    cmd = [
        "ffmpeg", "-nostdin", "-y",
        "-i", src_webm, "-i", tmp_bgm,
        "-map", "0:v",
        "-filter_complex", filter_complex,
        "-map", "[mixout]",
        "-c:v", "copy",
        "-c:a", "libopus", "-b:a", "128k",
        out_webm
    ]
    try:
        run(cmd)
        try: os.remove(tmp_bgm)
        except: pass
        print(f"[AUDIO MIXED] -> {os.path.basename(out_webm)}")
        return True
    except subprocess.CalledProcessError as e:
        print("[ERROR] audio mixing failed:", e.stderr[:400])
        try: os.remove(tmp_bgm)
        except: pass
        return False

# ----------------- HIGH LEVEL PIPELINE -----------------
def compile_duo_kills(speed_path, immortal_path, outdir=OUT_DIR_DEFAULT, pre_sec=PRE_SEC, post_sec=POST_SEC,
                   interval=OCR_INTERVAL, workers=MAX_OCR_WORKERS, test_mode=False):
    require_ffmpeg()
    ocr_type, ocr_reader = init_ocr()
    
    # Configure runtime settings
    global OCR_INTERVAL, MAX_OCR_WORKERS, PRE_SEC, POST_SEC, TEST_MODE
    OCR_INTERVAL = interval
    MAX_OCR_WORKERS = workers
    PRE_SEC = pre_sec
    POST_SEC = post_sec
    TEST_MODE = test_mode

    script_dir = os.path.abspath(os.path.dirname(__file__))
    out_root = os.path.abspath(outdir or OUT_DIR_DEFAULT)
    tmp_root = os.path.join(script_dir, TMP_DIR)
    a_tmp = os.path.join(tmp_root, "a")
    b_tmp = os.path.join(tmp_root, "b")
    merged_tmp = os.path.join(tmp_root, "merged_pairs")
    final_tmp = os.path.join(tmp_root, "final_mixed")
    for p in [out_root, a_tmp, b_tmp, merged_tmp, final_tmp]:
        os.makedirs(p, exist_ok=True)

    # ---------------------------------------------------------------------
    # 1) Detect kills in each input (uses ROI pre-crop internally)
    # ---------------------------------------------------------------------
    print("[STEP] detecting kills in input A:", speed_path)
    kills_a = detect_kills(speed_path, ocr_type, ocr_reader, roi_norm=ROI_NORM,
                           tmp_root=tmp_root, interval=interval, resize=OCR_RESIZE,
                           diff_thresh_pct=FRAME_DIFF_THRESHOLD, batch_size=OCR_BATCH_SIZE)
    if test_mode and kills_a:
        print("[TEST MODE] Taking only first kill from input A")
        kills_a = [kills_a[0]]  # Take only the first kill for testing
    print(f"[INFO] found {len(kills_a)} kills in A")

    print("[STEP] detecting kills in input B:", immortal_path)
    kills_b = detect_kills(immortal_path, ocr_type, ocr_reader, roi_norm=ROI_NORM,
                           tmp_root=tmp_root, interval=interval, resize=OCR_RESIZE,
                           diff_thresh_pct=FRAME_DIFF_THRESHOLD, batch_size=OCR_BATCH_SIZE)
    if test_mode and kills_b:
        print("[TEST MODE] Taking only first kill from input B")
        kills_b = [kills_b[0]]  # Take only the first kill for testing
    print(f"[INFO] found {len(kills_b)} kills in B")

    # ---------------------------------------------------------------------
    # 2) Extract clips (in test mode, only one from each input)
    # ---------------------------------------------------------------------
    if test_mode:
        print("[TEST MODE] Extracting only first clip from each input")
        if kills_a:
            clips_a = extract_clips(speed_path, [kills_a[0]], a_tmp, pre=pre_sec, post=post_sec)
        else:
            clips_a = []
            print("[TEST MODE WARNING] No kills found in speedkill input")
            
        if kills_b:
            clips_b = extract_clips(immortal_path, [kills_b[0]], b_tmp, pre=pre_sec, post=post_sec)
        else:
            clips_b = []
            print("[TEST MODE WARNING] No kills found in immortal input")
    else:
        clips_a = extract_clips(speed_path, kills_a, a_tmp, pre=pre_sec, post=post_sec)
        clips_b = extract_clips(immortal_path, kills_b, b_tmp, pre=pre_sec, post=post_sec)

    clips_a.sort(); clips_b.sort()
    alternating = interleave_lists(clips_a, clips_b)
    print(f"[INFO] Number of clips to process: {len(alternating)}")

    # ---------------------------------------------------------------------
    # 3) Merge clips
    # ---------------------------------------------------------------------
    merged_pairs = []
    if test_mode:
        if len(clips_a) > 0 and len(clips_b) > 0:
            # Take exactly one from each for test mode
            test_pair = [clips_a[0], clips_b[0]]
            out_m = os.path.join(merged_tmp, TEST_MERGED_NAME)
            concat_copy_if_compatible(test_pair, out_m)
            merged_pairs.append(out_m)
            print("[TEST MODE] Successfully merged one test clip from each input")
        else:
            print("[TEST MODE WARNING] Need at least one clip from each input for test merge")
    else:
        # Normal mode: merge all pairs
        for i in range(0, len(alternating), 2):
            pair = alternating[i:i+2]
            out_m = os.path.join(merged_tmp, f"merged_pair_{(i//2)+1:03d}.webm")
            concat_copy_if_compatible(pair, out_m)
            merged_pairs.append(out_m)

    # ---------------------------------------------------------------------
    # 4) Mix background music (50/50) if available; keep WebM outputs
    # ---------------------------------------------------------------------
    bgm_files = []
    bgm_folder = os.path.join(script_dir, BGM_DIR)
    if os.path.isdir(bgm_folder):
        for f in os.listdir(bgm_folder):
            fp = os.path.join(bgm_folder, f)
            if os.path.isfile(fp) and fp.lower().split('.')[-1] in ("mp3","wav","m4a","aac","opus"):
                bgm_files.append(fp)
    if not bgm_files:
        print("[WARN] No bgm files found; producing compilation without BGM mix")

    final_clips = []
    for i, mp in enumerate(merged_pairs, start=1):
        out_final = os.path.join(final_tmp, f"final_{i:03d}.webm")
        if bgm_files:
            bgm_choice = random.choice(bgm_files)
            ok = mix_bgm_with_game(mp, bgm_choice, out_final, game_vol=0.5, bgm_vol=0.5)
            if not ok:
                shutil.copy2(mp, out_final)
        else:
            shutil.copy2(mp, out_final)
        final_clips.append(out_final)

    # ---------------------------------------------------------------------
    # 5) Final compilation
    # ---------------------------------------------------------------------
    if test_mode:
        if final_clips:
            final_comp = os.path.join(out_root, "test_compilation.webm")
            # In test mode, we should only have one clip to copy
            shutil.copy2(final_clips[0], final_comp)
            print("\n[TEST MODE DONE] Test compilation:", final_comp)
        else:
            print("\n[TEST MODE ERROR] No clips were produced for test compilation")
    else:
        final_comp = os.path.join(out_root, "compilation_final.webm")
        concat_copy_if_compatible(final_clips, final_comp)
        print("\n[DONE] Final compilation:", final_comp)

    # Cleanup tmp
    try:
        shutil.rmtree(tmp_root)
        print("[CLEANUP] removed temp files")
    except Exception:
        pass
    gc.collect()

# ----------------- CLI -----------------
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Fast duo kill extractor -> alternating compilation (WebM).")
    parser.add_argument("--speed", required=True, help="Speedkill input video path")
    parser.add_argument("--immortal", required=True, help="Immortal input video path")
    parser.add_argument("--outdir", default=OUT_DIR_DEFAULT, help="output folder")
    parser.add_argument("--pre", type=float, default=PRE_SEC, help="seconds before detected event")
    parser.add_argument("--post", type=float, default=POST_SEC, help="seconds after detected event")
    parser.add_argument("--ocr_interval", type=float, default=OCR_INTERVAL, help="seconds between OCR samples")
    parser.add_argument("--ocr_workers", type=int, default=MAX_OCR_WORKERS, help="OCR worker threads")
    parser.add_argument("--test", action="store_true", help="Test mode: process only one clip from each input")
    args = parser.parse_args()

    try:
        compile_duo_kills(
            args.speed, args.immortal, args.outdir,
            pre_sec=args.pre, post_sec=args.post,
            interval=args.ocr_interval, workers=args.ocr_workers,
            test_mode=args.test
        )
    except KeyboardInterrupt:
        print("[INTERRUPT] stopped by user")
        sys.exit(1)
