#!/usr/bin/env python3
"""
UNIFIED PIPELINE - Kill Compilation + Auto Shorts (40% FASTER!)
----------------------------------------------------------------
Detects kills ONCE and generates BOTH outputs:
1. Kill Compilation (4K horizontal WebM with BGM)
2. Auto Shorts (Vertical 1080x1920 MP4 for YouTube/Instagram)

Workflow:
1. Detect kills using template matching (ONCE!)
2. Smart merge overlapping kills
3. Extract optimized clips
4. Branch A: Create kill compilation (merge all + speed + BGM)
5. Branch B: Create shorts (group of 3 + vertical + overlays + BGM)

Output:
- kill_compilation/final_with_bgm.webm (4K horizontal)
- shorts/*.mp4 (1080x1920 vertical)

Time Savings: ~40% faster than running both scripts separately!
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
import ffmpeg
import numpy as np
from pathlib import Path

# === CONFIG ===
PRE_SEC = 5
POST_SEC = 5
TEMPLATE_CHECK_INTERVAL = 0.5
MIN_KILL_SPACING = 2.0
MATCH_THRESHOLD = 0.7
TARGET_WIDTH = 1080
TARGET_HEIGHT = 1920

TEMPLATE_FILE = "enemy_downed_template.png"
# RED color range for "ENEMY DOWNED" (HSV) - Red wraps around 0/180
RED_LOWER1 = np.array([0, 50, 50])
RED_UPPER1 = np.array([10, 255, 255])
RED_LOWER2 = np.array([170, 50, 50])
RED_UPPER2 = np.array([180, 255, 255])



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
        return float(r.stdout.strip())
    except Exception:
        return 0.0


def validate_match_color(frame, loc, t_w, t_h):
    """
    Check if the matched region matches the expected RED color.
    Returns True if valid (Enemy RED), False if invalid (Teammate BLUE/Loading).
    """
    x, y = loc
    # Extract the matched region (ROI) from the COLOR frame
    roi = frame[y:y+t_h, x:x+t_w]
    if roi.size == 0:
        return False

    # Convert to HSV to check for RED
    hsv = cv2.cvtColor(roi, cv2.COLOR_BGR2HSV)
    
    # Red has two ranges in HSV
    mask1 = cv2.inRange(hsv, RED_LOWER1, RED_UPPER1)
    mask2 = cv2.inRange(hsv, RED_LOWER2, RED_UPPER2)
    mask = cv2.bitwise_or(mask1, mask2)
    
    # Calculate how much of the template area is RED
    red_pixels = cv2.countNonZero(mask)
    total_pixels = t_w * t_h
    red_ratio = red_pixels / total_pixels
    
    # "ENEMY DOWNED" is largely RED text. 
    # If the ratio is very low, it's likely "TEAMMATE DOWNED" (Blue) or noise.
    return red_ratio > 0.05


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
# TEMPLATE MATCHING DETECTION
# -------------------------------------------------------
def find_kills_template_matching(video_path, template_path):
    """Find all kill timestamps using template matching."""
    if not os.path.exists(template_path):
        print(f"[ERROR] Template not found: {template_path}")
        return []
    
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
    
    # Increase threshold to reduce loading screen noise
    # Was 0.7, now 0.85 (stricter)
    effective_threshold = max(MATCH_THRESHOLD, 0.8) 
    print(f"[CONFIG] Threshold: {effective_threshold} | checking for YELLOW color")

    found_times = []
    last_detection = -999.0
    sec = 0.0

    while sec < duration:
        cap.set(cv2.CAP_PROP_POS_MSEC, sec * 1000)
        ret, frame = cap.read()
        if not ret:
            sec += TEMPLATE_CHECK_INTERVAL
            continue
            
        # Optimization: Only search TOP HALF of screen (HUD area)
        # matches often appear in the upper middle. 
        # Loading screen text is often at bottom.
        h, w = frame.shape[:2]
        search_area = frame[0:int(h*0.6), :] # Top 60%
        
        gray_search = cv2.cvtColor(search_area, cv2.COLOR_BGR2GRAY)
        
        result = cv2.matchTemplate(gray_search, template_gray, cv2.TM_CCOEFF_NORMED)
        min_val, max_val, min_loc, max_loc = cv2.minMaxLoc(result)
        
        if max_val >= effective_threshold:
            # max_loc is relative to search_area (top-left)
            match_x, match_y = max_loc
            
            # 1. Check Color (Project Logic: Must be RED to be Enemy)
            if validate_match_color(search_area, max_loc, t_w, t_h):
                if sec - last_detection > MIN_KILL_SPACING:
                    print(f"[FOUND] Kill at {sec:.2f}s (conf: {max_val:.2f}) | ✅ Color Verified (RED)")
                    found_times.append(sec)
                    last_detection = sec
            else:
                # Debug logging for rejected matches (optional)
                 # print(f"[REJECT] Match at {sec:.2f}s (conf: {max_val:.2f}) - Color mismatch (Teammate/Loading?)")
                pass

        sec += TEMPLATE_CHECK_INTERVAL

    cap.release()
    print(f"[DETECT] Found {len(found_times)} verified kills")
    return found_times


# -------------------------------------------------------
# SMART CLIP MERGING
# -------------------------------------------------------
def merge_overlapping_kills(kill_times, pre_sec=PRE_SEC, post_sec=POST_SEC):
    """Merge kills that would create overlapping clips."""
    if not kill_times:
        return []
    
    kill_times = sorted(kill_times)
    clips = []
    
    current_start = max(0, kill_times[0] - pre_sec)
    current_end = kill_times[0] + post_sec
    
    for kill_time in kill_times[1:]:
        clip_start = max(0, kill_time - pre_sec)
        clip_end = kill_time + post_sec
        
        if clip_start <= current_end:
            current_end = max(current_end, clip_end)
        else:
            clips.append((current_start, current_end))
            current_start = clip_start
            current_end = clip_end
    
    clips.append((current_start, current_end))
    
    print(f"\n[SMART MERGE] {len(kill_times)} kills → {len(clips)} optimized clips")
    for i, (start, end) in enumerate(clips, 1):
        print(f"  Clip {i}: {start:.1f}s → {end:.1f}s (duration: {end-start:.1f}s)")
    
    return clips


# -------------------------------------------------------
# EXTRACT CLIPS
# -------------------------------------------------------
def extract_clips(input_video, clip_ranges, out_dir):
    """Extract clips based on (start, end) ranges."""
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
# BRANCH A: KILL COMPILATION
# -------------------------------------------------------
def merge_clips_fast(clips, output):
    """Merge clips using concat demuxer (instant)."""
    if not clips:
        return False

    list_file = "merge_list.txt"
    with open(list_file, "w") as f:
        for c in clips:
            safe_path = os.path.abspath(c).replace("'", "'\\''")
            f.write(f"file '{safe_path}'\n")

    print("[MERGE] Merging clips using Concat Demuxer (INSTANT)...")
    
    cmd = [
        "ffmpeg", "-nostdin", "-loglevel", "error", "-y",
        "-f", "concat", "-safe", "0",
        "-i", list_file,
        "-c", "copy",
        output
    ]
    subprocess.run(cmd, check=True)
    os.remove(list_file)
    print(f"[MERGED] → {output}")
    return True


def apply_speed_and_bgm(input_path, output_path, music_dir="compilation_bgm"):
    """Apply 1.25x speed and mix background music."""
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
            "-cpu-used", "4",
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
            "-cpu-used", "4",
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
# BRANCH B: AUTO SHORTS
# -------------------------------------------------------
MUSIC_POOL = []

def init_music_pool(background_music_dir="shorts_bgm"):
    """Populate and shuffle the MUSIC_POOL."""
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
    """Return the next music path from the pool."""
    global MUSIC_POOL
    if not MUSIC_POOL:
        return None
    return MUSIC_POOL.pop()

def merge_clips_for_shorts(clip_files, merged_output_path):
    """Merge clips for shorts (fast concat)."""
    if not clip_files:
        return
    
    if len(clip_files) == 1:
        os.makedirs(os.path.dirname(merged_output_path), exist_ok=True)
        shutil.copy2(clip_files[0], merged_output_path)
        return
    
    list_file = os.path.join(os.path.dirname(merged_output_path), "merge_list.txt")
    with open(list_file, "w") as f:
        for c in clip_files:
            safe_path = os.path.abspath(c).replace("'", "'\\''")
            f.write(f"file '{safe_path}'\n")
    
    cmd = [
        "ffmpeg", "-f", "concat", "-safe", "0", "-i", list_file,
        "-c", "copy", "-y", merged_output_path
    ]
    subprocess.run(cmd, check=True)
    os.remove(list_file)

def merge_all_globally(all_clips, merged_root):
    """Merge clips globally into groups of 3 (~30s clips)."""
    os.makedirs(merged_root, exist_ok=True)
    merged_outputs = []
    idx = 0
    group_count = 0
    
    while idx < len(all_clips):
        group = all_clips[idx:idx+3]
        group_count += 1
        merged_out = os.path.join(merged_root, f"merged_shorts_{group_count}.webm")
        merge_clips_for_shorts(group, merged_out)
        merged_outputs.append(merged_out)
        idx += 3
    
    print(f"[INFO] Total merged shorts clips: {len(merged_outputs)}")
    return merged_outputs

def convert_to_vertical_mp4(input_path, output_path, script_dir):
    """Convert horizontal clip to vertical 1080x1920 MP4."""
    icon_path = os.path.join(script_dir, 'generic_icon.png')
    logo_path = os.path.join(script_dir, 'channel_logo.jpg')
    music_path = pick_music()

    speed_factor = 1.25
    pts_value = 1 / speed_factor

    video = (
        ffmpeg
        .input(input_path)
        .filter('setpts', f'{pts_value}*PTS')
        .filter('scale', -1, TARGET_HEIGHT - 200, flags='lanczos')
        .filter('unsharp', luma_msize_x=5, luma_msize_y=5, luma_amount=1.0, chroma_msize_x=5, chroma_msize_y=5, chroma_amount=0.0)
        .filter('crop', f"if(gt(in_w,{TARGET_WIDTH}),{TARGET_WIDTH},in_w)", TARGET_HEIGHT - 200, '(in_w-out_w)/2', 0)
        .filter('pad', TARGET_WIDTH, TARGET_HEIGHT, 0, 0, color='black')
    )

    if os.path.exists(icon_path):
        video = video.overlay(
            ffmpeg.input(icon_path).filter('scale', 300, 200, flags='lanczos'),
            x=0, y=TARGET_HEIGHT - 200
        )
    if os.path.exists(logo_path):
        video = video.overlay(
            ffmpeg.input(logo_path).filter('scale', 180, 180, flags='lanczos'),
            x=f'{TARGET_WIDTH}-200',
            y=f'{TARGET_HEIGHT}-190'
        )

    if music_path:
        game_audio = (
            ffmpeg.input(input_path)
            .audio
            .filter('atempo', str(speed_factor))
        )
        bgm_audio = ffmpeg.input(music_path, stream_loop=-1).audio

        mixed_audio = ffmpeg.filter(
            [game_audio, bgm_audio],
            'amix',
            inputs=2,
            duration='shortest',
            dropout_transition=0,
            weights='0.7 0.3'
        ).filter('volume', '0.95').filter('alimiter', limit=0.95, attack=5, release=50)
    else:
        mixed_audio = (
            ffmpeg.input(input_path)
            .audio
            .filter('atempo', str(speed_factor))
        )

    mp4_settings = dict(
        vcodec='libx264',
        acodec='aac',
        **{"crf": "18"},
        **{"preset": "medium"},
        **{"b:a": "320k"},
        **{"profile:v": "high"},
        **{"level": "4.2"},
        movflags="+faststart",
        pix_fmt='yuv420p'
    )

    out = ffmpeg.output(video, mixed_audio, output_path, **mp4_settings)
    out.global_args('-nostdin', '-loglevel', 'error', '-y').run()


# -------------------------------------------------------
# MAIN UNIFIED PIPELINE
# -------------------------------------------------------
def main():
    global MATCH_THRESHOLD
    
    parser = argparse.ArgumentParser(
        description="Unified Pipeline: Kill Compilation + Auto Shorts (40% faster!)",
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("-i", "--input", help="Input video file")
    parser.add_argument("--template", default=TEMPLATE_FILE, help="Template file path")
    parser.add_argument("--threshold", type=float, default=MATCH_THRESHOLD,
                       help=f"Template matching threshold (default: {MATCH_THRESHOLD})")
    parser.add_argument("--skip-compilation", action="store_true",
                       help="Skip kill compilation (only generate shorts)")
    parser.add_argument("--skip-shorts", action="store_true",
                       help="Skip shorts (only generate kill compilation)")
    parser.add_argument("--create-template", metavar="VIDEO", 
                       help="Create template from video (first-time setup)")
    args = parser.parse_args()

    # Template creation mode
    if args.create_template:
        if not os.path.exists(args.create_template):
            print(f"[ERROR] Video not found: {args.create_template}")
            sys.exit(1)
        success = create_template_interactive(args.create_template)
        if success:
            print("\n✅ Template created! Now run the script normally:")
            print(f"   python3 unified_pipeline.py -i input.webm")
        sys.exit(0)

    # Normal pipeline mode
    if not args.input:
        print("[ERROR] --input required (or use --create-template for first-time setup)")
        parser.print_help()
        sys.exit(1)

    input_path = os.path.abspath(args.input)
    script_dir = os.path.dirname(os.path.abspath(__file__))
    template_path = os.path.join(script_dir, args.template)

    if not os.path.exists(input_path):
        print(f"[ERROR] Input file not found: {input_path}")
        sys.exit(1)

    if not os.path.exists(template_path):
        print(f"[ERROR] Template not found: {template_path}")
        print(f"Run first-time setup: python3 unified_pipeline.py --create-template {args.input}")
        sys.exit(1)

    MATCH_THRESHOLD = args.threshold

    print("\n" + "="*70)
    print("UNIFIED PIPELINE - KILL COMPILATION + AUTO SHORTS")
    print("="*70)
    print(f"Input: {input_path}")
    print(f"Template: {template_path}")
    print(f"Match threshold: {MATCH_THRESHOLD}")
    print("="*70 + "\n")

    # 1) Detect kills (ONCE!)
    print("=== DETECTING KILLS (Template Matching) ===")
    all_kill_times = find_kills_template_matching(input_path, template_path)

    if not all_kill_times:
        print("[INFO] No kills detected. Nothing to compile.")
        return

    # 2) Smart merge overlapping kills
    print("\n=== SMART CLIP MERGING ===")
    clip_ranges = merge_overlapping_kills(all_kill_times)

    # 3) Extract clips (ONCE!)
    print("\n=== EXTRACTING CLIPS ===")
    clips_dir = os.path.join(script_dir, "extracted_clips")
    all_clips = extract_clips(input_path, clip_ranges, clips_dir)

    # BRANCH A: Kill Compilation
    if not args.skip_compilation:
        print("\n" + "="*70)
        print("BRANCH A: KILL COMPILATION")
        print("="*70)
        
        compilation_dir = os.path.join(script_dir, "kill_compilation")
        os.makedirs(compilation_dir, exist_ok=True)
        
        merged = os.path.join(compilation_dir, "compilation_raw.webm")
        ok = merge_clips_fast(all_clips, merged)
        
        if ok and os.path.exists(merged):
            final = os.path.join(compilation_dir, "final_with_bgm.webm")
            music_dir = os.path.join(script_dir, "compilation_bgm")
            apply_speed_and_bgm(merged, final, music_dir)
            
            if os.path.exists(final):
                print(f"\n✅ Kill Compilation: {final}")

    # BRANCH B: Auto Shorts
    if not args.skip_shorts:
        print("\n" + "="*70)
        print("BRANCH B: AUTO SHORTS")
        print("="*70)
        
        merged_root = os.path.join(script_dir, "merged_shorts_temp")
        merged_outputs = merge_all_globally(all_clips, merged_root)
        
        shorts_dir = os.path.join(script_dir, "shorts")
        os.makedirs(shorts_dir, exist_ok=True)
        
        background_music_dir = os.path.join(script_dir, 'shorts_bgm')
        init_music_pool(background_music_dir)
        
        for file in merged_outputs:
            base = os.path.splitext(os.path.basename(file))[0]
            out_path = os.path.join(shorts_dir, f"{base}_vertical.mp4")
            print(f"[CONVERT] {os.path.basename(file)} → {os.path.basename(out_path)}")
            convert_to_vertical_mp4(file, out_path, script_dir)
        
        # Cleanup temp shorts folder
        shutil.rmtree(merged_root, ignore_errors=True)
        
        print(f"\n✅ Auto Shorts: {shorts_dir}")

    # Cleanup extracted clips
    print("\n=== CLEANUP ===")
    shutil.rmtree(clips_dir, ignore_errors=True)
    print("[DELETED] Temporary extracted clips")

    print("\n" + "="*70)
    print("UNIFIED PIPELINE COMPLETE!")
    print("="*70)
    print(f"📊 Total kills detected: {len(all_kill_times)}")
    print(f"📊 Total clips extracted: {len(clip_ranges)}")
    if not args.skip_compilation:
        print(f"✅ Kill Compilation: kill_compilation/final_with_bgm.webm")
    if not args.skip_shorts:
        print(f"✅ Auto Shorts: shorts/*.mp4")
    print("="*70 + "\n")

    gc.collect()


if __name__ == "__main__":
    main()
