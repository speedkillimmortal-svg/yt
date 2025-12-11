#!/usr/bin/env python3
"""
manual_shorts_extractor.py
Extract YouTube Shorts clips from a video using manual start times.
- Converts to vertical (1080x1920)
- Exports high-quality .mp4 (H.264 + AAC) for YouTube Shorts & Instagram Reels.
"""

import os
import subprocess

# === CONFIG ===
INPUT_VIDEO = "input.webm"        # input video file
OUTPUT_DIR = "shorts"             # output folder for .mp4 shorts
CLIP_LENGTH = 45                  # length of each short in seconds
INTERVAL = 45                     # Extract clips continuously (no gaps)
OVERLAP = 0                       # No overlap between clips

# --- helper functions ---
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
        print("[ERROR] Could not determine video duration")
        return 0


def generate_start_times(duration, interval=INTERVAL, overlap=OVERLAP):
    """Generate clip start times at regular intervals"""
    start_times = []
    current_time = 0
    while current_time + CLIP_LENGTH <= duration:
        start_times.append(current_time)
        current_time += interval - overlap
    return start_times


# --- constants ---
# --- constants ---
CROP_FILTER = "crop=in_h*9/16:in_h:(in_w-out_w)/2:0,scale=1080:1920:flags=lanczos,unsharp=luma_msize_x=5:luma_msize_y=5:luma_amount=1.0:chroma_msize_x=5:chroma_msize_y=5:chroma_amount=0.0"

TARGET_W, TARGET_H = 1080, 1920
BOTTOM_BAR = 200
VIDEO_H = TARGET_H - BOTTOM_BAR


def extract_clips(input_path, start_times, clip_len, out_dir):
    os.makedirs(out_dir, exist_ok=True)

    # Software H.264 Encoder for MAXIMUM Quality (Reverted by User Request)
    # CPU Usage will be high (~95%) but quality is mathematically superior.
    codec_args = [
        "-c:v", "libx264",
        "-crf", "18",             # Near-lossless quality
        "-preset", "medium",      # Good balance of speed/compression
        "-threads", "7",          # Limit threads to prevent system freeze
        "-profile:v", "high",
        "-level", "4.2",
        "-c:a", "aac",
        "-b:a", "320k",
        "-movflags", "+faststart"
    ]

    script_dir = os.path.dirname(os.path.abspath(__file__))
    icon_path = os.path.join(script_dir, 'generic_icon.png')
    logo_path = os.path.join(script_dir, 'channel_logo.jpg')

    for idx, start in enumerate(start_times, start=1):
        out_file = os.path.join(out_dir, f"short_{idx}.mp4")

        if os.path.exists(icon_path) or os.path.exists(logo_path):
            cmd = ["ffmpeg", "-nostdin", "-y", "-ss", str(start), "-t", str(clip_len), "-i", input_path]
            img_idx = 1
            overlays = []
            if os.path.exists(icon_path):
                cmd += ["-i", icon_path]
                overlays.append(('icon', img_idx))
                img_idx += 1
            if os.path.exists(logo_path):
                cmd += ["-i", logo_path]
                overlays.append(('logo', img_idx))
                img_idx += 1

            filters = []
            filters.append(
                f"[0:v]scale=-1:{VIDEO_H}:flags=lanczos,unsharp=luma_msize_x=5:luma_msize_y=5:luma_amount=1.0:chroma_msize_x=5:chroma_msize_y=5:chroma_amount=0.0,crop='if(gt(in_w,{TARGET_W}),{TARGET_W},in_w)':{VIDEO_H}:'(in_w-out_w)/2':0,"
                f"pad={TARGET_W}:{TARGET_H}:0:0:black[v0]"
            )

            map_chain = '[v0]'
            overlay_count = 0
            for name, idx_input in overlays:
                if name == 'icon':
                    # Use Lanczos scaling for sharp icon
                    filters.append(f"[{idx_input}:v]scale=300:{BOTTOM_BAR}:flags=lanczos[icon]")
                    filters.append(f"{map_chain}[icon]overlay=0:{VIDEO_H}[v{overlay_count+1}]")
                    map_chain = f"[v{overlay_count+1}]"
                elif name == 'logo':
                    # Use Lanczos scaling for sharp logo
                    filters.append(f"[{idx_input}:v]scale=180:180:flags=lanczos[logo]")
                    logo_x = TARGET_W - 180 - 20
                    logo_y = TARGET_H - 180 - 10
                    filters.append(f"{map_chain}[logo]overlay={logo_x}:{logo_y}[v{overlay_count+1}]")
                    map_chain = f"[v{overlay_count+1}]"
                overlay_count += 1

            final_label = map_chain
            filter_complex = ';'.join(filters)

            cmd += ["-filter_complex", filter_complex, "-map", final_label, "-map", "0:a?", *codec_args, out_file]

        else:
            cmd = [
                "ffmpeg", "-nostdin", "-y", "-ss", str(start), "-t", str(clip_len),
                "-i", input_path, "-vf", CROP_FILTER, *codec_args, out_file
            ]

        print(f"[EXPORT] {out_file} (start={start}s → {start+clip_len}s)")
        subprocess.run(cmd, check=True)


def main():
    if not os.path.exists(INPUT_VIDEO):
        print(f"[ERROR] Input video {INPUT_VIDEO} not found.")
        return

    duration = get_video_duration(INPUT_VIDEO)
    if duration == 0:
        return

    start_times = generate_start_times(duration)
    print(f"\n[INFO] Video duration: {duration:.1f}s")
    print(f"[INFO] Extracting {len(start_times)} clips at {INTERVAL}s intervals\n")

    # --- Export High Quality MP4 Shorts ---
    print("[STEP] Generating High Quality MP4 Shorts (YouTube & Instagram)...")
    extract_clips(INPUT_VIDEO, start_times, CLIP_LENGTH, OUTPUT_DIR)

    print(f"\n✅ [DONE] Export complete:")
    print(f"   • {OUTPUT_DIR}/ (YouTube Shorts & Instagram Reels - H.264)")


if __name__ == "__main__":
    main()
