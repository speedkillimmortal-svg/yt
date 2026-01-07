#!/usr/bin/env python3
"""
combined_pipeline.py
A unified workflow to:
1. Extract Shorts from a long video (Manual or Auto).
2. Apply Text Overlays to the extracted shorts.

Usage:
    python3 combined_pipeline.py
"""

import os
import json
import sys
import argparse
import subprocess
import cv2
import re

# ==========================================
#               CONFIGURATION
# ==========================================

# --- Input / Output ---
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# Path to the source video (long form)
INPUT_VIDEO = os.path.join(BASE_DIR, "input.webm")

# Directories
RAW_SHORTS_DIR = os.path.join(BASE_DIR, "processed_clips/raw")
FINAL_OUTPUT_DIR = os.path.join(BASE_DIR, "processed_clips/final")
RESOURCE_DIR = BASE_DIR

# --- Step 1: Shorts Extraction Config ---
# List of manual clips: (Start_Time, End_Time) - Seconds
# Example: [(10, 60), (120, 180)]
MANUAL_CLIPS = [
    (111, 120)
]

# Auto Mode Settings (if MANUAL_CLIPS is empty)
CLIP_LENGTH = 55
INTERVAL = 55
OVERLAP = 0

# Visual Settings for Extraction
TARGET_W, TARGET_H = 1080, 1920
BOTTOM_BAR = 200
VIDEO_H = TARGET_H - BOTTOM_BAR
POV_SHIFT_X = -300  # Shift left to frame specific areas (e.g. Kratos)


# --- Step 2: Text Overlay Config ---
# Visual Style
TEXT_COLOR = "white"
BORDER_COLOR = "black"
FONT_NAME = "Impact"

# Text content for each extracted clip (Sequential)
# The first clip gets the first string, second clip gets the second, etc.
OVERLAY_TEXTS = [
    "Test again"
]
DEFAULT_TEXT = "SUBSCRIBE FOR MORE" 

# Config file for storing the text rectangle region
CONFIG_FILE = os.path.join(BASE_DIR, "overlay_config.json")


# ==========================================
#           HELPER FUNCTIONS (COMMON)
# ==========================================

def natural_sort_key(s):
    """Sorts strings containing numbers naturally (short1, short2, short10 instead of short1, short10, short2)"""
    return [int(text) if text.isdigit() else text.lower()
            for text in re.split('([0-9]+)', s)]


# ==========================================
#        PART 1: SHORTS EXTRACTION
# ==========================================

