# AI Kill Clip Extractor

This script automatically splits a large video into 4 parts and extracts highlight clips based on a configurable keyword (e.g., player name or phrase) using OCR.

## Features
- Splits any input video into 4 equal parts for efficient processing
- Extracts clips where the keyword appears on screen (using Tesseract OCR)
- Configurable keyword, pre- and post-event seconds
- Output clips are organized by keyword and part

## Requirements
- Python 3.8+
- ffmpeg (installed and available in PATH)
- ffprobe (comes with ffmpeg)
- Tesseract OCR (installed and available in PATH)
- Python packages: opencv-python, ffmpeg-python, pillow, pytesseract

## Setup
1. **Install ffmpeg and ffprobe**
   - macOS: `brew install ffmpeg`
   - Ubuntu: `sudo apt install ffmpeg`
2. **Install Tesseract OCR**
   - macOS: `brew install tesseract`
   - Ubuntu: `sudo apt install tesseract-ocr`
3. **Install Python dependencies** (in your virtual environment):
   ```sh
   pip install opencv-python ffmpeg-python pillow pytesseract
   ```
4. **Place your video file** in the `kill_extracter_clips_script` folder and rename it to `input.mp4`.

## Configuration
Edit the top of `extract_kill_clips.py` to set:
- `KILL_KEYWORD` — the player name or phrase to detect (case-insensitive)
- `PRE_SEC` — seconds before the event to include in each clip
- `POST_SEC` — seconds after the event to include in each clip

## Usage
From the `kill_extracter_clips_script` directory, run:
```sh
python extract_kill_clips.py
```

## Output
- The script will split `input.mp4` into 4 parts.
- For each part, it will extract clips where the keyword appears and save them in a folder named `<KILL_KEYWORD>_clips/partN/`.

## Notes
- For best results, use high-quality videos and set the keyword to match the on-screen text exactly as it appears.
- If you encounter errors with video reading, try re-encoding your video with ffmpeg.
- You can adjust the number of parts or OCR region in the script if needed.

---

For questions or improvements, please contact the script author.
