# Video Resolution Converter for Shorts/Reels/TikTok (WebM / 4K Optimized)
# Requirements: ffmpeg-python, pillow
# Usage: Place your input clips in the 'input_clips' folder. Run this script to convert all videos
# into 1080x1920 (vertical, 9:16) for social media. Outputs in .webm using VP9 + Opus.

import os
import ffmpeg
import random

# Target resolution for Shorts/Reels/TikTok
TARGET_WIDTH = 1080
TARGET_HEIGHT = 1920

# Input and output folders
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
INPUT_DIR = os.path.join(SCRIPT_DIR, 'input_clips')
OUTPUT_DIR = os.path.join(SCRIPT_DIR, 'output_clips')
os.makedirs(OUTPUT_DIR, exist_ok=True)

# Supported video extensions
VIDEO_EXTS = ['.mp4', '.mov', '.avi', '.mkv', '.webm']
BACKGROUND_MUSIC_DIR = os.path.join(SCRIPT_DIR, 'background_musics')

def is_video_file(filename):
    return any(filename.lower().endswith(ext) for ext in VIDEO_EXTS)

def pick_random_music():
    if not os.path.exists(BACKGROUND_MUSIC_DIR):
        return None
    music_files = [f for f in os.listdir(BACKGROUND_MUSIC_DIR) if f.lower().endswith(('.mp3', '.wav', '.aac', '.m4a'))]
    if not music_files:
        return None
    return os.path.join(BACKGROUND_MUSIC_DIR, random.choice(music_files))

def convert_to_vertical_webm(input_path, output_path):
    bottom_bar_height = 200  # pixels reserved for channel info
    video_height = TARGET_HEIGHT - bottom_bar_height

    icon_path = os.path.join(SCRIPT_DIR, 'generic_icon.png')
    logo_path = os.path.join(SCRIPT_DIR, 'channel_logo.jpg')
    music_path = pick_random_music()

    # Scale, crop, and pad video to fit vertical format
    video = (
        ffmpeg
        .input(input_path)
        .filter('scale', -1, video_height)  # scale keeping aspect ratio
        .filter('crop',
                f"if(gt(in_w,{TARGET_WIDTH}),{TARGET_WIDTH},in_w)",  # crop if wider
                video_height,
                '(in_w-out_w)/2',
                0)
        .filter('pad', TARGET_WIDTH, TARGET_HEIGHT, 0, 0, color='black')
    )

    # Overlay bottom icon
    if os.path.exists(icon_path):
        video = video.overlay(
            ffmpeg.input(icon_path).filter('scale', 300, bottom_bar_height),
            x=0,
            y=TARGET_HEIGHT - bottom_bar_height
        )

    # Overlay logo (bottom-right)
    if os.path.exists(logo_path):
        video = video.overlay(
            ffmpeg.input(logo_path).filter('scale', 180, 180),
            x=f'{TARGET_WIDTH}-180-20',
            y=f'{TARGET_HEIGHT}-180-10'
        )

    # VP9 + Opus settings (optimized for quality + speed)
    vp9_settings = dict(
        vcodec='libvpx-vp9',
        acodec='libopus',
        crf=32,                               # Quality control (lower=better, 30–36 good for web)
        **{"b:v": "0"},                       # Required syntax for ffmpeg-python
        audio_bitrate='128k',
        **{"deadline": "realtime", "cpu-used": "4"},  # VP9 private options (speed boost)
        pix_fmt='yuv420p'
    )

    # If music exists, replace audio
    if music_path:
        music_input = ffmpeg.input(music_path, stream_loop=-1)
        out = (
            ffmpeg
            .output(
                video,
                music_input.audio,
                output_path,
                shortest=None,
                **vp9_settings
            )
            .global_args('-nostdin', '-loglevel', 'error')
            .overwrite_output()
        )
    else:
        out = (
            ffmpeg
            .output(
                video,
                output_path,
                **vp9_settings
            )
            .global_args('-nostdin', '-loglevel', 'error')
            .overwrite_output()
        )

    out.run()

def main():
    for fname in os.listdir(INPUT_DIR):
        if is_video_file(fname):
            in_path = os.path.join(INPUT_DIR, fname)
            base, _ = os.path.splitext(fname)
            out_path = os.path.join(OUTPUT_DIR, f"{base}_vertical4k.webm")
            print(f'Converting {fname} → {out_path}')
            convert_to_vertical_webm(in_path, out_path)
            print(f'Saved: {out_path}')

if __name__ == '__main__':
    main()
