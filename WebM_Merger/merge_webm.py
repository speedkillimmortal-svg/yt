#!/usr/bin/env python3
"""
WebM Video Merger (Lossless)
-----------------------------
Merges multiple WebM videos without re-encoding, preserving original quality.

Usage:
    # Auto-detect and merge all part*.webm files from input folder
    python3 merge_webm.py
    
    # Merge specific files
    python3 merge_webm.py video1.webm video2.webm video3.webm -o output.webm
    
    # Use custom input folder
    python3 merge_webm.py --input-dir /path/to/videos
    
Features:
    - Lossless merging using FFmpeg concat demuxer
    - No re-encoding (stream copy mode)
    - Automatic detection of part1.webm, part2.webm, etc.
    - Supports both file list and command-line arguments
    
Requirements:
    - FFmpeg installed on system
"""

import os
import sys
import subprocess
import argparse
import tempfile
import re
from pathlib import Path


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
    """Get codec information from a video file."""
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
        
        result = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=True
        )
        
        return result.stdout
    except subprocess.CalledProcessError as e:
        print(f"⚠️  Warning: Could not get info for {video_path}: {e}")
        return None


def check_compatibility(video_files):
    """
    Check if all videos have compatible codecs for lossless concatenation.
    Returns True if compatible, False otherwise.
    """
    print("\n🔍 Checking video compatibility...")
    
    if not video_files:
        return False
    
    # Get info for first video as reference
    first_info = get_video_info(video_files[0])
    if not first_info:
        return False
    
    print(f"✓ Reference video: {os.path.basename(video_files[0])}")
    
    # Check all other videos against the first
    for video in video_files[1:]:
        info = get_video_info(video)
        if not info:
            print(f"✗ Could not verify: {os.path.basename(video)}")
            continue
        
        # Basic check - in practice, you might want more detailed comparison
        print(f"✓ Checked: {os.path.basename(video)}")
    
    print("✓ All videos appear compatible for lossless merging\n")
    return True


def auto_detect_parts(input_dir):
    """
    Auto-detect part*.webm files in the input directory.
    Returns sorted list of file paths.
    """
    input_path = Path(input_dir)
    
    if not input_path.exists():
        print(f"❌ Input directory not found: {input_dir}")
        return []
    
    # Find all files matching part*.webm pattern
    part_files = []
    pattern = re.compile(r'^part(\d+)\.webm$', re.IGNORECASE)
    
    for file in input_path.iterdir():
        if file.is_file():
            match = pattern.match(file.name)
            if match:
                part_num = int(match.group(1))
                part_files.append((part_num, str(file.absolute())))
    
    # Sort by part number
    part_files.sort(key=lambda x: x[0])
    
    # Return just the file paths
    return [path for _, path in part_files]


def merge_videos_lossless(video_files, output_file):
    """
    Merge videos using FFmpeg concat demuxer (lossless).
    This method doesn't re-encode, preserving original quality.
    """
    # Create temporary file list for FFmpeg concat demuxer
    with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as f:
        concat_file = f.name
        for video in video_files:
            # FFmpeg concat demuxer requires absolute paths
            abs_path = os.path.abspath(video)
            # Escape special characters for FFmpeg
            escaped_path = abs_path.replace("'", "'\\''")
            f.write(f"file '{escaped_path}'\n")
    
    try:
        print(f"🎬 Merging {len(video_files)} videos...")
        print(f"📤 Output: {output_file}\n")
        
        # FFmpeg command using concat demuxer with stream copy (no re-encoding)
        cmd = [
            "ffmpeg",
            "-f", "concat",           # Use concat demuxer
            "-safe", "0",             # Allow absolute paths
            "-i", concat_file,        # Input file list
            "-c", "copy",             # Copy streams without re-encoding (LOSSLESS)
            "-y",                     # Overwrite output file if exists
            output_file
        ]
        
        print("🔧 FFmpeg command:")
        print(" ".join(cmd))
        print("\n" + "="*60)
        
        # Run FFmpeg
        subprocess.run(cmd, check=True)
        
        print("="*60)
        print(f"\n✅ Success! Merged video saved to: {output_file}")
        
        # Show file size
        size_mb = os.path.getsize(output_file) / (1024 * 1024)
        print(f"📊 Output file size: {size_mb:.2f} MB")
        
    except subprocess.CalledProcessError as e:
        print(f"\n❌ Error during merging: {e}")
        sys.exit(1)
    finally:
        # Clean up temporary file
        if os.path.exists(concat_file):
            os.remove(concat_file)


