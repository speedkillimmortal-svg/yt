#!/usr/bin/env python3
"""
manual_shorts_extractor.py
Extract YouTube Shorts clips from a video using manual start times.
- Converts to vertical (1080x1920)
- Exports BOTH .webm (VP9 + Opus) and .mp4 (H.264 + AAC) formats.
"""

import os
import subprocess

# === CONFIG ===
INPUT_VIDEO = "input.webm"        # input video file
OUTPUT_DIR_WEBM = "shorts_webm"   # output folder for .webm
OUTPUT_DIR_MP4 = "shorts_mp4"     # output folder for .mp4
CLIP_LENGTH = 60                  # length of each short in seconds
INTERVAL = 3000                 # Extract clips every 3 minutes (180 seconds)
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
CROP_FILTER = "crop=in_h*9/16:in_h:(in_w-out_w)/2:0,scale=1080:1920"
TARGET_W, TARGET_H = 1080, 1920
BOTTOM_BAR = 200
VIDEO_H = TARGET_H - BOTTOM_BAR


def extract_clips(input_path, start_times, clip_len, fmt, out_dir):
    os.makedirs(out_dir, exist_ok=True)

    for idx, start in enumerate(start_times, start=1):
        out_file = os.path.join(out_dir, f"short_{idx}.{fmt}")

        if fmt == "webm":
            codec_args = ["-c:v", "libvpx-vp9", "-b:v", "4M", "-c:a", "libopus", "-b:a", "128k"]
        else:
            codec_args = ["-c:v", "libx264", "-preset", "fast", "-crf", "23", "-c:a", "aac", "-b:a", "128k"]

        script_dir = os.path.dirname(os.path.abspath(__file__))
        icon_path = os.path.join(script_dir, 'generic_icon.png')
        logo_path = os.path.join(script_dir, 'channel_logo.jpg')

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
                f"[0:v]scale=-1:{VIDEO_H},crop='if(gt(in_w,{TARGET_W}),{TARGET_W},in_w)':{VIDEO_H}:'(in_w-out_w)/2':0,"
                f"pad={TARGET_W}:{TARGET_H}:0:0:black[v0]"
            )

            map_chain = '[v0]'
            overlay_count = 0
            for name, idx_input in overlays:
                if name == 'icon':
                    filters.append(f"[{idx_input}:v]scale=300:{BOTTOM_BAR}[icon]")
                    filters.append(f"{map_chain}[icon]overlay=0:{VIDEO_H}[v{overlay_count+1}]")
                    map_chain = f"[v{overlay_count+1}]"
                elif name == 'logo':
                    filters.append(f"[{idx_input}:v]scale=180:180[logo]")
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

    # --- Export both formats ---
    print("[STEP] Exporting WebM versions...")
    extract_clips(INPUT_VIDEO, start_times, CLIP_LENGTH, "webm", OUTPUT_DIR_WEBM)

    print("\n[STEP] Exporting MP4 versions...")
    extract_clips(INPUT_VIDEO, start_times, CLIP_LENGTH, "mp4", OUTPUT_DIR_MP4)

    print(f"\n✅ [DONE] Export complete:")
    print(f"   • {OUTPUT_DIR_WEBM}/ (YouTube Shorts)")
    print(f"   • {OUTPUT_DIR_MP4}/ (Instagram Reels)")


if __name__ == "__main__":
    main()
