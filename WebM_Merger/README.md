# WebM Video Merger

Merge multiple WebM videos **without quality loss** using FFmpeg's concat demuxer.

## 📁 Folder Structure

```
WebM_Merger/
├── merge_webm.py          # Main merge script
├── input/                 # Place your video parts here
│   ├── part1.webm
│   ├── part2.webm
│   ├── part3.webm
│   └── ...
└── merged_output.webm     # Output will be created here
```

## 🚀 Quick Start

### 1. Add Your Videos

Place your WebM video parts in the `input/` folder with naming:
- `part1.webm`
- `part2.webm`
- `part3.webm`
- etc.

### 2. Run the Script

Simply run:
```bash
python3 merge_webm.py
```

The script will:
- ✅ Auto-detect all `part*.webm` files in the `input/` folder
- ✅ Sort them numerically (part1, part2, part3...)
- ✅ Merge them **losslessly** (no quality loss!)
- ✅ Output to `merged_output.webm`

## 📖 Usage Options

### Auto Mode (Default)
Automatically merges all `part*.webm` files from `input/` folder:
```bash
python3 merge_webm.py
```

### Custom Output Name
```bash
python3 merge_webm.py -o my_video.webm
```

### Custom Input Directory
```bash
python3 merge_webm.py --input-dir /path/to/videos
```

### Manual File Selection
```bash
python3 merge_webm.py video1.webm video2.webm video3.webm -o output.webm
```

### Force Re-encoding (High Quality)
If videos have different codecs/formats:
```bash
python3 merge_webm.py --reencode
```

## 🎯 Key Features

- **🔥 Lossless Merging**: Uses stream copy mode - no re-encoding, no quality loss
- **⚡ Fast**: Just copies video streams, no processing needed
- **🤖 Auto-Detection**: Automatically finds and sorts part*.webm files
- **✅ Compatibility Check**: Verifies videos can be merged losslessly
- **🎨 High-Quality Fallback**: If re-encoding needed, uses VP9 CRF 15 (very high quality)

## 📋 Requirements

- **FFmpeg** must be installed on your system

### Install FFmpeg:

**macOS:**
```bash
brew install ffmpeg
```

**Ubuntu/Debian:**
```bash
sudo apt install ffmpeg
```

**Windows:**
Download from [ffmpeg.org](https://ffmpeg.org/download.html)

## 💡 How It Works

1. **Lossless Mode** (default):
   - Uses FFmpeg's concat demuxer
   - Copies video/audio streams directly (`-c copy`)
   - No re-encoding = **zero quality loss**
   - Very fast!

2. **Re-encode Mode** (when needed):
   - VP9 codec with CRF 15 (very high quality)
   - Opus audio at 192kbps
   - Row-based multithreading for speed

## 🔍 Example Output

```
🔍 Scanning 'input' for part*.webm files...

📋 Input files:
  1. part1.webm (245.32 MB)
  2. part2.webm (198.76 MB)
  3. part3.webm (312.45 MB)

📊 Total input size: 756.53 MB

🔍 Checking video compatibility...
✓ Reference video: part1.webm
✓ Checked: part2.webm
✓ Checked: part3.webm
✓ All videos appear compatible for lossless merging

🎬 Merging 3 videos...
📤 Output: merged_output.webm

✅ Success! Merged video saved to: merged_output.webm
📊 Output file size: 756.48 MB
```

## ⚠️ Important Notes

- All input videos should have the **same codec, resolution, and frame rate** for lossless merging
- If videos differ, use `--reencode` flag for high-quality re-encoding
- File naming must be `part1.webm`, `part2.webm`, etc. (case-insensitive)
- Numbers can be any length: `part001.webm`, `part002.webm` also work

## 🆘 Troubleshooting

**"No part*.webm files found"**
- Make sure files are named `part1.webm`, `part2.webm`, etc.
- Check they're in the `input/` folder
- File extension must be `.webm`

**"FFmpeg is not installed"**
- Install FFmpeg using instructions above
- Verify with: `ffmpeg -version`

**Videos won't merge losslessly**
- Videos may have different codecs/settings
- Use `--reencode` flag for high-quality re-encoding

## 📝 License

Free to use and modify!
