import subprocess
import json
import sys

def get_video_color_info(video_path):
    cmd = [
        "ffprobe",
        "-v", "error",
        "-select_streams", "v:0",
        "-show_entries", "stream=color_space,color_transfer,color_primaries,pix_fmt,bits_per_raw_sample,profile,level",
        "-of", "json",
        video_path
    ]
    
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        data = json.loads(result.stdout)
        return data.get('streams', [{}])[0]
    except Exception as e:
        print(f"Error analyzing {video_path}: {str(e)}")
        return {}

def print_color_info(video_path):
    print(f"\nAnalyzing {video_path}:")
    print("-" * 50)
    
    info = get_video_color_info(video_path)
    
    properties = [
        ("Color Space", "color_space"),
        ("Color Transfer", "color_transfer"),
        ("Color Primaries", "color_primaries"),
        ("Pixel Format", "pix_fmt"),
        ("Bits per Raw Sample", "bits_per_raw_sample"),
        ("Profile", "profile"),
        ("Level", "level")
    ]
    
    for label, key in properties:
        value = info.get(key, "Not specified")
        print(f"{label:20}: {value}")

# Get frame sample color information
def get_frame_color_stats(video_path):
    cmd = [
        "ffmpeg",
        "-i", video_path,
        "-vf", "signalstats",
        "-vframes", "1",
        "-f", "null",
        "-"
    ]
    
    try:
        result = subprocess.run(cmd, capture_output=True, text=True)
        # Extract relevant color statistics from the output
        return result.stderr
    except Exception as e:
        print(f"Error getting frame stats for {video_path}: {str(e)}")
        return ""

if __name__ == "__main__":
    if len(sys.argv) != 3:
        print("Usage: python analyze_color_properties.py <speedkill_video> <immortal_video>")
        sys.exit(1)
        
    speedkill_path = sys.argv[1]
    immortal_path = sys.argv[2]
    
    print("\n=== Color Properties Analysis ===")
    print_color_info(speedkill_path)
    print_color_info(immortal_path)
    
    print("\n=== Frame Color Statistics ===")
    print("\nSpeedkill Video Frame Stats:")
    print(get_frame_color_stats(speedkill_path))
    
    print("\nImmortal Video Frame Stats:")
    print(get_frame_color_stats(immortal_path))