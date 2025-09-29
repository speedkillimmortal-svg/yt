# Video Resolution Converter for Shorts/Reels/TikTok
# Requirements: ffmpeg-python
# Usage: Place your input clips in the 'input_clips' folder. Run this script to convert all videos to 1080x1920 (vertical, 9:16) for social media.

import os
import ffmpeg
from PIL import Image

# Target resolution for Shorts/Reels/TikTok
TARGET_WIDTH = 1080
TARGET_HEIGHT = 1920

# Input and output folders
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
INPUT_DIR = os.path.join(SCRIPT_DIR, 'input_clips')
OUTPUT_DIR = os.path.join(SCRIPT_DIR, 'output_clips')
os.makedirs(OUTPUT_DIR, exist_ok=True)

# Supported video extensions
VIDEO_EXTS = ['.mp4', '.mov', '.avi', '.mkv']

def is_video_file(filename):
    return any(filename.lower().endswith(ext) for ext in VIDEO_EXTS)

def convert_to_vertical(input_path, output_path):
    bottom_bar_height = 200  # pixels reserved for channel info
    video_height = TARGET_HEIGHT - bottom_bar_height
    # Place the icon at a fixed size (400x200) in the left bottom corner
    icon_path = os.path.join(SCRIPT_DIR, 'generic_icon.png')
    icon_width = 400
    icon_height = bottom_bar_height
    icon_x = 0
    icon_y = TARGET_HEIGHT - bottom_bar_height
    # Prepare main video stream
    stream = (
        ffmpeg
        .input(input_path)
        .filter('scale', -1, video_height)
        .filter('crop', f"if(gt(in_w,{TARGET_WIDTH}),{TARGET_WIDTH},in_w)", video_height, '(in_w-out_w)/2', 0)
        .filter('pad', TARGET_WIDTH, TARGET_HEIGHT, 0, 0, color='black')
    )
    stream = stream.overlay(
        ffmpeg.input(icon_path).filter('scale', icon_width, icon_height),
        x=icon_x,
        y=icon_y
    )
    # Overlay channel logo last (bottom right)
    logo_path = os.path.join(SCRIPT_DIR, 'channel_logo.jpg')
    stream = stream.overlay(
        ffmpeg.input(logo_path).filter('scale', 180, 180),
        x=f'{TARGET_WIDTH}-180-20',
        y=f'{TARGET_HEIGHT}-180-10'
    )
    stream = stream.output(
        output_path,
        vcodec='libx264',
        acodec='aac',
        strict='experimental',
        movflags='+faststart',
        pix_fmt='yuv420p',
        preset='fast'
    ).global_args('-nostdin', '-loglevel', 'error').overwrite_output()
    stream.run()

def main():
    for fname in os.listdir(INPUT_DIR):
        if is_video_file(fname):
            in_path = os.path.join(INPUT_DIR, fname)
            out_path = os.path.join(OUTPUT_DIR, fname)
            print(f'Converting {fname}...')
            convert_to_vertical(in_path, out_path)
            print(f'Saved: {out_path}')

if __name__ == '__main__':
    main()
