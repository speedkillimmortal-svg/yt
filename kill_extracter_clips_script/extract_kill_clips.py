# AI Kill Clip Extractor
# This script uses a pre-trained action recognition model to detect kill events in a video and extracts those clips.

# Requirements: torch, torchvision, opencv-python, ffmpeg-python

# === CONFIGURATION ===
# Set the keyword or player name to extract kills for (case-insensitive substring match)
KILL_KEYWORD = "immortal"  # Change this to the player name or phrase you want to detect

# Number of seconds to include before the detected kill event in the output clip
PRE_SEC = 5  # e.g., 5 means the clip will start 5 seconds before the detected event
# Number of seconds to include after the detected kill event in the output clip
POST_SEC = 5  # e.g., 5 means the clip will end 5 seconds after the detected event


import cv2
import ffmpeg
import os
import subprocess
import pytesseract
from PIL import Image

def find_immortal_and_extract(video_path, output_dir, ocr_interval=0.5, pre_sec=5, post_sec=5):
    """
    Scan video for the KILL_KEYWORD in the middle of the left side using OCR, extract a clip PRE_SEC seconds before and POST_SEC seconds after each detection.
    """
    os.makedirs(output_dir, exist_ok=True)
    cap = cv2.VideoCapture(video_path)
    fps = cap.get(cv2.CAP_PROP_FPS)
    frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    duration = frame_count / fps
    print(f"Video FPS: {fps}, Total frames: {frame_count}, Duration: {duration}s")

    found_times = []
    sec = 0.0
    last_found = -100  # To avoid duplicate detections within a short window
    while sec < duration:
        cap.set(cv2.CAP_PROP_POS_MSEC, sec * 1000)
        ret, frame = cap.read()
        if not ret:
            sec += ocr_interval
            continue
        h, w, _ = frame.shape
        y1 = int(h * 1/3)
        y2 = int(h * 2/3)
        x1 = 0
        x2 = int(w * 0.25)
        region = frame[y1:y2, x1:x2]
        pil_img = Image.fromarray(cv2.cvtColor(region, cv2.COLOR_BGR2RGB))
        text = pytesseract.image_to_string(pil_img)
        if KILL_KEYWORD.lower() in text.lower() and (sec - last_found > pre_sec + post_sec):
            found_times.append(sec)
            last_found = sec
            print(f"Found '{KILL_KEYWORD}' at {sec:.2f} seconds")
        sec += ocr_interval
    cap.release()

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
            print(f"Saved: {out_file}")
    else:
        print(f"No '{KILL_KEYWORD}' found in video.")


def split_video_into_parts(input_path, num_parts=4, output_prefix="part"):
    """
    Split the input video into num_parts equal parts using ffmpeg.
    Returns a list of output part filenames.
    """
    # Get video duration using ffprobe
    try:
        result = subprocess.run([
            "ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", input_path
        ], capture_output=True, text=True, check=True)
        duration = float(result.stdout.strip())
    except Exception as e:
        print(f"Error getting video duration: {e}")
        return []
    part_length = duration / num_parts
    part_files = []
    for i in range(num_parts):
        start = i * part_length
        out_file = f"{output_prefix}{i+1}.mp4"
        cmd = [
            "ffmpeg", "-nostdin", "-loglevel", "error", "-y", "-i", input_path, "-ss", str(start), "-t", str(part_length), "-c", "copy", out_file
        ]
        print(f"Splitting: {' '.join(cmd)}")
        subprocess.run(cmd, check=True)
        part_files.append(out_file)
    return part_files

if __name__ == "__main__":
    # Use absolute path for input.mp4
    script_dir = os.path.dirname(os.path.abspath(__file__))
    video_path = os.path.join(script_dir, "input.mp4")
    # Output directory is based on the keyword for clarity and organization
    output_dir = os.path.join(script_dir, f"{KILL_KEYWORD.capitalize()}_clips")
    # Step 1: Split the main video into 4 parts
    print("Splitting main video into 4 parts...")
    part_files = split_video_into_parts(video_path, num_parts=4, output_prefix=os.path.join(script_dir, "part"))
    print(f"Parts created: {part_files}")
    # Step 2: Process each part one by one
    for idx, part_file in enumerate(part_files, 1):
        print(f"\nProcessing {part_file} ...")
        part_output_dir = os.path.join(output_dir, f"part{idx}")
        find_immortal_and_extract(part_file, part_output_dir, pre_sec=PRE_SEC, post_sec=POST_SEC)
