#!/usr/bin/env python3
"""
OPTIMIZED Auto Shorts Pipeline - Template Matching (10-20x FASTER!)
--------------------------------------------------------------------
Uses OpenCV template matching instead of OCR for 10-20x speed improvement.

Workflow:
1. Detect 'ENEMY DOWNED' using TEMPLATE MATCHING (10-20x faster than OCR!)
2. Smart merge overlapping kills into longer clips
3. Extract optimized clips
4. Merge clips globally into groups of 3 (~30s each)
5. Convert to vertical 1080x1920 MP4 with overlays + BGM

Output: shorts/ folder with YouTube Shorts & Instagram Reels ready MP4s

FIRST TIME SETUP:
    Use the template from Kill_Compilation_4K/enemy_downed_template.png
    OR create a new one with the template creation tool
"""

import os
import sys
import gc
import shutil
import cv2
import ffmpeg
import subprocess
import random
import numpy as np
from pathlib import Path

# === USER CONFIGURATION ===
PRE_SEC = 5
POST_SEC = 5
TEMPLATE_CHECK_INTERVAL = 0.5  # Check every 0.5s (2x faster than OCR at 1s)
MIN_KILL_SPACING = 2.0  # Minimum 2 seconds between separate kills
MATCH_THRESHOLD = 0.7  # Template matching confidence (0.0-1.0)
TARGET_WIDTH = 1080
TARGET_HEIGHT = 1920

# Template file (use the one from Kill Compilation or create new)
TEMPLATE_FILE = "../Kill_Compilation_4K/enemy_downed_template.png"

# === Utility Functions ===
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


# -------------------------------------------------------
# TEMPLATE MATCHING DETECTION (10-20x FASTER!)
# -------------------------------------------------------
def find_kills_template_matching(video_path, template_path):
    """
    Find all kill timestamps using template matching.
    Returns list of timestamps (in seconds).
    """
    if not os.path.exists(template_path):
        print(f"[ERROR] Template not found: {template_path}")
        print("Copy from Kill_Compilation_4K/enemy_downed_template.png")
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
            # Avoid duplicate detections
            if sec - last_detection > MIN_KILL_SPACING:
                print(f"[FOUND] Kill at {sec:.2f}s (confidence: {max_val:.2f})")
                found_times.append(sec)
                last_detection = sec

        sec += TEMPLATE_CHECK_INTERVAL

    cap.release()
    print(f"[DETECT] Found {len(found_times)} kills in {os.path.basename(video_path)}")
    return found_times


# -------------------------------------------------------
# SMART CLIP MERGING
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
# EXTRACT CLIPS
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
# MERGE CLIPS GLOBALLY (FAST - NO RE-ENCODING)
# -------------------------------------------------------
def merge_clips_fast(clip_files, merged_output_path):
    """
    Merge clips using FFmpeg concat demuxer (INSTANT stream copy).
    """
    if not clip_files:
        print(f"[SKIP] No clips to merge → {merged_output_path}")
        return

    # If only one clip, copy it
    if len(clip_files) == 1:
        os.makedirs(os.path.dirname(merged_output_path), exist_ok=True)
        shutil.copy2(clip_files[0], merged_output_path)
        print(f"[COPIED] single clip → {merged_output_path}")
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
    print(f"[MERGED] {merged_output_path}")


def merge_all_globally(all_clips, merged_root):
    """
    Merge clips globally into groups of 3 (~30s clips).
    """
    os.makedirs(merged_root, exist_ok=True)
    merged_outputs = []
    idx = 0
    group_count = 0
    
    while idx < len(all_clips):
        group = all_clips[idx:idx+3]
        group_count += 1
        merged_out = os.path.join(merged_root, f"merged_shorts_{group_count}.webm")
        merge_clips_fast(group, merged_out)
        merged_outputs.append(merged_out)
        idx += 3
    
    print(f"[INFO] Total merged global clips: {len(merged_outputs)}")
    return merged_outputs


# -------------------------------------------------------
# SHORTS CONVERSION
# -------------------------------------------------------
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
    """Return the next music path from the pool (non-repeating)."""
    global MUSIC_POOL
    if not MUSIC_POOL:
        return None
    return MUSIC_POOL.pop()

