import os
import subprocess

def convert_videos(input_folder, output_folder):
    if not os.path.exists(output_folder):
        os.makedirs(output_folder)

    for file in os.listdir(input_folder):
        if file.lower().endswith(('.mp4', '.mov', '.mkv', '.avi', '.webm', '.flv')):
            input_path = os.path.join(input_folder, file)
            output_path = os.path.join(output_folder, os.path.splitext(file)[0] + ".mp4")

            # Auto-crop to 9:16 (center cut) for Instagram Reels
            crop_filter = "crop=in_h*9/16:in_h:(in_w-out_w)/2:0,scale=1080:1920"

            # Optimized ffmpeg command using Apple Silicon encoder
            command = [
                "ffmpeg",
                "-i", input_path,
                "-vf", crop_filter,
                "-c:v", "h264_videotoolbox",   # Hardware-accelerated H.264 encoder
                "-b:v", "6M",                  # Target ~6 Mbps
                "-maxrate", "8M",
                "-bufsize", "12M",
                "-c:a", "aac",                 # AAC audio
                "-b:a", "128k",
                "-movflags", "+faststart",     # Optimized for uploads
                output_path
            ]

            print(f"Converting (cropped 9:16): {file} → {output_path}")
            subprocess.run(command, check=True)

    print("✅ Conversion complete! Cropped Reels saved in:", output_folder)


if __name__ == "__main__":
    input_folder = "input_videos"     # Place raw videos here
    output_folder = "reels_ready"     # Converted Reels go here

    convert_videos(input_folder, output_folder)
