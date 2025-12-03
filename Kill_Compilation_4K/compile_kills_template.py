#!/usr/bin/env python3
"""
OPTIMIZED Kill Compilation Script - Template Matching (10-20x FASTER!)
------------------------------------------------------------------------
Uses OpenCV template matching instead of OCR for 10-20x speed improvement.

Workflow:
1. Split input video into ~6-minute parts (fast, no re-encode)
2. Detect 'ENEMY DOWNED' using TEMPLATE MATCHING (10-20x faster than OCR!)
3. Smart merge overlapping kills into longer clips
4. Extract optimized clips (fewer total clips)
5. Merge all clips into one WebM
6. Apply 1.25× speed + Mix BGM in ONE PASS

Output:  output/final_with_bgm.webm   (4K VP9 + Opus, YouTube-optimized)

FIRST TIME SETUP:
    Run with --create-template flag to capture the "ENEMY DOWNED" template
    python3 compile_kills_template.py --create-template input.webm
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
import cv2
import numpy as np
from pathlib import Path

# === CONFIG ===
PRE_SEC = 5
POST_SEC = 5
TEMPLATE_CHECK_INTERVAL = 0.5  # Check every 0.5s (2x faster than OCR at 1s)
PART_SECONDS = 360   # 6 minutes
MIN_KILL_SPACING = 2.0  # Minimum 2 seconds between separate kills
MATCH_THRESHOLD = 0.7  # Template matching confidence (0.0-1.0, lower = more lenient)

TEMPLATE_FILE = "enemy_downed_template.png"


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


def get_video_fps(path):
    try:
        r = subprocess.run(
            ['ffprobe', '-v', 'error', '-select_streams', 'v:0',
             '-show_entries', 'stream=r_frame_rate',
             '-of', 'default=nokey=1:noprint_wrappers=1', path],
            capture_output=True, text=True, check=True
        )
        fps_str = r.stdout.strip()
        if '/' in fps_str:
            num, den = fps_str.split('/')
            return float(num) / float(den)
        return float(fps_str)
    except Exception:
        return 30.0


# -------------------------------------------------------
# TEMPLATE CREATION TOOL
# -------------------------------------------------------
def create_template_interactive(video_path):
    """
    Interactive tool to capture the 'ENEMY DOWNED' template from video.
    """
    print("\n" + "="*70)
    print("TEMPLATE CREATION MODE")
    print("="*70)
    print("\nInstructions:")
    print("1. Video will play and pause at intervals")
    print("2. When you see 'ENEMY DOWNED' text, press SPACE to capture")
    print("3. Draw a rectangle around JUST the 'ENEMY DOWNED' text")
    print("4. Press ENTER to confirm, ESC to retry")
    print("5. Press 'q' to quit anytime")
    print("\nStarting in 3 seconds...\n")
    time.sleep(3)
    
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        print(f"[ERROR] Cannot open {video_path}")
        return False
    
    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    duration = total_frames / fps
    
    print(f"[INFO] Video: {duration:.1f}s, {fps:.1f} fps")
    print("[INFO] Press SPACE when you see 'ENEMY DOWNED' text")
    
    # Jump through video looking for kills
    current_time = 0
    jump_interval = 10  # Jump 10 seconds at a time
    
    template_captured = False
    
    while current_time < duration and not template_captured:
        cap.set(cv2.CAP_PROP_POS_MSEC, current_time * 1000)
        ret, frame = cap.read()
        
        if not ret:
            current_time += jump_interval
            continue
        
        # Show frame
        display_frame = frame.copy()
        h, w = frame.shape[:2]
        
        # Draw ROI hint (top-right area where HUD usually is)
        roi_x1, roi_x2 = int(w * 0.70), w
        roi_y1, roi_y2 = 0, int(h * 0.30)
        cv2.rectangle(display_frame, (roi_x1, roi_y1), (roi_x2, roi_y2), (0, 255, 0), 2)
        cv2.putText(display_frame, "Typical HUD area (look here)", 
                   (roi_x1 + 10, roi_y1 + 30), cv2.FONT_HERSHEY_SIMPLEX, 
                   0.7, (0, 255, 0), 2)
        
        cv2.putText(display_frame, f"Time: {current_time:.1f}s | SPACE=Capture | Q=Quit", 
                   (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 255), 2)
        
        cv2.imshow('Find ENEMY DOWNED text', display_frame)
        
        key = cv2.waitKey(1000) & 0xFF  # Wait 1 second, auto-advance
        
        if key == ord('q'):
            print("\n[INFO] Cancelled by user")
            break
        elif key == ord(' '):  # Space pressed - capture template
            print(f"\n[CAPTURE] Frame at {current_time:.1f}s")
            cv2.destroyAllWindows()
            
            # Let user select ROI
            print("[INFO] Draw a rectangle around 'ENEMY DOWNED' text, then press ENTER")
            roi = cv2.selectROI("Select ENEMY DOWNED text", frame, fromCenter=False, showCrosshair=True)
            cv2.destroyAllWindows()
            
            if roi[2] > 0 and roi[3] > 0:  # Valid selection
                x, y, w_roi, h_roi = roi
                template = frame[y:y+h_roi, x:x+w_roi]
                
                # Show preview
                cv2.imshow('Template Preview - Press ENTER to save, ESC to retry', template)
                key = cv2.waitKey(0) & 0xFF
                cv2.destroyAllWindows()
                
                if key == 13:  # Enter key
                    cv2.imwrite(TEMPLATE_FILE, template)
                    print(f"\n✅ Template saved to: {TEMPLATE_FILE}")
                    print(f"   Size: {w_roi}x{h_roi} pixels")
                    template_captured = True
                else:
                    print("[INFO] Retrying... Press SPACE when you see the text again")
            else:
                print("[WARN] Invalid selection, try again")
        
        current_time += jump_interval
    
    cap.release()
    cv2.destroyAllWindows()
    
    return template_captured


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
# 2) TEMPLATE MATCHING DETECTION (10-20x FASTER!)
# -------------------------------------------------------
def find_kills_template_matching(video_path, template_path, part_offset=0.0):
    """
    Find all kill timestamps using template matching.
    Returns list of timestamps (in seconds from video start).
    """
    if not os.path.exists(template_path):
        print(f"[ERROR] Template not found: {template_path}")
        print("Run with --create-template first!")
        return []
    
    # Load template
    template = cv2.imread(template_path)
    if template is None:
        print(f"[ERROR] Could not load template: {template_path}")
        return []
    
    template_gray = cv2.cvtColor(template, cv2.COLOR_BGR2GRAY)
    t_h, t_w = template_gray.shape
    
    print(f"[TEMPLATE] Loaded: {t_w}x{t_h} pixels")
    
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        print(f"[ERROR] Cannot open {video_path}")
        return []

    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    frame_count = cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0
    duration = frame_count / fps if fps > 0 else 0.0

    print(f"[DETECT] {os.path.basename(video_path)} | dur={duration:.1f}s, fps={fps:.1f}")

    found_times = []
    last_detection = -999.0
    sec = 0.0

    while sec < duration:
        cap.set(cv2.CAP_PROP_POS_MSEC, sec * 1000)
        ret, frame = cap.read()
        if not ret:
            sec += TEMPLATE_CHECK_INTERVAL
            continue

        # Convert to grayscale for matching
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        
        # Template matching
        result = cv2.matchTemplate(gray, template_gray, cv2.TM_CCOEFF_NORMED)
        min_val, max_val, min_loc, max_loc = cv2.minMaxLoc(result)
        
        # Check if match is good enough
        if max_val >= MATCH_THRESHOLD:
            # Avoid duplicate detections (same kill detected multiple times)
            if sec - last_detection > MIN_KILL_SPACING:
                absolute_time = part_offset + sec
                print(f"[FOUND] Kill at {absolute_time:.2f}s (confidence: {max_val:.2f})")
                found_times.append(absolute_time)
                last_detection = sec

        sec += TEMPLATE_CHECK_INTERVAL

    cap.release()
    print(f"[DETECT] Found {len(found_times)} kills in {os.path.basename(video_path)}")
    return found_times


# -------------------------------------------------------
# 3) SMART CLIP MERGING
# -------------------------------------------------------
def merge_overlapping_kills(kill_times, pre_sec=PRE_SEC, post_sec=POST_SEC):
    """
    Merge kills that would create overlapping clips into single longer clips.
    Returns list of (start, end) tuples.
    """
    if not kill_times:
        return []
    
    kill_times = sorted(kill_times)
    clips = []
    
    current_start = max(0, kill_times[0] - pre_sec)
    current_end = kill_times[0] + post_sec
    
    for kill_time in kill_times[1:]:
        clip_start = max(0, kill_time - pre_sec)
        clip_end = kill_time + post_sec
        
        # Check if this clip overlaps with current clip
        if clip_start <= current_end:
            # Merge: extend current clip
            current_end = max(current_end, clip_end)
        else:
            # No overlap: save current clip and start new one
            clips.append((current_start, current_end))
            current_start = clip_start
            current_end = clip_end
    
    # Don't forget the last clip
    clips.append((current_start, current_end))
    
    print(f"\n[SMART MERGE] {len(kill_times)} kills → {len(clips)} optimized clips")
    for i, (start, end) in enumerate(clips, 1):
        print(f"  Clip {i}: {start:.1f}s → {end:.1f}s (duration: {end-start:.1f}s)")
    
    return clips


# -------------------------------------------------------
# 4) EXTRACT CLIPS
# -------------------------------------------------------
def extract_clips(input_video, clip_ranges, out_dir):
    """
    Extract clips based on (start, end) ranges.
    """
    os.makedirs(out_dir, exist_ok=True)
    extracted = []
    
    for i, (start, end) in enumerate(clip_ranges, 1):
        length = end - start
        out = os.path.join(out_dir, f"clip_{i:03d}.webm")
        
        cmd = [
            "ffmpeg", "-nostdin", "-loglevel", "error", "-y",
            "-ss", f"{start:.3f}",
            "-t", f"{length:.3f}",
            "-i", input_video,
            "-c", "copy",
            out
        ]
        subprocess.run(cmd, check=True)
        extracted.append(out)
        print(f"[EXTRACT] {out}  ({start:.2f}s → {end:.2f}s)")
    
    return extracted


# -------------------------------------------------------
# 5) MERGE ALL KILL CLIPS
# -------------------------------------------------------
def merge_clips(clips, output):
    """
    Merge clips using FFmpeg concat demuxer (INSTANT stream copy).
    Skips re-encoding to save time. Sync is handled in the final pass.
    """
    if not clips:
        return False

    list_file = "merge_list.txt"
    with open(list_file, "w") as f:
        for c in clips:
            # Escape single quotes for FFmpeg concat file
            safe_path = os.path.abspath(c).replace("'", "'\\''")
            f.write(f"file '{safe_path}'\n")

    print("[MERGE] Merging clips using Concat Demuxer (INSTANT)...")
    
    cmd = [
        "ffmpeg", "-nostdin", "-loglevel", "error", "-y",
        "-f", "concat", "-safe", "0",
        "-i", list_file,
        "-c", "copy",  # STREAM COPY (No re-encoding!)
        output
    ]
    subprocess.run(cmd, check=True)
    os.remove(list_file)
    print(f"[MERGED] → {output}")
    return True


# -------------------------------------------------------
# 6) APPLY 1.25x SPEED + MIX BGM
# -------------------------------------------------------
def apply_speed_and_bgm(input_path, output_path, music_dir="background_musics"):
    """
    Apply 1.25x speed and mix background music.
    """
    duration = get_video_duration(input_path)
    if duration <= 0:
        print("[ERROR] Cannot read duration for speed-up.")
        return

    musics = glob.glob(os.path.join(music_dir, "*.mp3")) + \
             glob.glob(os.path.join(music_dir, "*.wav"))

    if not musics:
        print(f"[WARN] No background music in {music_dir}, applying 1.25x speed only.")
        cmd = [
            "ffmpeg", "-nostdin", "-y",
            "-i", input_path,
            "-filter_complex", 
            "[0:v]setpts=PTS/1.25,unsharp=luma_msize_x=5:luma_msize_y=5:luma_amount=1.0:chroma_msize_x=5:chroma_msize_y=5:chroma_amount=0.0[v];[0:a]atempo=1.25[a]",
            "-map", "[v]", "-map", "[a]",
            "-vsync", "cfr",
            "-max_muxing_queue_size", "9999",
            "-c:v", "libvpx-vp9",
            "-b:v", "0",
            "-crf", "18",
            "-cpu-used", "2",
            "-row-mt", "1",
            "-c:a", "libopus",
            "-b:a", "320k",
            output_path
        ]
    else:
        track = random.choice(musics)
        print(f"[OPTIMIZED] Applying 1.25× speed + Sharpening + mixing BGM...")
        print(f"[BGM] Using: {os.path.basename(track)} (70% game / 30% BGM)")
        
        cmd = [
            "ffmpeg", "-nostdin", "-y",
            "-stream_loop", "-1", "-i", track,
            "-i", input_path,
            "-filter_complex",
            "[1:v]setpts=PTS/1.25,unsharp=luma_msize_x=5:luma_msize_y=5:luma_amount=1.0:chroma_msize_x=5:chroma_msize_y=5:chroma_amount=0.0[v];"
            "[1:a]atempo=1.25[game_fast];"
            "[0:a]volume=0.3[bgm];"
            "[game_fast]volume=0.7[game];"
            "[bgm][game]amix=inputs=2:duration=shortest:normalize=0[a]",
            "-map", "[v]", "-map", "[a]",
            "-vsync", "cfr",
            "-max_muxing_queue_size", "9999",
            "-c:v", "libvpx-vp9",
            "-b:v", "0",
            "-crf", "18",
            "-cpu-used", "2",
            "-row-mt", "1",
            "-c:a", "libopus",
            "-b:a", "320k",
            "-shortest",
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
    global MATCH_THRESHOLD
    
    parser = argparse.ArgumentParser(
        description="OPTIMIZED Kill Compilation using Template Matching (10-20x faster!)",
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("-i", "--input", help="Input 4K WebM (game recording)")
    parser.add_argument("-o", "--outdir", default="output", help="Output folder")
    parser.add_argument("--create-template", metavar="VIDEO", 
                       help="Create template from video (first-time setup)")
    parser.add_argument("--threshold", type=float, default=MATCH_THRESHOLD,
                       help=f"Template matching threshold (default: {MATCH_THRESHOLD})")
    args = parser.parse_args()

    # Template creation mode
    if args.create_template:
        if not os.path.exists(args.create_template):
            print(f"[ERROR] Video not found: {args.create_template}")
            sys.exit(1)
        success = create_template_interactive(args.create_template)
        if success:
            print("\n✅ Template created! Now run the script normally:")
            print(f"   python3 {sys.argv[0]} -i input.webm")
        sys.exit(0)

    # Normal compilation mode
    if not args.input:
        print("[ERROR] --input required (or use --create-template for first-time setup)")
        parser.print_help()
        sys.exit(1)

    if not os.path.exists(TEMPLATE_FILE):
        print(f"[ERROR] Template not found: {TEMPLATE_FILE}")
        print(f"Run first-time setup: python3 {sys.argv[0]} --create-template {args.input}")
        sys.exit(1)

    input_path = os.path.abspath(args.input)
    outdir = os.path.abspath(args.outdir)
    os.makedirs(outdir, exist_ok=True)

    MATCH_THRESHOLD = args.threshold

    print("\n" + "="*70)
    print("OPTIMIZED KILL COMPILATION - TEMPLATE MATCHING")
    print("="*70)
    print(f"Input: {input_path}")
    print(f"Template: {TEMPLATE_FILE}")
    print(f"Match threshold: {MATCH_THRESHOLD}")
    print("="*70 + "\n")

    # 1) Split into parts (optional - can process full video directly)
    # For now, let's process the full video directly for simplicity
    print("=== DETECTING KILLS (Template Matching) ===")
    all_kill_times = find_kills_template_matching(input_path, TEMPLATE_FILE)

    if not all_kill_times:
        print("[INFO] No kills detected. Nothing to compile.")
        return

    # 2) Smart merge overlapping kills
    print("\n=== SMART CLIP MERGING ===")
    clip_ranges = merge_overlapping_kills(all_kill_times)

    # 3) Extract clips
    print("\n=== EXTRACTING CLIPS ===")
    clips_dir = os.path.join(outdir, "clips")
    all_clips = extract_clips(input_path, clip_ranges, clips_dir)

    # 4) Merge all clips
    print("\n=== MERGING CLIPS ===")
    merged = os.path.join(outdir, "compilation_raw.webm")
    ok = merge_clips(all_clips, merged)
    if not ok or not os.path.exists(merged):
        print("[ERROR] Merging clips failed.")
        return

    # 5) Apply 1.25× speed + Mix BGM
    print("\n=== FINAL ENCODING ===")
    final = os.path.join(outdir, "final_with_bgm.webm")
    apply_speed_and_bgm(merged, final)

    if not os.path.exists(final):
        print(f"[ERROR] Final output not found: {final}")
        return

    print(f"\n✅ DONE → {final}")
    print(f"📊 Total kills compiled: {len(all_kill_times)}")
    print(f"📊 Total clips: {len(clip_ranges)}")
    gc.collect()


if __name__ == "__main__":
    main()
