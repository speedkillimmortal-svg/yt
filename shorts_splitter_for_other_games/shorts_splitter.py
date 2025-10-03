#!/usr/bin/env python3
"""
manual_shorts_extractor.py
Extract YouTube Shorts clips from a video using manual start times.
- Converts to vertical (1080x1920)
- Saves in .webm (VP9 + Opus) for high quality
"""

import os
import subprocess

# === CONFIG ===
INPUT_VIDEO = "input.mp4"        # input video file
OUTPUT_DIR = "shorts_output"     # output folder
CLIP_LENGTH = 45                 # length of each short in seconds
OUTPUT_FORMAT = "mp4"           # "webm" or "mp4"

# Start times in seconds (you edit this list manually)
START_TIMES = [
    30,     # clip from 00:00:30 → 00:01:15
    120,    # clip from 00:02:00 → 00:02:45
    250,    # clip from 00:04:10 → 00:04:55
]

# Vertical crop for Shorts/Reels (16:9 → 9:16)
CROP_FILTER = "crop=in_h*9/16:in_h:(in_w-out_w)/2:0,scale=1080:1920"


def extract_clips(input_path, out_dir, start_times, clip_len, fmt):
    os.makedirs(out_dir, exist_ok=True)

    for idx, start in enumerate(start_times, start=1):
        out_file = os.path.join(out_dir, f"short_{idx}.{fmt}")

        if fmt == "webm":
            codec_args = ["-c:v", "libvpx-vp9", "-b:v", "4M",
                          "-c:a", "libopus", "-b:a", "128k"]
        else:  # mp4
            codec_args = ["-c:v", "libx264", "-preset", "fast", "-crf", "23",
                          "-c:a", "aac", "-b:a", "128k"]

        cmd = [
            "ffmpeg", "-nostdin", "-y",
            "-ss", str(start), "-t", str(clip_len),
            "-i", input_path,
            "-vf", CROP_FILTER,
            *codec_args,
            out_file
        ]

        print(f"[EXPORT] {out_file} (start={start}s → {start+clip_len}s)")
        subprocess.run(cmd, check=True)


def main():
    if not os.path.exists(INPUT_VIDEO):
        print(f"[ERROR] Input video {INPUT_VIDEO} not found.")
        return

    extract_clips(INPUT_VIDEO, OUTPUT_DIR, START_TIMES, CLIP_LENGTH, OUTPUT_FORMAT)
    print("[DONE] All selected clips exported.")


if __name__ == "__main__":
    main()
