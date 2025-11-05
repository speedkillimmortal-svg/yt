#!/usr/bin/env python3
"""
experiment_duo.py
Experimental script to extract and merge one clip each from SpeedKill and Immortal gameplay.
Focus on timing analysis and quality assessment.
"""

import os
import sys
import time
import subprocess
import cv2
import shutil

# Configuration
PRE_SEC = 5
POST_SEC = 5
OCR_INTERVAL = 0.5
OCR_RESIZE = 0.6
ROI_NORM = (0.05, 0.60, 0.25, 0.35)  # (y, x, h, w) normalized to video dims
TMP_DIR = "tmp_exp"
OUT_DIR = "exp_output"

def measure_time(func):
    """Decorator to measure execution time of functions"""
    def wrapper(*args, **kwargs):
        start = time.time()
        result = func(*args, **kwargs)
        end = time.time()
        print(f"[TIMING] {func.__name__} took {end - start:.2f} seconds")
        return result
    return wrapper

def run(cmd, check=True):
    """Run a command and return its output"""
    return subprocess.run(cmd, capture_output=True, text=True, check=check)

def require_ffmpeg():
    """Check if ffmpeg is available"""
    try:
        run(["ffmpeg", "-version"])
    except Exception:
        print("[ERROR] ffmpeg not found in PATH. Install with: brew install ffmpeg")
        sys.exit(1)

def init_ocr():
    """Initialize OCR with EasyOCR"""
    try:
        import torch
        use_mps = torch.backends.mps.is_available()
    except Exception:
        use_mps = False
    try:
        import easyocr
        reader = easyocr.Reader(['en'], gpu=use_mps)
        print(f"[INFO] Using EasyOCR (MPS available: {use_mps})")
        return reader
    except Exception:
        print("[ERROR] EasyOCR not available. Install with: pip install easyocr")
        sys.exit(1)

def save_frame_sample(video_path, timestamp, output_path):
    """Save a frame from the video at specified timestamp"""
    try:
        cmd = [
            "ffmpeg", "-nostdin", "-y",
            "-ss", str(timestamp),
            "-i", video_path,
            "-vframes", "1",
            "-q:v", "1",  # Highest quality
            output_path
        ]
        run(cmd)
        return True
    except Exception as e:
        print(f"[ERROR] Failed to save frame: {e}")
        return False

def probe_props(path):
    """Get video stream properties including bitrate and quality info"""
    try:
        # Get stream info
        r = run([
            'ffprobe', '-v', 'error', '-select_streams', 'v:0',
            '-show_entries', 'stream=codec_name,width,height,pix_fmt,r_frame_rate,bit_rate',
            '-show_entries', 'format=bit_rate,size',
            '-of', 'json', path
        ])
        import json
        info = json.loads(r.stdout)
        streams = info.get('streams') or []
        if not streams:
            return None
        s = streams[0]
        return {
            'codec_name': s.get('codec_name'),
            'width': int(s.get('width') or 0),
            'height': int(s.get('height') or 0),
            'pix_fmt': s.get('pix_fmt'),
            'r_frame_rate': s.get('r_frame_rate')
        }
    except Exception:
        return None

def clips_compatible(paths):
    """Check if clips can be merged without re-encoding"""
    base = None
    print("\n[DEBUG] Checking clip compatibility:")
    for p in paths:
        pr = probe_props(p)
        print(f"\nFile: {os.path.basename(p)}")
        if not pr:
            print("  Failed to get properties!")
            return False
        print(f"  Codec: {pr.get('codec_name')}")
        print(f"  Resolution: {pr.get('width')}x{pr.get('height')}")
        print(f"  Pixel Format: {pr.get('pix_fmt')}")
        print(f"  Frame Rate: {pr.get('r_frame_rate')}")
        
        if base is None:
            base = pr
            continue
            
        diffs = []
        for k in ('codec_name', 'width', 'height', 'pix_fmt', 'r_frame_rate'):
            if str(base.get(k)) != str(pr.get(k)):
                diffs.append(f"{k}: {base.get(k)} != {pr.get(k)}")
        
        if diffs:
            print("\n[DEBUG] Incompatible properties:")
            for diff in diffs:
                print(f"  - {diff}")
            return False
    
    print("\n[DEBUG] Clips are compatible!")
    return True

def ocr_frame(reader, region_bgr):
    """Perform OCR on a single frame"""
    if OCR_RESIZE != 1.0:
        region_bgr = cv2.resize(region_bgr, None, fx=OCR_RESIZE, fy=OCR_RESIZE)
    results = reader.readtext(region_bgr, detail=0)
    return " ".join(results).strip()

