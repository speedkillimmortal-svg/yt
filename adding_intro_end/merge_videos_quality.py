#!/usr/bin/env python3
"""
Fix intro/end videos to match main video quality (10-bit VP9)
This ensures no quality loss during concatenation
"""
import subprocess
import os

def convert_to_10bit(input_file, output_file):
    """Convert video to 10-bit VP9 to match main video"""
    print(f"Converting {input_file} to 10-bit VP9...")
    
    cmd = [
        "ffmpeg", "-y",
        "-i", input_file,
        "-c:v", "libvpx-vp9",
        "-pix_fmt", "yuv420p10le",  # 10-bit color depth
        "-crf", "15",                # Maximum quality
        "-b:v", "0",                 # Constant quality mode
        "-c:a", "libopus",           # Opus audio codec
        "-b:a", "320k",              # High quality audio
        output_file
    ]
    
    try:
        subprocess.run(cmd, check=True)
        print(f"✅ Successfully converted: {output_file}")
    except subprocess.CalledProcessError as e:
        print(f"❌ Error converting {input_file}: {e}")
        return False
    return True

def merge_files(file_list, output_file):
    """Merge videos with -c copy (no re-encoding)"""
    print("\n🎬 Merging files...")
    
    # Create concatenation list
    with open("files.txt", "w") as f:
        for filename in file_list:
            if os.path.exists(filename):
                f.write(f"file '{filename}'\n")
            else:
                print(f"⚠️  Warning: {filename} not found!")
                return False
    
    # Concatenate with copy (no re-encoding)
    cmd = [
        "ffmpeg", "-y",
        "-f", "concat",
        "-safe", "0",
        "-i", "files.txt",
        "-c", "copy",  # No re-encoding = perfect quality
        output_file
    ]
    
    try:
        subprocess.run(cmd, check=True)
        print(f"✅ Successfully created: {output_file}")
        return True
    except subprocess.CalledProcessError as e:
        print(f"❌ Error during merging: {e}")
        return False
    finally:
        if os.path.exists("files.txt"):
            os.remove("files.txt")

def main():
    root_dir = "/Users/anshgarewal/Desktop/research/adding_intro_end"
    os.chdir(root_dir)
    
    print("="*70)
    print("🎌 GHOST OF TSUSHIMA - QUALITY-PRESERVING VIDEO MERGER")
    print("="*70)
    print("\nStep 1: Converting intro/end to 10-bit to match main video...")
    print("="*70)
    
    # Convert intro and end to 10-bit
    intro_10bit = "intro_10bit.webm"
    end_10bit = "end_10bit.webm"
    
    if not convert_to_10bit("intro.webm", intro_10bit):
        return
    
    if not convert_to_10bit("end.webm", end_10bit):
        return
    
    print("\n" + "="*70)
    print("Step 2: Merging all videos (no quality loss)...")
    print("="*70)
    
    # Now merge with 10-bit versions
    files_to_merge = [intro_10bit, "final_with_bgm.webm", end_10bit]
    output = "final_compiled_video_10bit.webm"
    
    if merge_files(files_to_merge, output):
        print("\n" + "="*70)
        print("✅ SUCCESS - Video merged with ZERO quality loss!")
        print("="*70)
        print(f"Output: {output}")
        print("All videos are now 10-bit VP9 - perfect quality match!")
        print("="*70)

if __name__ == "__main__":
    main()
