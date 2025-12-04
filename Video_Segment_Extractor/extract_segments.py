#!/usr/bin/env python3
"""
Video Segment Extractor (Lossless)
-----------------------------------
Extracts multiple segments from a video without re-encoding (preserves quality).

Usage:
    python3 extract_segments.py -i input.webm -s segments.txt
    
    OR with inline segments:
    python3 extract_segments.py -i input.webm --segments "0:10-0:30" "1:15-2:00" "5:00-5:45"

Segments file format (segments.txt):
    0:10-0:30
    1:15-2:00
    5:00-5:45
    
Time format: MM:SS or HH:MM:SS

Features:
    - Lossless extraction (stream copy, no re-encoding)
    - Batch processing of multiple segments
    - Automatic output naming
    - Quality preservation
"""

import os
import sys
import subprocess
import argparse
from pathlib import Path


def parse_timestamp(timestamp):
    """
    Convert timestamp string (MM:SS or HH:MM:SS) to seconds.
    """
    parts = timestamp.strip().split(':')
    
    if len(parts) == 2:  # MM:SS
        minutes, seconds = parts
        return int(minutes) * 60 + float(seconds)
    elif len(parts) == 3:  # HH:MM:SS
        hours, minutes, seconds = parts
        return int(hours) * 3600 + int(minutes) * 60 + float(seconds)
    else:
        raise ValueError(f"Invalid timestamp format: {timestamp}")


def parse_segment(segment_str):
    """
    Parse segment string like "0:10-0:30" into (start_seconds, end_seconds).
    """
    try:
        start_str, end_str = segment_str.strip().split('-')
        start = parse_timestamp(start_str)
        end = parse_timestamp(end_str)
        
        if end <= start:
            raise ValueError(f"End time must be after start time: {segment_str}")
        
        return start, end
    except Exception as e:
        raise ValueError(f"Error parsing segment '{segment_str}': {e}")


def read_segments_file(filepath):
    """
    Read segments from a text file.
    Each line should be in format: START-END (e.g., 0:10-0:30)
    """
    segments = []
    
    with open(filepath, 'r') as f:
        for line_num, line in enumerate(f, 1):
            line = line.strip()
            
            # Skip empty lines and comments
            if not line or line.startswith('#'):
                continue
            
            try:
                start, end = parse_segment(line)
                segments.append((start, end))
            except ValueError as e:
                print(f"[WARNING] Line {line_num}: {e}")
                continue
    
    return segments


def format_time(seconds):
    """
    Convert seconds to HH:MM:SS format.
    """
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = seconds % 60
    
    if hours > 0:
        return f"{hours:02d}:{minutes:02d}:{secs:05.2f}"
    else:
        return f"{minutes:02d}:{secs:05.2f}"


def extract_segment(input_file, start, end, output_file):
    """
    Extract a segment from input_file using FFmpeg stream copy (lossless).
    
    Args:
        input_file: Path to input video
        start: Start time in seconds
        end: End time in seconds
        output_file: Path to output file
    """
    duration = end - start
    
    print(f"\n[EXTRACT] {format_time(start)} → {format_time(end)} (duration: {format_time(duration)})")
    print(f"[OUTPUT] {output_file}")
    
    cmd = [
        "ffmpeg",
        "-nostdin",
        "-loglevel", "error",
        "-stats",
        "-y",
        "-ss", f"{start:.3f}",      # Start time
        "-t", f"{duration:.3f}",     # Duration
        "-i", input_file,
        "-c", "copy",                # Stream copy (lossless)
        output_file
    ]
    
    try:
        subprocess.run(cmd, check=True)
        
        # Get output file size
        size_mb = os.path.getsize(output_file) / (1024 * 1024)
        print(f"[SUCCESS] Created {output_file} ({size_mb:.2f} MB)")
        
    except subprocess.CalledProcessError as e:
        print(f"[ERROR] Failed to extract segment: {e}")
        return False
    
    return True


def main():
    parser = argparse.ArgumentParser(
        description="Extract video segments without quality loss",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Using segments file
  python3 extract_segments.py -i input.webm -s segments.txt
  
  # Using inline segments
  python3 extract_segments.py -i input.webm --segments "0:10-0:30" "1:15-2:00"
  
  # Custom output directory
  python3 extract_segments.py -i input.webm -s segments.txt -o my_clips

Segments file format (one per line):
  0:10-0:30
  1:15-2:00
  5:00-5:45
  
Time format: MM:SS or HH:MM:SS
        """
    )
    
    parser.add_argument("-i", "--input", required=True,
                       help="Input video file")
    parser.add_argument("-s", "--segments-file",
                       help="Text file containing segments (one per line: START-END)")
    parser.add_argument("--segments", nargs='+',
                       help="Inline segments (e.g., '0:10-0:30' '1:15-2:00')")
    parser.add_argument("-o", "--output-dir", default="output",
                       help="Output directory (default: output)")
    parser.add_argument("--prefix", default="segment",
                       help="Output file prefix (default: segment)")
    
    args = parser.parse_args()
    
    # Validate input file
    if not os.path.exists(args.input):
        print(f"[ERROR] Input file not found: {args.input}")
        sys.exit(1)
    
    # Get segments from file or inline arguments
    segments = []
    
    if args.segments_file:
        if not os.path.exists(args.segments_file):
            print(f"[ERROR] Segments file not found: {args.segments_file}")
            sys.exit(1)
        segments = read_segments_file(args.segments_file)
    elif args.segments:
        for seg_str in args.segments:
            try:
                start, end = parse_segment(seg_str)
                segments.append((start, end))
            except ValueError as e:
                print(f"[ERROR] {e}")
                sys.exit(1)
    else:
        print("[ERROR] Must provide either --segments-file or --segments")
        parser.print_help()
        sys.exit(1)
    
    if not segments:
        print("[ERROR] No valid segments found")
        sys.exit(1)
    
    # Create output directory
    os.makedirs(args.output_dir, exist_ok=True)
    
    # Get input file extension
    input_ext = Path(args.input).suffix
    
    # Extract segments
    print(f"\n{'='*70}")
    print(f"VIDEO SEGMENT EXTRACTOR")
    print(f"{'='*70}")
    print(f"Input: {args.input}")
    print(f"Output directory: {args.output_dir}")
    print(f"Segments to extract: {len(segments)}")
    print(f"{'='*70}")
    
    successful = 0
    failed = 0
    
    for i, (start, end) in enumerate(segments, 1):
        output_file = os.path.join(
            args.output_dir,
            f"{args.prefix}_{i:03d}{input_ext}"
        )
        
        if extract_segment(args.input, start, end, output_file):
            successful += 1
        else:
            failed += 1
    
    # Summary
    print(f"\n{'='*70}")
    print(f"SUMMARY")
    print(f"{'='*70}")
    print(f"✅ Successful: {successful}")
    if failed > 0:
        print(f"❌ Failed: {failed}")
    print(f"📁 Output directory: {args.output_dir}")
    print(f"{'='*70}\n")


if __name__ == "__main__":
    main()