def get_video_duration(input_path):
    cmd = [
        "ffprobe", "-v", "error",
        "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1",
        input_path
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        return float(result.stdout.strip())
    except (subprocess.CalledProcessError, ValueError):
        print(f"[ERROR] Could not determine duration for {input_path}")
        return 0

def generate_start_times(duration, interval=INTERVAL, overlap=OVERLAP):
    start_times = []
    current_time = 0
    while current_time + CLIP_LENGTH <= duration:
        start_times.append(current_time)
        current_time += interval - overlap
    return start_times

def extract_clips(input_path, clips_list, out_dir):
    """
    Extracts clips from input_path to out_dir based on clips_list [(start, duration)].
    """
    os.makedirs(out_dir, exist_ok=True)

    # Assets
    icon_path = os.path.join(RESOURCE_DIR, 'generic_icon.png')
    logo_path = os.path.join(RESOURCE_DIR, 'channel_logo.jpg')

    # Common Codec Args
    codec_args = [
        "-c:v", "libx264",
        "-crf", "15",
        "-preset", "veryslow",
        "-threads", "7",
        "-profile:v", "high",
        "-level", "4.2",
        "-c:a", "aac",
        "-b:a", "320k",
        "-movflags", "+faststart"
    ]

    CROP_FILTER = f"crop=in_h*9/16:in_h:(in_w-out_w)/2:0,scale={TARGET_W}:{TARGET_H}:flags=lanczos,unsharp=luma_msize_x=5:luma_msize_y=5:luma_amount=1.0:chroma_msize_x=5:chroma_msize_y=5:chroma_amount=0.0"

    generated_files = []

    for idx, (start, duration) in enumerate(clips_list, start=1):
        out_file = os.path.join(out_dir, f"short_{idx}.mp4")
        
        # Check overlays
        overlays = []
        if os.path.exists(icon_path):
            overlays.append(('icon', 1)) 
        if os.path.exists(logo_path):
            img_idx = 2 if os.path.exists(icon_path) else 1
            overlays.append(('logo', img_idx))

        if overlays:
            # Complex Filter Chain
            filters = []
            filters.append(
                f"[0:v]scale=-1:{VIDEO_H}:flags=lanczos,unsharp=luma_msize_x=5:luma_msize_y=5:luma_amount=1.0:chroma_msize_x=5:chroma_msize_y=5:chroma_amount=0.0,crop='if(gt(in_w,{TARGET_W}),{TARGET_W},in_w)':{VIDEO_H}:'(in_w-out_w)/2 + ({POV_SHIFT_X})':0,"
                f"pad={TARGET_W}:{TARGET_H}:0:0:black[v0]"
            )
            map_chain = '[v0]'
            
            cmd = ["ffmpeg", "-nostdin", "-y", "-ss", str(start), "-t", str(duration), "-i", input_path]
            if os.path.exists(icon_path): cmd += ["-i", icon_path]
            if os.path.exists(logo_path): cmd += ["-i", logo_path]
            
            overlay_count = 0
            for name, idx_input in overlays:
                if name == 'icon':
                    filters.append(f"[{idx_input}:v]scale=300:{BOTTOM_BAR}:flags=lanczos[icon]")
                    filters.append(f"{map_chain}[icon]overlay=0:{VIDEO_H}[v{overlay_count+1}]")
                    map_chain = f"[v{overlay_count+1}]"
                elif name == 'logo':
                    filters.append(f"[{idx_input}:v]scale=180:180:flags=lanczos[logo]")
                    logo_x = TARGET_W - 180 - 20
                    logo_y = TARGET_H - 180 - 10
                    filters.append(f"{map_chain}[logo]overlay={logo_x}:{logo_y}[v{overlay_count+1}]")
                    map_chain = f"[v{overlay_count+1}]"
                overlay_count += 1

            filter_complex = ';'.join(filters)
            cmd += ["-filter_complex", filter_complex, "-map", map_chain, "-map", "0:a?", *codec_args, out_file]

        else:
            # Simple Crop (No Overlays)
            cmd = [
                "ffmpeg", "-nostdin", "-y", "-ss", str(start), "-t", str(duration),
                "-i", input_path, "-vf", CROP_FILTER, *codec_args, out_file
            ]

        print(f"[EXTRACT] Processing {out_file} (start={start}s, duration={duration}s)...")
        subprocess.run(cmd, check=True)
        generated_files.append(out_file)

    return generated_files


# ==========================================
#        PART 2: TEXT OVERLAY
# ==========================================

def load_config():
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, 'r') as f:
                data = json.load(f)
                return data.get("rect")
        except Exception as e:
            print(f"[WARN] Could not load config: {e}")
    return None

def save_config(rect):
    try:
        with open(CONFIG_FILE, 'w') as f:
            json.dump({"rect": rect}, f)
        print(f"[INFO] Region saved to {CONFIG_FILE}")
    except Exception as e:
        print(f"[WARN] Could not save config: {e}")

def select_region(video_path):
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        print(f"Error: Could not open video {video_path}")
        return None

    # Read a few frames to ensure we have a good one
    for _ in range(10):
        ret, frame = cap.read()
        if ret:
            break
    
    if not ret:
        print("Error: Could not read any frames from video")
        return None

    print("\n" + "="*50)
    print("INSTRUCTIONS (Close window or press SPACE/ENTER to confirm):")
    print("1. A window will open showing the video frame.")
    print("2. Click and drag to draw a rectangle where the text should appear.")
    print("3. Press SPACE or ENTER to confirm the selection.")
    print("4. Press 'c' to cancel selection.")
    print("="*50 + "\n")

    roi = cv2.selectROI("Select Text Region", frame, fromCenter=False, showCrosshair=True)
    cv2.destroyAllWindows()
    cap.release()

    if roi[2] == 0 or roi[3] == 0:
        return None

    return roi

