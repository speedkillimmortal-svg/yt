# Video Segment Extractor

Extract multiple segments from a video file **without quality loss** using FFmpeg stream copy.

## 📁 Folder Structure

```
Video_Segment_Extractor/
├── extract_segments.py    # Main extraction script
├── segments.txt           # Sample segments file
├── README.md             # This file
└── output/               # Extracted clips will be saved here
```

## 🚀 Quick Start

### Method 1: Using a Segments File

1. **Create a segments file** (e.g., `segments.txt`):
```
0:10-0:30
1:15-2:00
5:00-5:45
```

2. **Run the script**:
```bash
python3 extract_segments.py -i input.webm -s segments.txt
```

### Method 2: Inline Segments

```bash
python3 extract_segments.py -i input.webm --segments "0:10-0:30" "1:15-2:00" "5:00-5:45"
```

## 📖 Usage

### Basic Usage
```bash
python3 extract_segments.py -i <input_file> -s <segments_file>
```

### Advanced Options
```bash
python3 extract_segments.py -i input.webm -s segments.txt -o my_clips --prefix clip
```

**Options:**
- `-i, --input`: Input video file (required)
- `-s, --segments-file`: Text file with segments (one per line)
- `--segments`: Inline segments (alternative to file)
- `-o, --output-dir`: Output directory (default: `output`)
- `--prefix`: Output filename prefix (default: `segment`)

## 📝 Segments File Format

Create a text file with one segment per line in format: `START-END`

**Example (`segments.txt`):**
```
# Extract intro
0:00-0:15

# Extract first kill
0:45-1:05

# Extract second kill
2:30-2:50

# Extract outro
5:00-5:20
```

**Time Format:**
- `MM:SS` (e.g., `1:30` = 1 minute 30 seconds)
- `HH:MM:SS` (e.g., `1:15:30` = 1 hour 15 minutes 30 seconds)

**Notes:**
- Lines starting with `#` are comments (ignored)
- Empty lines are ignored
- End time must be after start time

## 🎯 Features

- ✅ **Lossless Extraction**: Uses FFmpeg stream copy (`-c copy`)
- ✅ **No Re-encoding**: Preserves original quality
- ✅ **Fast**: Just copies data, no processing
- ✅ **Batch Processing**: Extract multiple segments at once
- ✅ **Flexible Input**: File or inline segments
- ✅ **Auto-naming**: Segments numbered automatically

## 📊 Examples

### Example 1: Extract Highlights
```bash
# segments.txt
0:30-1:00
2:15-2:45
5:00-5:30

# Run
python3 extract_segments.py -i gameplay.webm -s segments.txt
```

**Output:**
```
output/segment_001.webm  (0:30-1:00)
output/segment_002.webm  (2:15-2:45)
output/segment_003.webm  (5:00-5:30)
```

### Example 2: Custom Output
```bash
python3 extract_segments.py -i input.webm --segments "0:10-0:30" -o highlights --prefix kill
```

**Output:**
```
highlights/kill_001.webm
```

### Example 3: Multiple Segments Inline
```bash
python3 extract_segments.py -i video.webm \
  --segments "0:00-0:15" "1:30-2:00" "3:45-4:15" \
  -o clips
```

## 🔍 Sample Output

```
======================================================================
VIDEO SEGMENT EXTRACTOR
======================================================================
Input: input.webm
Output directory: output
Segments to extract: 3
======================================================================

[EXTRACT] 00:10.00 → 00:30.00 (duration: 00:20.00)
[OUTPUT] output/segment_001.webm
[SUCCESS] Created output/segment_001.webm (45.32 MB)

[EXTRACT] 01:15.00 → 02:00.00 (duration: 00:45.00)
[OUTPUT] output/segment_002.webm
[SUCCESS] Created output/segment_002.webm (102.15 MB)

[EXTRACT] 05:00.00 → 05:45.00 (duration: 00:45.00)
[OUTPUT] output/segment_003.webm
[SUCCESS] Created output/segment_003.webm (98.76 MB)

======================================================================
SUMMARY
======================================================================
✅ Successful: 3
📁 Output directory: output
======================================================================
```

## ⚠️ Important Notes

1. **Quality**: No quality loss - uses stream copy
2. **Speed**: Very fast - no encoding needed
3. **Format**: Output format matches input format
4. **Precision**: Seeks to nearest keyframe (may be slightly off)

## 🆘 Troubleshooting

### "Input file not found"
- Check the file path is correct
- Use absolute path if needed

### "Invalid timestamp format"
- Use `MM:SS` or `HH:MM:SS` format
- Example: `1:30` or `0:01:30`

### "End time must be after start time"
- Make sure end > start
- Check you didn't swap them

### Segment slightly off
- FFmpeg seeks to nearest keyframe
- For frame-accurate cuts, re-encoding is needed (slower)

## 💡 Tips

1. **Find Timestamps**: Use a video player to note exact times
2. **Test First**: Extract one segment to verify timing
3. **Batch Extract**: Put all segments in a file for efficiency
4. **Keep Original**: Script doesn't modify input file

## 📋 Requirements

- Python 3.6+
- FFmpeg installed

**Install FFmpeg:**
```bash
# macOS
brew install ffmpeg

# Ubuntu/Debian
sudo apt install ffmpeg
```

## 🎬 Use Cases

- Extract highlights from gameplay
- Cut out specific scenes
- Create compilation clips
- Remove unwanted parts
- Batch extract multiple moments

---

**Enjoy fast, lossless video extraction!** 🚀
