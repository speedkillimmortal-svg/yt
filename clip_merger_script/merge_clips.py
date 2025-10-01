# Clip Merger Script (WEBM 4K lossless)
# Requirements: ffmpeg-python
# Place your input clips in the 'input_clips' folder. 
# The script will merge them in batches of 2, and if the total is odd, the last batch will have 3 clips.

import os
import ffmpeg

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
INPUT_DIR = os.path.join(SCRIPT_DIR, 'input_clips')
OUTPUT_DIR = os.path.join(SCRIPT_DIR, 'output_clips')
os.makedirs(OUTPUT_DIR, exist_ok=True)

# Supported video extensions (added .webm)
VIDEO_EXTS = ['.webm', '.mp4', '.mov', '.avi', '.mkv']

def is_video_file(filename):
    return any(filename.lower().endswith(ext) for ext in VIDEO_EXTS)

def merge_clips(clip_paths, output_path):
    # Create concat list file
    list_file = output_path + '_list.txt'
    with open(list_file, 'w') as f:
        for clip in clip_paths:
            f.write(f"file '{clip}'\n")  # simpler, works fine unless paths have single quotes

    (
        ffmpeg
        .input(list_file, format='concat', safe=0)
        .output(output_path, c='copy')  # lossless merge, no re-encode
        .global_args('-nostdin', '-loglevel', 'error')
        .overwrite_output()
        .run()
    )
    os.remove(list_file)

def main():
    files = sorted([f for f in os.listdir(INPUT_DIR) if is_video_file(f)])
    clip_paths = [os.path.join(INPUT_DIR, f) for f in files]
    batch_num = 1
    i = 0
    while i < len(clip_paths):
        # If last batch and odd number, merge 3
        if i + 3 == len(clip_paths):
            batch = clip_paths[i:i+3]
            i += 3
        else:
            batch = clip_paths[i:i+2]
            i += 2
        if batch:
            out_name = f'merged_batch_{batch_num}.webm'  # <-- keep webm
            out_path = os.path.join(OUTPUT_DIR, out_name)
            print(f'Merging: {batch} -> {out_name}')
            merge_clips(batch, out_path)
            batch_num += 1

if __name__ == '__main__':
    main()