def generate_ass_file(ass_path, text, rect, vid_w=1080, vid_h=1920):
    x, y, w, h = rect
    cx = x + (w // 2)
    cy = y + (h // 2)
    
    # 40% of box height
    font_size = int(h * 0.40)
    if font_size < 20: font_size = 20

    ass_content = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {vid_w}
PlayResY: {vid_h}

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,{FONT_NAME},{font_size},&H00FFFFFF,&H000000FF,&H00000000,&H00000000,0,0,0,0,100,100,0,0,1,5,0,5,10,10,10,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    safe_text = text.replace('\n', '\\N')
    dialogue_line = f"Dialogue: 0,0:00:00.00,99:59:59.99,Default,,0,0,0,,{{\\an5\\pos({cx},{cy})}}{safe_text}"
    ass_content += dialogue_line + "\n"
    
    with open(ass_path, 'w', encoding='utf-8') as f:
        f.write(ass_content)

def apply_text_overlay(video_path, output_path, text, rect):
    x, y, w, h = rect
    print(f"[OVERLAY] Applying text to: {os.path.basename(video_path)}")
    print(f"          Text: '{text.replace(chr(10), ' ')}'")
    
    ass_filename = f"temp_{os.path.basename(video_path)}.ass"
    ass_path = os.path.abspath(ass_filename)
    
    try:
        generate_ass_file(ass_path, text, rect, TARGET_W, TARGET_H)
        
        safe_dir = os.path.dirname(ass_path).replace(":", "\\:").replace("'", "'\\''")
        filter_arg = f"subtitles='{os.path.basename(ass_path)}':fontsdir='{safe_dir}'"

        cmd = [
            "ffmpeg", "-y", "-v", "error",
            "-i", video_path,
            "-vf", filter_arg,
            "-c:a", "copy",          
            "-c:v", "libx264",       
            "-crf", "15",
            "-preset", "veryslow",
            output_path
        ]
        
        subprocess.run(cmd, check=True)
        print(f"          -> Saved to: {output_path}")

    except subprocess.CalledProcessError as e:
        print(f"[ERROR] Overlay failed for {video_path}: {e}")
    finally:
        if os.path.exists(ass_path):
            os.remove(ass_path)


# ==========================================
#               MAIN PIPELINE
# ==========================================

def main():
    # 0. Validate Inputs
    input_video_path = os.path.abspath(INPUT_VIDEO)
    if not os.path.exists(input_video_path):
        print(f"[ERROR] Input video not found at: {input_video_path}")
        print("Please check INPUT_VIDEO path in the script.")
        return

    # ------------------------------------------
    # STEP 1: EXTRACT SHORTS
    # ------------------------------------------
    print("\n" + "="*40)
    print(" STEP 1: EXTRACTING SHORTS")
    print("="*40)

    duration = get_video_duration(input_video_path)
    if duration == 0: return

    clips_to_process = []
    if MANUAL_CLIPS:
        print(f"[INFO] Using {len(MANUAL_CLIPS)} manual clips.")
        for start, end in MANUAL_CLIPS:
            if end > start:
                clips_to_process.append((start, end - start))
    else:
        print("[INFO] Auto Mode.")
        start_points = generate_start_times(duration)
        clips_to_process = [(s, CLIP_LENGTH) for s in start_points]

    extracted_files = extract_clips(input_video_path, clips_to_process, RAW_SHORTS_DIR)
    
    if not extracted_files:
        print("[ERROR] No clips extracted.")
        return

    # ------------------------------------------
    # STEP 2: APPLY TEXT OVERLAYS
    # ------------------------------------------
    print("\n" + "="*40)
    print(" STEP 2: APPLYING TEXT OVERLAYS")
    print("="*40)
    
    os.makedirs(FINAL_OUTPUT_DIR, exist_ok=True)

    # Determine Region (Run once for all videos)
    rect = load_config()
    if not rect:
        print("[INFO] Text region not configured.")
        print(f"[INFO] Opening GUI selector on first clip: {extracted_files[0]}")
        rect = select_region(extracted_files[0])
        if rect:
            save_config(rect)
        else:
            print("[WARN] No region selected. Skipping overlays.")
            return
    else:
        print(f"[INFO] Using saved text region: {rect}")

    # Process each extracted file
    for idx, vid_path in enumerate(extracted_files):
        # Determine text
        if idx < len(OVERLAY_TEXTS):
            text_content = OVERLAY_TEXTS[idx]
        else:
            text_content = DEFAULT_TEXT
        
        # Output filename
        fname = os.path.basename(vid_path)
        out_path = os.path.join(FINAL_OUTPUT_DIR, fname)
        
        apply_text_overlay(vid_path, out_path, text_content, rect)

    print("\n" + "="*40)
    print(" ✅ PIPELINE COMPLETE")
    print("="*40)
    print(f"Final videos are in: {os.path.abspath(FINAL_OUTPUT_DIR)}")

if __name__ == "__main__":
    main()
