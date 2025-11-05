#!/usr/bin/env python3
"""
compile_duo_kills_fast.py

Optimized dual-input kill extractor + alternating compilation for macOS (M1).
- Uses EasyOCR (MPS if available).
- Detects "ENEMY DOWNED" in a tuned HUD ROI using sparse sampling + f        if is_hdr:
            # Enhanced HDR to SDR conversion with vivid colors
            vf_filters = (
                # Initial HDR to linear conversion with higher brightness
                "zscale=t=linear:npl=400:pin=bt2020:tin=smpte2084,"
                "format=gbrpf32le,"
                # Enhanced tone mapping with better highlights and colors
                "zscale=t=linear:p=bt709:m=bt709,"
                "tonemap=tonemap=mobius:desat=0:peak=300:exposure=1.5,"
                # Final color enhancement
                "zscale=t=bt709:m=bt709:r=tv,"
                "eq=brightness=0.05:contrast=1.1:saturation=1.4,"
                "colorlevels=rimin=0:gimin=0:bimin=0:rimax=0.95:gimax=0.95:bimax=0.95,"
                "format=yuv420p"
            )
            cmd.extend([
                "-vf", vf_filters,
                "-c:v", "libvpx-vp9",
                "-crf", "20",
                "-b:v", "0",
                "-row-mt", "1",
                "-pix_fmt", "yuv420p",
                "-color_primaries", "bt709",
                "-color_trc", "bt709",
                "-colorspace", "bt709",
                "-c:a", "copy"
            ])xports high-quality WebM (VP9 + Opus) and mixes background music 50/50 with game audio.
- Alternates clips from the two inputs (Speedkill / Immortal) into one compilation.
- Merges clips 2-by-2 (test-mode merging). Deletes temp files at the end.
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

# --- Configurable defaults ---
KILL_KEYWORDS = ["ENEMY DOWNED"]
PRE_SEC = 5
POST_SEC = 5
OCR_INTERVAL = 0.8           # seconds between OCR samples (larger -> faster but risk missing)
OCR_RESIZE = 0.6             # scale down before OCR (faster)
FRAME_DIFF_THRESHOLD = 10.0  # mean absolute difference threshold (%) to skip static frames
MAX_OCR_WORKERS = 2
BGM_DIRNAME = "background_musics"
OUT_DIR_DEFAULT = "output"
TEMP_DIRNAME = "tmp_duo"
ROI_NORM = (0.05, 0.60, 0.25, 0.35)  # (y, x, h, w) normalized HUD region; bottom-right-ish tuned for your HUD

# Final webm settings (keeps quality; VP9 lossless isn't necessary — use good CRF)
VP9_CRF = 28  # lower -> better quality (set 18-30). 28 is a good balance for file size/quality.
VP9_THREADS = 4

# --- Ensure ffmpeg is available ---
def require_ffmpeg():
    try:
        subprocess.run(["ffmpeg", "-version"], capture_output=True, check=True)
    except Exception:
        print("[ERROR] ffmpeg not found in PATH. Install via homebrew: brew install ffmpeg")
        sys.exit(1)

# --- EasyOCR setup (MPS if available on M1) ---
def init_easyocr():
    try:
        import torch
        use_mps = torch.backends.mps.is_available()
    except Exception:
        use_mps = False
    try:
        import easyocr
    except Exception:
        print("[ERROR] easyocr not installed. Install: python3 -m pip install easyocr")
        sys.exit(1)
    print(f"[INFO] EasyOCR initialized (MPS available: {use_mps})")
    reader = easyocr.Reader(['en'], gpu=use_mps)
    return reader

# --- Utility helpers ---
def run(cmd, check=True):
    # helper to run subprocess with streaming output suppressed
    # return CompletedProcess
    return subprocess.run(cmd, capture_output=True, text=True, check=check)

def get_duration(path):
    try:
        r = subprocess.run([
            "ffprobe", "-v", "error", "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1", path
        ], capture_output=True, text=True, check=True)
        return float(r.stdout.strip())
    except Exception:
        return None

def probe_video_props(path):
    try:
        r = subprocess.run([
            "ffprobe", "-v", "error", "-select_streams", "v:0",
            "-show_entries", "stream=codec_name,width,height,profile,pix_fmt,r_frame_rate",
            "-of", "json", path
        ], capture_output=True, text=True, check=True)
        import json
        info = json.loads(r.stdout)
        streams = info.get("streams") or []
        if not streams:
            return {}
        s = streams[0]
        return s
    except Exception:
        return {}

# --- ROI helpers ---
def roi_pixel_box(frame_w, frame_h, roi_norm=ROI_NORM):
    y, x, h, w = roi_norm
    x_px = int(frame_w * x)
    y_px = int(frame_h * y)
    w_px = int(frame_w * w)
    h_px = int(frame_h * h)
    # clamp
    x_px = max(0, min(frame_w-1, x_px))
    y_px = max(0, min(frame_h-1, y_px))
    w_px = max(1, min(frame_w-x_px, w_px))
    h_px = max(1, min(frame_h-y_px, h_px))
    return x_px, y_px, w_px, h_px

# --- OCR worker wrapper ---
def ocr_region_text(reader, region_bgr):
    # region as numpy BGR image
    try:
        import cv2
        if OCR_RESIZE != 1.0:
            region_bgr = cv2.resize(region_bgr, None, fx=OCR_RESIZE, fy=OCR_RESIZE, interpolation=cv2.INTER_AREA)
        results = reader.readtext(region_bgr, detail=0)
        return " ".join(results).strip()
    except Exception:
        return ""

# --- Core: detect kill timestamps in a source video ---
def detect_kills(video_path, reader, roi_norm=ROI_NORM, interval=OCR_INTERVAL, max_workers=MAX_OCR_WORKERS, diff_thresh_pct=FRAME_DIFF_THRESHOLD):
    import cv2
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        print(f"[ERROR] cannot open {video_path}")
        return []

    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
    duration = frame_count / fps if fps else get_duration(video_path) or 0.0
    print(f"[SCAN] {os.path.basename(video_path)} dur={duration:.1f}s fps={fps:.1f}")

    # determine ROI in pixels using first frame
    cap.set(cv2.CAP_PROP_POS_MSEC, 0)
    ok, frame0 = cap.read()
    if not ok:
        cap.release()
        return []
    h, w = frame0.shape[:2]
    rx, ry, rw, rh = roi_pixel_box(w, h, roi_norm)

    # We'll sample frames every `interval` seconds; do a lightweight frame-diff test to skip
    times = []
    last_found = -1e9
    sec = 0.0

    executor = ThreadPoolExecutor(max_workers=max_workers)
    futures = []

    prev_roi_gray = None
    import numpy as np
    while sec < duration:
        cap.set(cv2.CAP_PROP_POS_MSEC, sec * 1000)
        ok, frame = cap.read()
        if not ok:
            sec += interval
            continue
        roi = frame[ry:ry+rh, rx:rx+rw]
        # quick frame difference (grayscale)
        gray = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)
        if prev_roi_gray is not None:
            diff = cv2.absdiff(gray, prev_roi_gray)
            mean_diff = diff.mean()  # 0..255
            # Normalize by 255 to percent
            mean_pct = (mean_diff / 255.0) * 100.0
            if mean_pct < diff_thresh_pct:
                # scene largely unchanged — skip OCR to save CPU
                prev_roi_gray = gray
                sec += interval
                continue
        prev_roi_gray = gray
        # submit OCR job
        futures.append((sec, executor.submit(ocr_region_text, reader, roi.copy())))
        sec += interval

    # gather results
    found_times = []
    for sec_stamp, fut in futures:
        text = ""
        try:
            text = fut.result(timeout=30)
        except Exception:
            text = ""
        if text:
            tclean = text.lower()
            for kw in KILL_KEYWORDS:
                if kw.lower() in tclean:
                    # cooldown check (avoid duplicates)
                    if sec_stamp - last_found > (PRE_SEC + POST_SEC - 0.5):
                        found_times.append(sec_stamp)
                        last_found = sec_stamp
                        print(f"[FOUND] {os.path.basename(video_path)} @ {sec_stamp:.2f}s -> '{kw}'")
    executor.shutdown(wait=True)
    cap.release()
    return found_times

# --- Extract clips (stream copy to preserve quality) ---
def extract_clips_from_timestamps(video_path, timestamps, out_dir, pre=PRE_SEC, post=POST_SEC):
    os.makedirs(out_dir, exist_ok=True)
    out_files = []

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
        ], check=True)
        vals = [l.strip().lower() for l in r.stdout.splitlines() if l.strip()]
        # order: color_space, color_transfer, color_primaries, pix_fmt
        if any("bt2020" in v or "pq" in v or "smpte2084" in v or "2100" in v or "10le" in v for v in vals):
            is_hdr = True
            print(f"[INFO] Detected HDR content in {os.path.basename(video_path)} - will normalize to SDR")
    except Exception:
        pass

    for i, sec_stamp in enumerate(timestamps, start=1):
        start = max(0.0, sec_stamp - pre)
        duration = pre + post
        out_path = os.path.join(out_dir, f"clip_{i:03d}.webm")

        # Build ffmpeg command with color normalization
        cmd = ["ffmpeg", "-nostdin", "-y", "-i", video_path]
        
        # Add seek and duration
        cmd.extend(["-ss", f"{start:.3f}", "-t", f"{duration:.3f}"])

        if is_hdr:
            # Improved HDR to SDR conversion with better color preservation
            vf_filters = (
                "zscale=t=linear:npl=250,format=gbrp,zscale=p=bt709:t=bt709:m=bt709,"
                "tonemap=tonemap=hable:desat=0:peak=100:exposure=0.8,"
                "zscale=t=bt709:m=bt709:r=tv,eq=saturation=1.2,"
                "format=yuv420p"
            )
            cmd.extend([
                "-vf", vf_filters,
                "-c:v", "libvpx-vp9",
                "-crf", "18",
                "-b:v", "0",
                "-pix_fmt", "yuv420p",
                "-color_primaries", "bt709",
                "-color_trc", "bt709",
                "-colorspace", "bt709",
                "-c:a", "copy"
            ])
        else:
            # For SDR content, ensure consistent BT.709 color metadata
            cmd.extend([
                "-vf", "format=yuv420p",
                "-c:v", "libvpx-vp9",
                "-crf", "18",
                "-b:v", "0",
                "-pix_fmt", "yuv420p",
                "-color_primaries", "bt709",
                "-color_trc", "bt709",
                "-colorspace", "bt709",
                "-c:a", "copy"
            ])
        
        cmd.append(out_path)
        
        try:
            run(cmd, check=True)
            out_files.append(out_path)
            print(f"[EXTRACT] {os.path.basename(out_path)} ({start:.1f}s->{start+duration:.1f}s)")
        except subprocess.CalledProcessError as e:
            print(f"[WARN] extract failed for {video_path} at {sec_stamp}: {e.stderr[:200]}")
    return out_files

# --- Interleave two lists (alternating) ---
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

# --- Merge 2-by-2 (for testing) preserving stream-copy when compatible ---
def concat_copy_if_compatible(clips, out_path):
    # if only 1 clip, copy
    if len(clips) == 0:
        return False
    if len(clips) == 1:
        shutil.copy2(clips[0], out_path)
        print(f"[COPIED] single -> {out_path}")
        return True

    # create concat list
    list_file = os.path.join(os.path.dirname(out_path), "concat_list.txt")
    with open(list_file, "w", encoding="utf-8") as f:
        for p in clips:
            f.write(f"file '{os.path.abspath(p)}'\n")
    cmd = ["ffmpeg", "-nostdin", "-y", "-f", "concat", "-safe", "0", "-i", list_file, "-c", "copy", out_path]
    try:
        subprocess.run(cmd, capture_output=True, check=True)
        os.remove(list_file)
        print(f"[MERGED] -> {out_path}")
        return True
    except subprocess.CalledProcessError as e:
        # fallback: re-encode lossless VP9 intermediates and concat
        print("[WARN] concat-copy failed, falling back to normalize")
        try:
            norms = []
            for p in clips:
                norm = os.path.splitext(p)[0] + "_norm.webm"
                cmd2 = ["ffmpeg", "-nostdin", "-y", "-i", p, "-c:v", "libvpx-vp9", "-lossless", "1", "-b:v", "0", "-c:a", "copy", norm]
                subprocess.run(cmd2, capture_output=True, check=True)
                norms.append(norm)
            with open(list_file, "w", encoding="utf-8") as f:
                for n in norms:
                    f.write(f"file '{os.path.abspath(n)}'\n")
            cmd3 = ["ffmpeg", "-nostdin", "-y", "-f", "concat", "-safe", "0", "-i", list_file, "-c", "copy", out_path]
            subprocess.run(cmd3, capture_output=True, check=True)
            os.remove(list_file)
            for n in norms:
                try: os.remove(n)
                except: pass
            print(f"[MERGED - normalized] -> {out_path}")
            return True
        except Exception as ee:
            print(f"[ERROR] merge fallback failed: {ee}")
            return False

# --- Mix background music + game audio for final compilation clip ---
def mix_bgm_with_game(src_webm, bgm_path, out_webm, target_game_vol=0.5, target_bgm_vol=0.5):
    """
    Creates a new WebM with audio mixed: (game * target_game_vol) + (bgm looped * target_bgm_vol).
    Keeps video copy (re-mux with vp9 copy if possible).
    We'll generate a temporary looped bgm as opus, then use filter_complex to mix.
    """
    tmp_dir = os.path.dirname(out_webm)
    os.makedirs(tmp_dir, exist_ok=True)
    duration = get_duration(src_webm) or 0.0
    tmp_bgm = os.path.join(tmp_dir, "bgm_looped.opus")
    # create looped background track in opus container (we'll use -t to trim)
    try:
        # convert and loop by using -stream_loop -1 and set -t
        cmd = [
            "ffmpeg", "-nostdin", "-y",
            "-stream_loop", "-1", "-i", bgm_path,
            "-t", f"{duration:.3f}",
            "-vn", "-c:a", "libopus", "-b:a", "128k", tmp_bgm
        ]
        subprocess.run(cmd, capture_output=True, check=True)
    except subprocess.CalledProcessError as e:
        print(f"[ERROR] failed to create looped bgm: {e.stderr[:200]}")
        return False

    # mix: take game audio from src_webm and the tmp_bgm. Use filter_complex:
    # [0:a]volume=game_vol[ga];[1:a]volume=bgm_vol[ba];[ga][ba]amix=inputs=2:dropout_transition=0,volume=2[outa]
    # Then copy video stream, encode audio to opus.
    cmd2 = [
        "ffmpeg", "-nostdin", "-y",
        "-i", src_webm, "-i", tmp_bgm,
        "-map", "0:v",  # video from src
        "-filter_complex",
        f"[0:a]volume={target_game_vol}[ga];[1:a]volume={target_bgm_vol}[ba];[ga][ba]amix=inputs=2:dropout_transition=0:normalize=0[mixout]",
        "-map", "[mixout]",
        "-c:v", "copy",  # keep video streams if possible
        "-c:a", "libopus", "-b:a", "128k",
        out_webm
    ]
    try:
        subprocess.run(cmd2, capture_output=True, check=True)
        try: os.remove(tmp_bgm)
        except: pass
        print(f"[AUDIO MIXED] -> {out_webm}")
        return True
    except subprocess.CalledProcessError as e:
        print(f"[ERROR] audio mixing failed: {e.stderr[:400]}")
        try: os.remove(tmp_bgm)
        except: pass
        return False

# --- High-level pipeline ---
def main(args):
    require_ffmpeg()
    reader = init_easyocr()

    script_dir = os.path.abspath(os.path.dirname(__file__))
    out_root = os.path.join(script_dir, args.outdir)
    tmp_root = os.path.join(script_dir, TEMP_DIRNAME)
    # folders
    a_tmp = os.path.join(tmp_root, "a")  # speedkill temp
    b_tmp = os.path.join(tmp_root, "b")  # immortal temp
    merged_tmp = os.path.join(tmp_root, "merged_pairs")
    final_tmp = os.path.join(tmp_root, "final_mixed")
    os.makedirs(out_root, exist_ok=True)
    os.makedirs(a_tmp, exist_ok=True)
    os.makedirs(b_tmp, exist_ok=True)
    os.makedirs(merged_tmp, exist_ok=True)
    os.makedirs(final_tmp, exist_ok=True)

    # detect kills (fast)
    print("[STEP] Scanning input1 for kills...")
    kills1 = detect_kills(args.speed, reader)
    print(f"[INFO] Found {len(kills1)} events in {os.path.basename(args.speed)}")

    print("[STEP] Scanning input2 for kills...")
    kills2 = detect_kills(args.immortal, reader)
    print(f"[INFO] Found {len(kills2)} events in {os.path.basename(args.immortal)}")

    if not kills1 and not kills2:
        print("[INFO] No kills found in either input. Exiting.")
        return

    # Extract clips to tmp folders (stream copy)
    clips1 = extract_clips_from_timestamps(args.speed, kills1, a_tmp, pre=args.pre, post=args.post)
    clips2 = extract_clips_from_timestamps(args.immortal, kills2, b_tmp, pre=args.pre, post=args.post)

    # Sort clips (ensures consistent ordering)
    clips1.sort()
    clips2.sort()

    # Interleave (alternating)
    alternating = interleave_lists(clips1, clips2)
    print(f"[INFO] Alternating list length: {len(alternating)}")

    # For testing: merge 2-by-2 sequentially (clip0+clip1 => merged_1, clip2+clip3 => merged_2, ...)
    merged_pairs = []
    for i in range(0, len(alternating), 2):
        pair = alternating[i:i+2]
        merged_out = os.path.join(merged_tmp, f"merged_pair_{i//2+1:03d}.webm")
        concat_copy_if_compatible(pair, merged_out)
        merged_pairs.append(merged_out)

    # --- Mix background music and keep webm output
    bgm_folder = os.path.join(script_dir, BGM_DIRNAME)
    bgm_files = []
    if os.path.isdir(bgm_folder):
        bgm_files = [os.path.join(bgm_folder, f) for f in os.listdir(bgm_folder) if os.path.isfile(os.path.join(bgm_folder, f))]
    if not bgm_files:
        print("[WARN] No background music files found in 'background_musics/'. Producing compilation without BGM.")
    final_outputs = []
    for i, merged in enumerate(merged_pairs, start=1):
        final_out = os.path.join(final_tmp, f"final_{i:03d}.webm")
        if bgm_files:
            bgm_choice = random.choice(bgm_files)
            ok = mix_bgm_with_game(merged, bgm_choice, final_out, target_game_vol=0.5, target_bgm_vol=0.5)
            if not ok:
                # fallback: just copy merged
                shutil.copy2(merged, final_out)
        else:
            shutil.copy2(merged, final_out)
        final_outputs.append(final_out)

    # Create one final compilation by concat-copying final_outputs
    compilation_out = os.path.join(out_root, "compilation_final.webm")
    concat_copy_if_compatible(final_outputs, compilation_out)

    print("\n[DONE] Final compilation:", compilation_out)

    # Cleanup temp
    try:
        shutil.rmtree(tmp_root)
        print("[CLEANUP] Temporary files removed.")
    except Exception:
        pass

    gc.collect()

# --- CLI args ---
if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Fast duo kill extractor -> alternating compilation (WebM).")
    ap.add_argument("--speed", required=True, help="Speedkill input video (webm/mp4)")
    ap.add_argument("--immortal", required=True, help="Immortal input video (webm/mp4)")
    ap.add_argument("--outdir", default=OUT_DIR_DEFAULT, help="Output folder")
    ap.add_argument("--pre", type=float, default=PRE_SEC, help="seconds before event")
    ap.add_argument("--post", type=float, default=POST_SEC, help="seconds after")
    ap.add_argument("--ocr_interval", type=float, default=OCR_INTERVAL, help="seconds between OCR samples")
    ap.add_argument("--ocr_workers", type=int, default=MAX_OCR_WORKERS, help="parallel OCR workers")
    args = ap.parse_args()

    # apply args to globals used inside
    OCR_INTERVAL = args.ocr_interval
    MAX_OCR_WORKERS = args.ocr_workers
    PRE_SEC = args.pre
    POST_SEC = args.post

    try:
        main(args)
    except KeyboardInterrupt:
        print("[INTERRUPT] User stopped.")
        sys.exit(1)
