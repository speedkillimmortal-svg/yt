import os
import subprocess

def download_youtube_shorts():
    # Hardcoded YouTube channel Shorts URL
    channel_url = "https://www.youtube.com/@sk-x-im"  # replace with your channel link

    # Create a folder to store downloads
    download_folder = "youtube_shorts"
    if not os.path.exists(download_folder):
        os.makedirs(download_folder)

    # yt-dlp command to download Shorts
    # --match-filter filters for only Shorts (under 60s)
    # -o sets the output format
    command = [
        "yt-dlp",
        "--match-filter", "duration < 61",   # ensures it's Shorts
        "-o", os.path.join(download_folder, "%(title)s.%(ext)s"),
        "--yes-playlist",
        channel_url
    ]

    try:
        print("Downloading Shorts from:", channel_url)
        subprocess.run(command, check=True)
        print("✅ Download complete! Files saved in:", download_folder)
    except subprocess.CalledProcessError as e:
        print("❌ Error while downloading:", e)


if __name__ == "__main__":
    download_youtube_shorts()