@measure_time
def find_first_kill(video_path, reader, tmp_root=TMP_DIR):
    """Find the first 'ENEMY DOWNED' event in the video"""
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        print(f"[ERROR] Cannot open {video_path}")
        return None

    # Get video properties
    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    
    # Define ROI coordinates for kill feed
    x1, x2 = int(w * 0.70), w
    y1, y2 = 0, int(h * 0.30)
    step_frames = max(1, int(round(OCR_INTERVAL * fps)))
    
    frame_idx = 0
    while True:
        cap.set(cv2.CAP_PROP_POS_FRAMES, frame_idx)
        ret, frame = cap.read()
        if not ret:
            break

        region = frame[y1:y2, x1:x2]
        text = ocr_frame(reader, region)
        if "enemy downed" in text.lower():
            timestamp = frame_idx / fps
            print(f"[FOUND] First kill at {timestamp:.2f}s in {os.path.basename(video_path)}")
            cap.release()
            return timestamp

        frame_idx += step_frames

    cap.release()
    return None

@measure_time
def extract_clip(video_path, timestamp, output_path, pre=PRE_SEC, post=POST_SEC):
    """Extract a clip with fast stream copy and HDR to SDR conversion"""
    start = max(0.0, timestamp - pre)
    duration = pre + post
    os.makedirs(os.path.dirname(output_path), exist_ok=True)

    # For Immortal clips, use direct copy
    if "immortal" in video_path.lower():
        try:
            cmd = [
                "ffmpeg", "-nostdin", "-y",
                "-ss", f"{start:.3f}",
                "-t", f"{duration:.3f}",
                "-i", video_path,
                "-c:v", "copy",  # Copy video stream
                "-c:a", "copy",  # Copy audio stream
                output_path
            ]
            run(cmd)
            
            # Print clip properties
            props = probe_props(output_path)
            print(f"\n[DEBUG] Extracted clip: {os.path.basename(output_path)}")
            print(f"  Codec: {props.get('codec_name')}")
            print(f"  Resolution: {props.get('width')}x{props.get('height')}")
            print(f"  Pixel Format: {props.get('pix_fmt')}")
            print(f"  Frame Rate: {props.get('r_frame_rate')}")
            
            print(f"[INFO] Fast copy successful for {os.path.basename(video_path)}")
            return output_path
        except Exception as e:
            print(f"[ERROR] Fast copy failed: {e}")
            return None
    
    # For SpeedKill clips, convert HDR to SDR with optimized settings
    try:
        vf = (
            "zscale=t=linear:npl=250:pin=bt2020:tin=smpte2084,"  # HDR to linear light
            "format=gbrpf32le,"                                   # 32-bit float processing
            "zscale=t=linear:p=bt709:m=bt709,"                   # Convert to BT.709 color space
            "tonemap=tonemap=reinhard:peak=100:desat=0,"         # Conservative SDR conversion
            "zscale=t=bt709:m=bt709:r=tv,"                       # Final color space conversion
            "eq=brightness=0.05:contrast=1.1:saturation=1.2"     # Fine-tune colors
        )
        
        cmd = [
            "ffmpeg", "-nostdin", "-y",
            "-ss", f"{start:.3f}",
            "-t", f"{duration:.3f}",
            "-i", video_path,
            "-vf", vf,
            "-pix_fmt", "yuv420p",        # Match Immortal's format
            "-c:v", "libvpx-vp9",         # VP9 codec
            "-crf", "18",                 # High quality
            "-b:v", "0",                  # Use CRF for quality control
            "-color_range", "tv",         # TV range for better compatibility
            "-colorspace", "bt709",       # Standard color space
            "-color_primaries", "bt709",  # Standard color primaries
            "-color_trc", "bt709",        # Standard transfer curve
            "-c:a", "copy",              # Preserve audio
            output_path
        ]
        run(cmd)
        
        # Print clip properties
        props = probe_props(output_path)
        print(f"\n[DEBUG] Extracted clip: {os.path.basename(output_path)}")
        print(f"  Codec: {props.get('codec_name')}")
        print(f"  Resolution: {props.get('width')}x{props.get('height')}")
        print(f"  Pixel Format: {props.get('pix_fmt')}")
        print(f"  Frame Rate: {props.get('r_frame_rate')}")
        
        print(f"[INFO] HDR conversion successful for {os.path.basename(video_path)}")
        return output_path
    except Exception as e:
        print(f"[ERROR] HDR conversion failed: {e}")
        return None

