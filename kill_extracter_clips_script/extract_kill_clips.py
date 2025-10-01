import cv2
import ffmpeg
import os
import subprocess
import pytesseract
from PIL import Image
from concurrent.futures import ThreadPoolExecutor

# === CONFIGURATION ===
KILL_KEYWORD = "immortal"
PRE_SEC = 5
POST_SEC = 5
OCR_INTERVAL = 0.5   # seconds between OCR scans
OCR_RESIZE = 0.5     # resize factor for faster OCR (0.5 = half size, 2.0 = double size)
MAX_THREADS = 4      # OCR threads for speedup

def ocr_frame(region):
    """Run OCR on cropped region with resizing optimization"""
    if OCR_RESIZE != 1.0:
        region = cv2.resize(region, None, fx=OCR_RESIZE, fy=OCR_RESIZE, interpolation=cv2.INTER_LINEAR)
    pil_img = Image.fromarray(cv2.cvtColor(region, cv2.COLOR_BGR2RGB))
    text = pytesseract.image_to_string(pil_img)
    return text

def find_immortal_and_extract(video_path, output_dir, ocr_interval=0.5, pre_sec=5, post_sec=5):
    os.makedirs(output_dir, exist_ok=True)
    cap = cv2.VideoCapture(video_path)
    fps = cap.get(cv2.CAP_PROP_FPS)
    frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    duration = frame_count / fps
    print(f"Video FPS: {fps}, Total frames: {frame_count}, Duration: {duration:.2f}s")

    found_times = []
    sec = 0.0
    last_found = -100

    executor = ThreadPoolExecutor(max_workers=MAX_THREADS)

    while sec < duration:
        cap.set(cv2.CAP_PROP_POS_MSEC, sec * 1000)
        ret, frame = cap.read()
        if not ret:
            sec += ocr_interval
            continue

        h, w, _ = frame.shape
        y1, y2 = int(h * 1/3), int(h * 2/3)
        x1, x2 = 0, int(w * 0.25)
        region = frame[y1:y2, x1:x2]

        # Run OCR (threaded for speedup)
        future = executor.submit(ocr_frame, region)
        text = future.result()

        if KILL_KEYWORD.lower() in text.lower() and (sec - last_found > pre_sec + post_sec):
            found_times.append(sec)
            last_found = sec
            print(f"✅ Found '{KILL_KEYWORD}' at {sec:.2f}s")

        sec += ocr_interval

    cap.release()
    executor.shutdown(wait=True)

    # Extract clips with ffmpeg
    if found_times:
        for idx, found_time in enumerate(found_times, 1):
            start = max(0, found_time - pre_sec)
            clip_length = pre_sec + post_sec
            out_file = os.path.join(output_dir, f"{KILL_KEYWORD.lower()}_clip_{idx}.mp4")
            (
                ffmpeg
                .input(video_path, ss=start, t=clip_length)
                .output(out_file, c="copy")
                .global_args('-nostdin', '-loglevel', 'error')
                .run(overwrite_output=True)
            )
            print(f"💾 Saved: {out_file}")
    else:
        print(f"⚠️ No '{KILL_KEYWORD}' found in {video_path}")

def split_video_into_parts(input_path, num_parts=4, output_prefix="part"):
    try:
        result = subprocess.run([
            "ffprobe", "-v", "error", "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1", input_path
        ], capture_output=True, text=True, check=True)
        duration = float(result.stdout.strip())
    except Exception as e:
        print(f"Error getting video duration: {e}")
        return []

    part_length = duration / num_parts
    part_files = []

    for i in range(num_parts):
        start = i * part_length
        out_file = f"{output_prefix}{i+1}.webm"  # keep webm codec if possible
        cmd = [
            "ffmpeg", "-nostdin", "-loglevel", "error", "-y",
            "-i", input_path, "-ss", str(start), "-t", str(part_length),
            "-c", "copy", out_file
        ]
        print(f"Splitting: {' '.join(cmd)}")
        subprocess.run(cmd, check=True)
        part_files.append(out_file)

    return part_files

if __name__ == "__main__":
    import sys
    import gc
    try:
        # Use absolute path for input.webm
        script_dir = os.path.dirname(os.path.abspath(__file__))
        video_path = os.path.join(script_dir, "input.webm")
        output_dir = os.path.join(script_dir, f"{KILL_KEYWORD.capitalize()}_clips")
        print("Splitting main video into 4 parts...")
        part_files = split_video_into_parts(video_path, num_parts=4, output_prefix=os.path.join(script_dir, "part"))
        print(f"Parts created: {part_files}")
        for idx, part_file in enumerate(part_files, 1):
            print(f"\nProcessing {part_file} ...")
            part_output_dir = os.path.join(output_dir, f"part{idx}")
            find_immortal_and_extract(part_file, part_output_dir, pre_sec=PRE_SEC, post_sec=POST_SEC)
        gc.collect()
        sys.exit(0)
    except Exception as e:
        print(f"[FATAL ERROR] {e}")
        sys.exit(1)