def convert_to_vertical_mp4(input_path, output_path, script_dir):
    """Convert horizontal clip to vertical 1080x1920 MP4 with overlays."""
    icon_path = os.path.join(script_dir, 'generic_icon.png')
    logo_path = os.path.join(script_dir, 'channel_logo.jpg')
    music_path = pick_music()

    # Speed factor (1.25x → 0.8 PTS)
    speed_factor = 1.25
    pts_value = 1 / speed_factor

    # Speed up video with high-quality scaling
    video = (
        ffmpeg
        .input(input_path)
        .filter('setpts', f'{pts_value}*PTS')
        .filter('scale', -1, TARGET_HEIGHT - 200, flags='lanczos')
        .filter('unsharp', luma_msize_x=5, luma_msize_y=5, luma_amount=1.0, chroma_msize_x=5, chroma_msize_y=5, chroma_amount=0.0)
        .filter('crop', f"if(gt(in_w,{TARGET_WIDTH}),{TARGET_WIDTH},in_w)", TARGET_HEIGHT - 200, '(in_w-out_w)/2', 0)
        .filter('pad', TARGET_WIDTH, TARGET_HEIGHT, 0, 0, color='black')
    )

    # Overlay channel logo and icon
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

    # Audio processing
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

    # High-quality H.264 encoding
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
# MAIN PIPELINE
# -------------------------------------------------------
def main_pipeline():
    script_dir = os.path.dirname(os.path.abspath(__file__))
    video_path = os.path.join(script_dir, "input.webm")
    
    if not os.path.exists(video_path):
        print("[ERROR] input.webm not found.")
        sys.exit(1)

    # Check template
    template_path = os.path.join(script_dir, TEMPLATE_FILE)
    if not os.path.exists(template_path):
        print(f"[ERROR] Template not found: {template_path}")
        print("Copy enemy_downed_template.png from Kill_Compilation_4K folder")
        sys.exit(1)

    print("\n" + "="*70)
    print("OPTIMIZED AUTO SHORTS PIPELINE - TEMPLATE MATCHING")
    print("="*70)
    print(f"Input: {video_path}")
    print(f"Template: {template_path}")
    print("="*70 + "\n")

    # 1) Detect kills using template matching
    print("=== DETECTING KILLS (Template Matching) ===")
    all_kill_times = find_kills_template_matching(video_path, template_path)

    if not all_kill_times:
        print("[INFO] No ENEMY DOWNED events found.")
        return

    # 2) Smart merge overlapping kills
    print("\n=== SMART CLIP MERGING ===")
    clip_ranges = merge_overlapping_kills(all_kill_times)

    # 3) Extract clips
    print("\n=== EXTRACTING CLIPS ===")
    clips_dir = os.path.join(script_dir, "Downed_clips")
    all_clips = extract_clips(video_path, clip_ranges, clips_dir)

    # 4) Merge clips globally into groups of 3
    print("\n=== MERGING CLIPS GLOBALLY ===")
    merged_root = os.path.join(script_dir, "Merged_All_Parts")
    merged_outputs = merge_all_globally(all_clips, merged_root)

    # 5) Convert to vertical shorts
    print("\n=== CONVERTING TO VERTICAL SHORTS ===")
    shorts_dir = os.path.join(script_dir, "shorts")
    os.makedirs(shorts_dir, exist_ok=True)

    # Initialize music pool
    background_music_dir = os.path.join(script_dir, 'background_musics')
    init_music_pool(background_music_dir)

    for file in merged_outputs:
        base = os.path.splitext(os.path.basename(file))[0]
        out_path = os.path.join(shorts_dir, f"{base}_vertical4k.mp4")
        print(f"[CONVERT] {os.path.basename(file)} → {os.path.basename(out_path)}")
        convert_to_vertical_mp4(file, out_path, script_dir)

    # Cleanup temporary files/folders
    print("\n=== CLEANUP ===")
    for folder in ["Downed_clips", "Merged_All_Parts"]:
        folder_path = os.path.join(script_dir, folder)
        if os.path.exists(folder_path):
            shutil.rmtree(folder_path, ignore_errors=True)
            print(f"[DELETED] {folder}")

    gc.collect()
    print("\n✅ [DONE] All outputs saved in:")
    print(f"   - Shorts (YouTube & Instagram): {shorts_dir}")
    print(f"📊 Total kills detected: {len(all_kill_times)}")
    print(f"📊 Total shorts created: {len(merged_outputs)}")

if __name__ == "__main__":
    try:
        main_pipeline()
        sys.exit(0)
    except Exception as e:
        print(f"[FATAL ERROR] {e}")
        import traceback
        traceback.print_exc()
        gc.collect()
        sys.exit(1)