@measure_time
def merge_clips(clip_a, clip_b, output_path):
    """Merge two clips with concat-demuxer, trying fast copy first"""
    list_file = os.path.join(os.path.dirname(output_path), "concat_list.txt")
    with open(list_file, "w", encoding="utf-8") as f:
        for p in [clip_a, clip_b]:
            f.write(f"file '{os.path.abspath(p)}'\n")

    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    
    # Try fast stream copy first
    if clips_compatible([clip_a, clip_b]):
        try:
            print("[INFO] Clips compatible - using fast copy merge")
            run(["ffmpeg", "-nostdin", "-y", "-f", "concat", "-safe", "0",
                 "-i", list_file, 
                 "-c:v", "copy",  # Copy video stream
                 "-c:a", "copy",  # Copy audio stream
                 output_path])
            os.remove(list_file)
            print(f"[MERGED] -> {os.path.basename(output_path)}")
            return True
        except Exception as e:
            print(f"[WARN] Fast copy merge failed: {e}")

    # Fallback to re-encode
    try:
        print("[INFO] Re-encoding for merge compatibility")
        run(["ffmpeg", "-nostdin", "-y", "-f", "concat", "-safe", "0",
             "-i", list_file, 
             "-c:v", "libvpx-vp9",
             "-crf", "18",
             "-b:v", "0",
             "-c:a", "copy",  # Still try to copy audio
             output_path])
        os.remove(list_file)
        print(f"[MERGED] -> {os.path.basename(output_path)}")
        return True
    except Exception as e:
        print(f"[ERROR] Merge failed: {e}")
        if os.path.exists(list_file):
            os.remove(list_file)
        return False

def main():
    if len(sys.argv) != 3:
        print("Usage: python experiment_duo.py <speedkill.webm> <immortal.webm>")
        sys.exit(1)

    speed_path = os.path.abspath(sys.argv[1])
    immortal_path = os.path.abspath(sys.argv[2])
    
    if not all(os.path.exists(p) for p in [speed_path, immortal_path]):
        print("[ERROR] Input files not found")
        sys.exit(1)

    require_ffmpeg()
    reader = init_ocr()

    # Create output structure
    os.makedirs(TMP_DIR, exist_ok=True)
    os.makedirs(OUT_DIR, exist_ok=True)

    # Find first kill in each video
    print("\n[STEP 1] Finding first kill in each video...")
    speed_time = find_first_kill(speed_path, reader)
    immortal_time = find_first_kill(immortal_path, reader)

    if not all([speed_time is not None, immortal_time is not None]):
        print("[ERROR] Could not find kills in both videos")
        sys.exit(1)

    # Extract clips
    print("\n[STEP 2] Extracting clips...")
    speed_clip = os.path.join(TMP_DIR, "speed_clip.webm")
    immortal_clip = os.path.join(TMP_DIR, "immortal_clip.webm")
    
    extract_clip(speed_path, speed_time, speed_clip)
    extract_clip(immortal_path, immortal_time, immortal_clip)

    # Merge clips
    print("\n[STEP 3] Merging clips...")
    final_output = os.path.join(OUT_DIR, "experiment_merged.webm")
    merge_clips(speed_clip, immortal_clip, final_output)

    # Cleanup
    try:
        shutil.rmtree(TMP_DIR)
        print("\n[CLEANUP] Removed temporary files")
    except:
        pass

    # Extract sample frames for color analysis
    print("\n[ANALYZING] Extracting frame samples for color analysis...")
    
    # Save frames from both parts of the merged video
    speed_sample = os.path.join(OUT_DIR, "speedkill_sample.jpg")
    immortal_sample = os.path.join(OUT_DIR, "immortal_sample.jpg")
    
    # Sample middle frames from each clip
    save_frame_sample(final_output, 2.5, speed_sample)  # Middle of first clip
    save_frame_sample(final_output, PRE_SEC + POST_SEC + 2.5, immortal_sample)  # Middle of second clip
    
    print("\n✅ [DONE] Output saved as:", final_output)
    print("\nFrame samples saved for color analysis:")
    print(f"SpeedKill sample: {speed_sample}")
    print(f"Immortal sample: {immortal_sample}")
    
    print("\nQuality Assessment:")
    print("1. Check the output video for:")
    print("   - Color accuracy and consistency")
    print("   - HDR to SDR conversion quality")
    print("   - Smooth transitions between clips")
    print("2. Review the timing measurements above")
    print("3. Compare output file size with input clips")
    print("\nPlease examine the saved frame samples to analyze color differences\n")

if __name__ == "__main__":
    main()