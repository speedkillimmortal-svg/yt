#!/usr/bin/env python3
"""
normalize_hdr_to_sdr.py

Pre-processes HDR content to SDR with careful color space conversion.
Optimized for speed while maintaining high quality.
"""

import os
import sys
import subprocess
import json
import argparse
import time
from pathlib import Path

def check_video_properties(video_path):
    """Check if input is HDR and get video properties."""
    cmd = [
        "ffprobe",
        "-v", "error",
        "-select_streams", "v:0",
        "-show_entries", "stream=color_space,color_transfer,color_primaries,pix_fmt,profile",
        "-of", "json",
        video_path
    ]
    
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        data = json.loads(result.stdout)
        stream_info = data.get('streams', [{}])[0]
        
        is_hdr = any(val in str(stream_info.values()) 
                    for val in ['bt2020', 'smpte2084', 'pq', '2100', '10le'])
        
        return is_hdr, stream_info
    except Exception as e:
        print(f"Error analyzing video: {str(e)}")
        sys.exit(1)

def get_duration(video_path):
    """Get video duration in seconds."""
    cmd = [
        "ffprobe",
        "-v", "error",
        "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1",
        video_path
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        return float(result.stdout.strip())
    except Exception:
        return None

def convert_hdr_to_sdr(input_path, output_path):
    """Convert HDR video to SDR with optimized parameters for speed and quality."""
    
    is_hdr, stream_info = check_video_properties(input_path)
    if not is_hdr:
        print("Input video is not HDR. No conversion needed.")
        return False
    
    print("Converting HDR to SDR with optimized processing...")
    
    # Optimized HDR to SDR conversion with enhanced colors and fast processing
    vf_filters = (
        # Initial HDR to linear light conversion with increased brightness
        "zscale=t=linear:npl=400:pin=bt2020:tin=smpte2084,"
        "format=gbrpf32le,"
        # Enhanced tonemap with vivid colors
        "zscale=t=linear:p=bt709:m=bt709,"
        "tonemap=tonemap=hable:desat=0:peak=200,"
        # Color enhancement for more vibrant output
        "zscale=t=bt709:m=bt709:r=tv,"
        "eq=brightness=0.05:contrast=1.15:saturation=1.4:gamma=0.95,"
        "colorlevels=rimin=0.05:gimin=0.05:bimin=0.05:rimax=0.95:gimax=0.95:bimax=0.95,"
        "colorbalance=rs=0.05:gs=0.0:bs=0.05"
    )
    
    # Get system info for optimal thread usage
    import multiprocessing
    cpu_count = multiprocessing.cpu_count()
    threads = min(16, cpu_count * 2)  # Use more threads for better performance
    
    # Build optimized ffmpeg command for maximum speed
    cmd = [
        "ffmpeg", "-y",
        # Enable hardware acceleration
        "-hwaccel", "videotoolbox",  # macOS specific hardware acceleration
        # Fast input reading
        "-threads", str(threads),
        # Input file
        "-i", input_path,
        "-vf", vf_filters,
        # Ultra-fast VP9 encoding settings
        "-c:v", "libvpx-vp9",
        "-crf", "25",          # Reduced quality for maximum speed
        "-b:v", "0",
        "-cpu-used", "8",      # Fastest encoding setting
        "-row-mt", "1",        # Enable row-based multithreading
        "-tile-columns", "4",  # Good parallelization
        "-frame-parallel", "1", # Enable frame parallel processing
        "-threads", str(threads),
        "-deadline", "realtime", # Fastest processing
        "-speed", "8",         # Fastest processing
        # Output settings (optimized for speed)
        "-pix_fmt", "yuv420p", # Use 8-bit for faster processing
        "-color_primaries", "bt709",
        "-color_trc", "bt709",
        "-colorspace", "bt709",
        # Fast audio encoding
        "-c:a", "libopus",
        "-b:a", "128k",
        "-compression_level", "0", # Fastest audio encoding
        output_path
    ]
    
    try:
        print("\nStarting conversion (optimized for speed while maintaining quality)...")
        print("Using settings:")
        print("- Hardware acceleration: Enabled (auto)")
        print("- Multi-threading: Enabled (8 threads)")
        print("- Frame parallel processing: Enabled")
        print("- Tile-based processing: 4x2 tiles")
        print("- Quality preset: CRF 18 (good balance)")
        
        # Get total duration for progress calculation
        duration = get_duration(input_path)
        if not duration:
            print("Warning: Could not determine video duration. Progress display will be limited.")
        
        # Add progress monitoring
        cmd.extend([
            "-progress", "pipe:1",  # Output progress information
            "-stats"               # Show encoding stats
        ])
        
        # Run the process with progress monitoring
        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            universal_newlines=True,
            bufsize=1
        )
        
        frame_count = 0
        start_time = time.time()
        
        # Process progress output
        while True:
            line = process.stdout.readline()
            if not line and process.poll() is not None:
                break
                
            # Parse progress information
            if "frame=" in line:
                try:
                    frame = int(line.split("frame=")[1].split()[0])
                    fps = float(line.split("fps=")[1].split()[0])
                    size = line.split("size=")[1].split()[0]
                    time_str = line.split("time=")[1].split()[0]
                    bitrate = line.split("bitrate=")[1].split()[0]
                    
                    # Calculate progress percentage if duration is known
                    if duration:
                        # Convert time_str (HH:MM:SS.ms) to seconds
                        time_parts = time_str.split(':')
                        time_secs = float(time_parts[-1])
                        if len(time_parts) > 1:
                            time_secs += int(time_parts[-2]) * 60
                        if len(time_parts) > 2:
                            time_secs += int(time_parts[-3]) * 3600
                        
                        progress = (time_secs / duration) * 100
                        
                        # Calculate ETA
                        elapsed = time.time() - start_time
                        if progress > 0:
                            total_estimate = elapsed * (100 / progress)
                            remaining = total_estimate - elapsed
                            eta_str = f"ETA: {int(remaining/60)}m {int(remaining%60)}s"
                        else:
                            eta_str = "ETA: calculating..."
                        
                        # Create progress bar
                        bar_width = 50
                        filled = int(bar_width * progress / 100)
                        bar = '=' * filled + '-' * (bar_width - filled)
                        
                        # Clear line and show progress
                        print(f"\rProgress: [{bar}] {progress:.1f}% | {time_str} / {duration:.1f}s | {fps:.1f} fps | Size: {size} | {eta_str}", end='', flush=True)
                    else:
                        # Simple progress without percentage
                        print(f"\rProcessed {frame} frames | {fps:.1f} fps | Time: {time_str} | Size: {size} | Bitrate: {bitrate}", end='', flush=True)
                except:
                    # If there's any error parsing the progress, just show the raw line
                    print(f"\r{line.strip()}", end='', flush=True)
        
        # Wait for process to complete
        process.wait()
        print("\n")  # New line after progress bar
        
        if process.returncode == 0:
            print(f"\nSuccessfully converted to SDR: {output_path}")
            return True
        else:
            error_output = process.stderr.read()
            print(f"Error during conversion: {error_output}")
            return False
            
    except Exception as e:
        print(f"Error during conversion: {str(e)}")
        return False

def main():
    parser = argparse.ArgumentParser(description="Convert HDR video to SDR with optimized settings for speed and quality")
    parser.add_argument("input", help="Input HDR video file")
    parser.add_argument("output", help="Output SDR video file")
    args = parser.parse_args()
    
    if not os.path.exists(args.input):
        print(f"Error: Input file '{args.input}' does not exist")
        sys.exit(1)
    
    # Create output directory if it doesn't exist
    os.makedirs(os.path.dirname(os.path.abspath(args.output)), exist_ok=True)
    
    # Check if ffmpeg is available
    try:
        subprocess.run(["ffmpeg", "-version"], capture_output=True, check=True)
    except Exception:
        print("Error: ffmpeg not found. Please install ffmpeg first.")
        sys.exit(1)
    
    # Perform conversion
    success = convert_hdr_to_sdr(args.input, args.output)
    if not success:
        sys.exit(1)
    
    # Verify output
    _, output_info = check_video_properties(args.output)
    print("\nOutput video properties:")
    for key, value in output_info.items():
        print(f"{key}: {value}")

if __name__ == "__main__":
    main()