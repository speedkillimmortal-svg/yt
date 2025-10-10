import sys
import os
import subprocess

"""
Optimized Clip Extractor for input.webm
---------------------------------------
Usage:
    python extract_clip.py start_time end_time output_name.webm

Example:
    python extract_clip.py 00:01:23 00:01:45 clip1.webm

Notes:
- Assumes 'input.webm' is in the same directory as this script.
- start_time and end_time format: HH:MM:SS[.ms]
- Uses ffmpeg's stream copy (-c copy) for zero quality loss.
- Optimized for low memory and CPU usage.
"""

def extract_clip(start_time, end_time, output_name):
    script_dir = os.path.dirname(os.path.abspath(__file__))
    input_path = os.path.join(script_dir, "input.webm")
    output_path = os.path.join(script_dir, output_name)

    if not os.path.isfile(input_path):
        print(f"[ERROR] Input file not found: {input_path}")
        sys.exit(1)

    # Ensure output directory exists
    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)

    # Minimal memory & CPU ffmpeg call
    cmd = [
        "ffmpeg",
        "-hide_banner",
        "-nostdin",
        "-loglevel", "error",   # suppress unnecessary logs
        "-y",                   # overwrite without prompt
        "-ss", start_time,      # precise start
        "-to", end_time,        # precise end
        "-i", input_path,
        "-map", "0",            # map all streams (video, audio, subtitles)
        "-c", "copy",           # no re-encode = no quality loss
        "-avoid_negative_ts", "make_zero",  # fix timestamp edge cases
        output_path
    ]

    print(f"[INFO] Extracting from input.webm → {output_name} [{start_time} - {end_time}]")

    try:
        # Run ffmpeg in a subprocess, releasing Python memory while processing
        subprocess.run(cmd, check=True)
        print(f"[SUCCESS] Saved: {output_path}")
    except subprocess.CalledProcessError:
        print("[ERROR] ffmpeg failed during extraction.")
        sys.exit(1)
    finally:
        # Force cleanup of any residual handles or buffers
        import gc
        gc.collect()

def main():
    if len(sys.argv) != 4:
        print("Usage: python extract_clip.py start_time end_time output_name.webm")
        sys.exit(1)

    start_time, end_time, output_name = sys.argv[1:]
    extract_clip(start_time, end_time, output_name)

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n[ABORTED] Interrupted by user.")
        sys.exit(0)
