import subprocess
import os

def merge_files(file_list, output_file):
    print("Merging files...")
    # Create the concatenation list file
    with open("files.txt", "w") as f:
        for filename in file_list:
            if os.path.exists(filename):
                f.write(f"file '{filename}'\n")
            else:
                print(f"Warning: {filename} not found! Skipping.")
    
    # Run FFmpeg to concatenate streams by copying (no re-encoding)
    cmd = [
        "ffmpeg", "-y",
        "-f", "concat",
        "-safe", "0",
        "-i", "files.txt",
        "-c", "copy",
        output_file
    ]
    
    try:
        subprocess.run(cmd, check=True)
        print(f"Successfully created {output_file}")
    except subprocess.CalledProcessError as e:
        print(f"Error during merging: {e}")
    finally:
        # Cleanup
        if os.path.exists("files.txt"):
            os.remove("files.txt")

def main():
    root_dir = "/Users/anshgarewal/Desktop/research/adding_intro_end"
    
    # Define files
    intro = "intro.webm"
    main_vid = "GOT_part_0.webm"  # Ghost of Tsushima main video
    end = "end.webm"
    output = "final_compiled_video.webm"
    
    # Ensure working directory
    os.chdir(root_dir)
    
    files_to_merge = [intro, main_vid, end]
    
    # Verify all files exist
    missing = [f for f in files_to_merge if not os.path.exists(f)]
    if missing:
        print(f"Cannot proceed. Missing files: {missing}")
        return

    merge_files(files_to_merge, output)

if __name__ == "__main__":
    main()
