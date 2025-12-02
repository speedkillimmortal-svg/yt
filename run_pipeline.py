#!/usr/bin/env python3
"""
Master Pipeline Runner
----------------------
Automates the execution of:
1. Kill Compilation (4K Long Form)
2. Auto Shorts Pipeline (Vertical Shorts)

Usage:
    python3 run_pipeline.py

Requirements:
    - 'input.webm' must be present in this directory.
"""

import os
import shutil
import subprocess
import sys
import time

# Configuration
INPUT_FILE = "input.webm"

# Scripts to run
SCRIPTS = [
    {
        "name": "Auto Shorts Pipeline",
        "folder": "Auto_Shorts_Pipeline",
        "script": "full_vid_to_shorts_reels.py",
        "description": "Extracts kills, converts to vertical 9:16, outputs high-quality MP4.",
        "args": []  # This script hardcodes input.webm, no args needed
    },
    {
        "name": "Kill Compilation (4K)",
        "folder": "Kill_Compilation_4K",
        "script": "compile_kills_1.25x.py",
        "description": "Extracts kills, speeds up 1.25x, mixes audio, outputs 4K WebM.",
        "args": ["-i", INPUT_FILE]
    }
]

def main():
    root_dir = os.path.dirname(os.path.abspath(__file__))

    print(f"🚀 [START] Starting Master Pipeline\n")

    for step in SCRIPTS:
        folder_name = step["folder"]
        script_name = step["script"]
        task_name = step["name"]
        script_args = step["args"]
        
        work_dir = os.path.join(root_dir, folder_name)
        script_path = os.path.join(work_dir, script_name)

        print(f"===================================================")
        print(f"▶️  RUNNING: {task_name}")
        print(f"   📂 Folder: {folder_name}")
        print(f"   📜 Script: {script_name}")
        print(f"   ℹ️  Info:   {step['description']}")
        print(f"===================================================")

        # 3. Check if input file exists in target folder
        dest_input = os.path.join(work_dir, INPUT_FILE)
        if not os.path.exists(dest_input):
            print(f"   ❌ [ERROR] '{INPUT_FILE}' not found in {folder_name}")
            print(f"      Please copy '{INPUT_FILE}' to '{folder_name}/' manually.")
            continue

        # 4. Execute the script
        print(f"   [EXEC] Launching script...")
        start_time = time.time()
        
        try:
            # Construct command with specific arguments
            cmd = ["python3", script_name] + script_args
            
            # Run the script inside its own directory
            subprocess.run(
                cmd,
                cwd=work_dir,
                check=True
            )
            elapsed = time.time() - start_time
            print(f"\n   ✅ [SUCCESS] {task_name} completed in {elapsed/60:.1f} minutes.")
            
        except subprocess.CalledProcessError as e:
            print(f"\n   ❌ [FAILURE] Script failed with exit code {e.returncode}")
            # Optional: Stop pipeline on failure? 
            # user_input = input("   Continue to next step? (y/n): ")
            # if user_input.lower() != 'y':
            #     sys.exit(1)
        except Exception as e:
            print(f"\n   ❌ [ERROR] An unexpected error occurred: {e}")

        print("\n")

    print("🎉 [DONE] All pipeline steps completed!")

if __name__ == "__main__":
    main()
 