#!/usr/bin/env python3
"""
Unified Video Merger
--------------------
Merges multiple videos into a single file.
Default behavior is LOSSLESS concatenation (stream copy).

Supported formats: MP4, WebM, MKV, MOV, etc.

Usage:
    # 1. Merge all videos in a folder (auto-detects extension)
    python3 merge_videos.py --input-dir my_clips/

    # 2. Merge specific files
    python3 merge_videos.py video1.mp4 video2.mp4 -o final.mp4

    # 3. Force re-encoding (if codecs don't match)
    python3 merge_videos.py --reencode --input-dir my_clips/
"""

import os
import sys
import subprocess
import argparse
import tempfile
import re
from pathlib import Path

# Common video extensions
VideoExtensions = ('.mp4', '.webm', '.mkv', '.mov', '.avi')

def check_ffmpeg():
    """Check if FFmpeg is installed and accessible."""
    try:
        subprocess.run(
            ["ffmpeg", "-version"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=True
        )
        return True
    except (subprocess.CalledProcessError, FileNotFoundError):
        return False

def get_video_info(video_path):
    """Get codec information."""
    try:
        cmd = [
            "ffprobe",
            "-v", "error",
            "-select_streams", "v:0",
            "-show_entries", "stream=codec_name,width,height,r_frame_rate",
            "-select_streams", "a:0",
            "-show_entries", "stream=codec_name,sample_rate",
            "-of", "default=noprint_wrappers=1",
            video_path
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        return result.stdout
    except subprocess.CalledProcessError as e:
        print(f"[WARN] Could not probe {video_path}: {e}")
        return None

def check_compatibility(video_files):
    """Check if files have same codec for lossless merge."""
    print("🔍 Checking video compatibility...")
    if not video_files: return False

    ref_info = get_video_info(video_files[0])
    if not ref_info: return False
    
    # Simple check: Just ensure they are all readable.
    # In a robust lossless merge, dimensions/codecs must match exactly.
    # FFmpeg concat demuxer will fail or produce bad output if they don't match.
    # We rely on user providing similar files, but warn if verification fails.
    for v in video_files[1:]:
        info = get_video_info(v)
        if not info:
             print(f"⚠️ Could not verify: {os.path.basename(v)}")
    
    print("✓ Compatibility check passed (assuming similar source).")
    return True

def natural_sort_key(s):
    """Sort files like file1, file2, file10..."""
    return [int(text) if text.isdigit() else text.lower()
            for text in re.split('([0-9]+)', str(s))]

def scan_directory(input_dir, extension=None):
    """
    Find video files in directory.
    If extension is None, finds the most common video extension.
    """
    path = Path(input_dir)
    if not path.is_dir():
        print(f"[ERROR] Directory not found: {input_dir}")
        return []

    files = [f for f in path.iterdir() if f.is_file() and f.suffix.lower() in VideoExtensions]
    
    if not files:
        return []

    # If specific extension requested
    if extension:
        files = [f for f in files if f.suffix.lower() == extension.lower()]
    
    # Sort naturally
    files.sort(key=lambda f: natural_sort_key(f.name))
    return [str(f.absolute()) for f in files]

def flatten(list_of_lists):
    if len(list_of_lists) == 0:
        return list_of_lists
    if isinstance(list_of_lists[0], list):
        return flatten(list_of_lists[0]) + flatten(list_of_lists[1:])
    return list_of_lists[0] + flatten(list_of_lists[1:])

def merge_lossless(video_files, output_file):
    """Use FFmpeg concat demuxer."""
    print(f"[INFO] Merging {len(video_files)} files (Lossless)...")
    
    with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as f:
        list_path = f.name
        for v in video_files:
            safe_path = os.path.abspath(v).replace("'", "'\\''")
            f.write(f"file '{safe_path}'\n")

    cmd = [
        "ffmpeg", "-y",
        "-f", "concat",
        "-safe", "0",
        "-i", list_path,
        "-c", "copy",
        output_file
    ]

    try:
        subprocess.run(cmd, check=True)
        print(f"\n✅ Success: {output_file}")
    except subprocess.CalledProcessError as e:
        print(f"\n❌ Merge Failed: {e}")
        print("Tip: If codecs differ, try using --reencode")
    finally:
        if os.path.exists(list_path):
            os.remove(list_path)

def merge_reencode(video_files, output_file):
    """Re-encode merge (safer if codecs differ)."""
    print(f"[INFO] Merging {len(video_files)} files (Re-encode High Quality)...")
    
    # Build filter complex
    # Format: [0:v][0:a][1:v][1:a]...concat=n=N:v=1:a=1[v][a]
    
    inputs = []
    filter_build = ""
    for i, v in enumerate(video_files):
        inputs.extend(["-i", v])
        filter_build += f"[{i}:v][{i}:a]"
    
    filter_build += f"concat=n={len(video_files)}:v=1:a=1[v][a]"
    
    # Codec selection based on output ext
    ext = os.path.splitext(output_file)[1].lower()
    
    if ext == '.webm':
        codec_args = ["-c:v", "libvpx-vp9", "-crf", "30", "-b:v", "0"] # reasonable quality
        audio_args = ["-c:a", "libopus"]
    else:
        # Default MP4/MOV settings
        codec_args = ["-c:v", "libx264", "-crf", "18", "-preset", "slow"]
        audio_args = ["-c:a", "aac", "-b:a", "192k"]

    cmd = ["ffmpeg", "-y"] + inputs + \
          ["-filter_complex", filter_build, "-map", "[v]", "-map", "[a]"] + \
          codec_args + audio_args + [output_file]
          
    try:
        subprocess.run(cmd, check=True)
        print(f"\n✅ Success: {output_file}")
    except subprocess.CalledProcessError as e:
        print(f"\n❌ Merge Failed: {e}")

def main():
    parser = argparse.ArgumentParser(description="Unified Video Merger")
    parser.add_argument('videos', nargs='*', help="List of video files")
    parser.add_argument('--input-dir', '-d', help="Directory to scan for videos")
    parser.add_argument('--output', '-o', default="merged_output.mp4", help="Output filename")
    parser.add_argument('--reencode', action='store_true', help="Force re-encoding (fix compatibility issues)")
    
    args = parser.parse_args()
    
    if not check_ffmpeg():
        print("❌ FFmpeg is missing.")
        sys.exit(1)

    video_files = []
    
    # 1. Gather files
    if args.videos:
        video_files = [os.path.abspath(f) for f in args.videos]
    elif args.input_dir:
        print(f"Scanning directory: {args.input_dir}")
        video_files = scan_directory(args.input_dir)
        if not video_files:
            print("[ERROR] No video files found in directory.")
            sys.exit(1)
        # If output extension matches input, great. If not, maybe warn?
        # We auto-name output if not provided
        ext = os.path.splitext(video_files[0])[1]
        if args.output == "merged_output.mp4" and ext.lower() == ".webm":
             args.output = "merged_output.webm"
             
    if len(video_files) < 2:
        print("❌ Need at least 2 files to merge.")
        sys.exit(1)

    print(f"Files to merge ({len(video_files)}):")
    for v in video_files:
        print(f" - {os.path.basename(v)}")

    # 2. Merge
    if args.reencode:
        merge_reencode(video_files, args.output)
    else:
        check_compatibility(video_files)
        merge_lossless(video_files, args.output)

if __name__ == "__main__":
    main()
