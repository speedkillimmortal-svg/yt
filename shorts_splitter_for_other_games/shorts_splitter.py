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
INPUT_VIDEO = "input.webm"        # input video file
OUTPUT_DIR = "shorts_output"     # output folder
CLIP_LENGTH = 30            # length of each short in seconds
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

        # If overlay assets exist, build a filter_complex that scales/crops/pads and overlays icon/logo
        script_dir = os.path.dirname(os.path.abspath(__file__))
        icon_path = os.path.join(script_dir, 'generic_icon.png')
        logo_path = os.path.join(script_dir, 'channel_logo.jpg')

        # video layout constants
        TARGET_W = 1080
        TARGET_H = 1920
        BOTTOM_BAR = 200
        VIDEO_H = TARGET_H - BOTTOM_BAR

        if os.path.exists(icon_path) or os.path.exists(logo_path):
            cmd = ["ffmpeg", "-nostdin", "-y", "-ss", str(start), "-t", str(clip_len), "-i", input_path]
            # add image inputs
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

            # build filter graph: scale/crop/pad main video to vertical, then overlay images sequentially
            filters = []
            # scale -> crop -> pad
            filters.append(f"[0:v]scale=-1:{VIDEO_H},crop='if(gt(in_w,{TARGET_W}),{TARGET_W},in_w)':{VIDEO_H}:'(in_w-out_w)/2':0,pad={TARGET_W}:{TARGET_H}:0:0:black[v0]")

            map_chain = '[v0]'
            overlay_count = 0
            for name, idx_input in overlays:
                if name == 'icon':
                    # icon scaled to (300 x BOTTOM_BAR)
                    filters.append(f"[{idx_input}:v]scale=300:{BOTTOM_BAR}[icon]")
                    # overlay at bottom-left (x=0, y=VIDEO_H)
                    filters.append(f"{map_chain}[icon]overlay=0:{VIDEO_H}[v{overlay_count+1}]")
                    map_chain = f"[v{overlay_count+1}]"
                elif name == 'logo':
                    # logo scaled to 180x180 and placed bottom-right
                    filters.append(f"[{idx_input}:v]scale=180:180[logo]")
                    logo_x = TARGET_W - 180 - 20
                    logo_y = TARGET_H - 180 - 10
                    filters.append(f"{map_chain}[logo]overlay={logo_x}:{logo_y}[v{overlay_count+1}]")
                    map_chain = f"[v{overlay_count+1}]"
                overlay_count += 1

            # final mapped video label
            final_label = map_chain
            filter_complex = ';'.join(filters)

            # assemble full command with filter_complex and mappings
            cmd += ["-filter_complex", filter_complex, "-map", final_label, "-map", "0:a?", *codec_args, out_file]

        else:
            # fallback: simple crop filter
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