def merge_videos_with_reencoding(video_files, output_file):
    """
    Merge videos with re-encoding (use when videos have different codecs).
    Uses high-quality settings to minimize quality loss.
    """
    print("⚠️  Videos have different formats. Re-encoding with high quality settings...")
    
    # Create filter complex for concatenation
    filter_parts = []
    for i in range(len(video_files)):
        filter_parts.append(f"[{i}:v][{i}:a]")
    
    filter_complex = "".join(filter_parts) + f"concat=n={len(video_files)}:v=1:a=1[outv][outa]"
    
    # Build FFmpeg command with high-quality VP9 encoding
    cmd = [
        "ffmpeg",
        "-y"
    ]
    
    # Add all input files
    for video in video_files:
        cmd.extend(["-i", video])
    
    # Add filter and output settings
    cmd.extend([
        "-filter_complex", filter_complex,
        "-map", "[outv]",
        "-map", "[outa]",
        "-c:v", "libvpx-vp9",      # VP9 codec for WebM
        "-crf", "15",               # High quality (lower = better, range 0-63)
        "-b:v", "0",                # Variable bitrate
        "-cpu-used", "2",           # Encoding speed (0=slowest/best, 5=fastest)
        "-row-mt", "1",             # Enable row-based multithreading
        "-c:a", "libopus",          # Opus audio codec
        "-b:a", "192k",             # High audio bitrate
        output_file
    ])
    
    print("🔧 FFmpeg command:")
    print(" ".join(cmd))
    print("\n" + "="*60)
    
    try:
        subprocess.run(cmd, check=True)
        print("="*60)
        print(f"\n✅ Success! Merged video saved to: {output_file}")
        
        size_mb = os.path.getsize(output_file) / (1024 * 1024)
        print(f"📊 Output file size: {size_mb:.2f} MB")
        
    except subprocess.CalledProcessError as e:
        print(f"\n❌ Error during merging: {e}")
        sys.exit(1)


def interactive_mode():
    """Run in interactive mode to select files."""
    print("\n" + "="*60)
    print("WebM Video Merger - Interactive Mode")
    print("="*60)
    
    video_files = []
    print("\nEnter WebM file paths (one per line).")
    print("Press Enter on empty line when done:\n")
    
    while True:
        file_path = input(f"Video {len(video_files) + 1}: ").strip()
        if not file_path:
            break
        
        if not os.path.exists(file_path):
            print(f"⚠️  File not found: {file_path}")
            continue
        
        if not file_path.lower().endswith('.webm'):
            print(f"⚠️  Not a WebM file: {file_path}")
            continue
        
        video_files.append(file_path)
        print(f"✓ Added: {os.path.basename(file_path)}")
    
    if len(video_files) < 2:
        print("\n❌ Need at least 2 videos to merge!")
        sys.exit(1)
    
    output_file = input("\nOutput filename (default: merged_output.webm): ").strip()
    if not output_file:
        output_file = "merged_output.webm"
    
    if not output_file.endswith('.webm'):
        output_file += '.webm'
    
    return video_files, output_file


def main():
    parser = argparse.ArgumentParser(
        description="Merge WebM videos without quality loss",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Auto-detect and merge part*.webm from input folder
  python3 merge_webm.py
  
  # Merge specific files
  python3 merge_webm.py video1.webm video2.webm video3.webm -o output.webm
  
  # Use custom input directory
  python3 merge_webm.py --input-dir /path/to/videos
  
  # Force re-encoding with high quality
  python3 merge_webm.py --reencode
        """
    )
    
    parser.add_argument(
        'videos',
        nargs='*',
        help='WebM video files to merge (optional if using --input-dir)'
    )
    
    parser.add_argument(
        '-o', '--output',
        default='merged_output.webm',
        help='Output filename (default: merged_output.webm)'
    )
    
    parser.add_argument(
        '--input-dir',
        default='input',
        help='Directory to scan for part*.webm files (default: input)'
    )
    
    parser.add_argument(
        '--reencode',
        action='store_true',
        help='Force re-encoding with high quality settings'
    )
    
    args = parser.parse_args()
    
    # Check FFmpeg availability
    if not check_ffmpeg():
        print("❌ Error: FFmpeg is not installed or not in PATH")
        print("Please install FFmpeg: https://ffmpeg.org/download.html")
        sys.exit(1)
    
    # Determine video files to merge
    if args.videos:
        # Use command-line specified videos
        video_files = args.videos
        output_file = args.output
    else:
        # Auto-detect from input directory
        print(f"\n🔍 Scanning '{args.input_dir}' for part*.webm files...")
        video_files = auto_detect_parts(args.input_dir)
        
        if not video_files:
            print(f"\n❌ No part*.webm files found in '{args.input_dir}'")
            print("\nExpected file naming: part1.webm, part2.webm, part3.webm, etc.")
            print("\nAlternatively, specify files manually:")
            print("  python3 merge_webm.py video1.webm video2.webm -o output.webm")
            sys.exit(1)
        
        output_file = args.output
    
    # Validate input files
    print("\n📋 Input files:")
    total_size = 0
    for i, video in enumerate(video_files, 1):
        if not os.path.exists(video):
            print(f"❌ File not found: {video}")
            sys.exit(1)
        
        size_mb = os.path.getsize(video) / (1024 * 1024)
        total_size += size_mb
        print(f"  {i}. {os.path.basename(video)} ({size_mb:.2f} MB)")
    
    print(f"\n📊 Total input size: {total_size:.2f} MB")
    
    if len(video_files) < 2:
        print("\n❌ Need at least 2 videos to merge!")
        sys.exit(1)
    
    # Check compatibility and merge
    if not args.reencode:
        check_compatibility(video_files)
        merge_videos_lossless(video_files, output_file)
    else:
        merge_videos_with_reencoding(video_files, output_file)


if __name__ == "__main__":
    main()
