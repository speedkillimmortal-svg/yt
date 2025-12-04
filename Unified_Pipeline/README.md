# Unified Pipeline - Kill Compilation + Auto Shorts 🚀

## 🎯 What Is This?

A **unified script** that generates **BOTH outputs** from a **single detection run**:

1. **Kill Compilation** (4K horizontal WebM with BGM)
2. **Auto Shorts** (Vertical 1080x1920 MP4 for YouTube/Instagram)

## ⚡ Performance Comparison

| Method | Detection Runs | Total Time | Outputs |
|--------|---------------|------------|---------|
| **Separate Scripts** | 2x | ~50 min | Both |
| **Unified Pipeline** | 1x | ~30 min | Both |

**Time Savings: ~40% faster!** ⚡

---

## 📋 Setup

### **Step 1: Copy Required Files**

```bash
cd Unified_Pipeline

# Copy template
cp ../Kill_Compilation_4K/enemy_downed_template.png .

# Copy assets (for shorts)
cp ../Auto_Shorts_Pipeline/generic_icon.png .
cp ../Auto_Shorts_Pipeline/channel_logo.jpg .

# Copy background music (separate folders for each output)
mkdir -p compilation_bgm shorts_bgm
cp ../Kill_Compilation_4K/background_musics/* compilation_bgm/
cp ../Auto_Shorts_Pipeline/background_musics/* shorts_bgm/
```

**Note:** The unified pipeline uses **two separate music folders**:
- `compilation_bgm/` - Music for kill compilation (4K horizontal)
- `shorts_bgm/` - Music for auto shorts (vertical)

### **Step 2: Add Input Video**

```bash
cp /path/to/your/gameplay.webm input.webm
```

---

## 🚀 Usage

### **Generate Both Outputs (Recommended)**

```bash
python3 unified_pipeline.py -i input.webm
```

This will create:
- `kill_compilation/final_with_bgm.webm` (4K horizontal)
- `shorts/*.mp4` (1080x1920 vertical)

### **Only Kill Compilation**

```bash
python3 unified_pipeline.py -i input.webm --skip-shorts
```

### **Only Auto Shorts**

```bash
python3 unified_pipeline.py -i input.webm --skip-compilation
```

### **Custom Template**

```bash
python3 unified_pipeline.py -i input.webm --template my_template.png
```

### **Adjust Detection Threshold**

```bash
python3 unified_pipeline.py -i input.webm --threshold 0.6
```

---

## 📊 Workflow

```
input.webm
    ↓
[Template Matching Detection] (5-8 min) ← RUNS ONCE!
    ↓
[Smart Clip Merging]
    ↓
[Extract Clips] (2 min) ← SHARED!
    ↓
    ├─→ BRANCH A: Kill Compilation
    │   ├─ Merge all clips
    │   ├─ Speed 1.25x + BGM
    │   └─ Output: final_with_bgm.webm (4K)
    │
    └─→ BRANCH B: Auto Shorts
        ├─ Merge into groups of 3
        ├─ Convert to vertical
        ├─ Add overlays + BGM
        └─ Output: shorts/*.mp4 (1080x1920)
```

---

## 📁 Output Structure

```
Unified_Pipeline/
├── unified_pipeline.py
├── input.webm
├── enemy_downed_template.png
├── generic_icon.png
├── channel_logo.jpg
├── compilation_bgm/          # Music for kill compilation
│   └── song1.mp3
├── shorts_bgm/                # Music for shorts
│   ├── song1.mp3
│   ├── song2.mp3
│   └── ...
├── kill_compilation/
│   ├── compilation_raw.webm
│   └── final_with_bgm.webm  ← 4K Kill Compilation
└── shorts/
    ├── merged_shorts_1_vertical.mp4  ← Vertical Shorts
    ├── merged_shorts_2_vertical.mp4
    └── ...
```

---

## ⏱️ Time Breakdown

### **For 1-hour gameplay with 30 kills:**

**Old Approach (Separate Scripts):**
```
Kill Compilation:
  - Detection: ~8 min
  - Processing: ~17 min
  - Total: ~25 min

Auto Shorts:
  - Detection: ~8 min (DUPLICATE!)
  - Processing: ~17 min
  - Total: ~25 min

TOTAL: ~50 minutes
```

**New Approach (Unified):**
```
Unified Pipeline:
  - Detection: ~8 min (ONCE!)
  - Extraction: ~2 min (SHARED!)
  - Kill Compilation: ~12 min
  - Auto Shorts: ~8 min
  
TOTAL: ~30 minutes ⚡
```

**Savings: ~20 minutes (40% faster!)**

---

## 🎯 Features

### **Kill Compilation Output:**
- ✅ 4K horizontal WebM
- ✅ VP9 codec (CRF 18 - near-lossless)
- ✅ 1.25x speed
- ✅ Background music mixed (70% game / 30% BGM)
- ✅ Opus audio 320kbps
- ✅ All kills included (no skipping)

### **Auto Shorts Output:**
- ✅ 1080x1920 vertical MP4
- ✅ H.264 codec (CRF 18 - near-lossless)
- ✅ 1.25x speed
- ✅ Channel logo overlay
- ✅ Generic icon overlay
- ✅ Background music mixed (70% game / 30% BGM)
- ✅ AAC audio 320kbps
- ✅ YouTube Shorts & Instagram Reels ready

---

## 🔧 Configuration

Edit these variables in the script if needed:

```python
PRE_SEC = 5                      # Seconds before kill
POST_SEC = 5                     # Seconds after kill
TEMPLATE_CHECK_INTERVAL = 0.5    # Check every 0.5s
MIN_KILL_SPACING = 2.0           # Min 2s between kills
MATCH_THRESHOLD = 0.7            # Template confidence
TARGET_WIDTH = 1080              # Shorts width
TARGET_HEIGHT = 1920             # Shorts height
```

---

## 💡 Why Use Unified Pipeline?

### **Advantages:**
1. ✅ **40% faster** - Detection runs once
2. ✅ **Saves disk space** - Shared extracted clips
3. ✅ **Consistent results** - Same kills in both outputs
4. ✅ **Simpler workflow** - One command, two outputs
5. ✅ **Same quality** - No compromises

### **When to Use Separate Scripts:**
- Different input videos for each output
- Only need one output type
- Testing/debugging individual pipelines

---

## 📊 Example Output

```
======================================================================
UNIFIED PIPELINE - KILL COMPILATION + AUTO SHORTS
======================================================================
Input: /path/to/input.webm
Template: enemy_downed_template.png
Match threshold: 0.7
======================================================================

=== DETECTING KILLS (Template Matching) ===
[TEMPLATE] Loaded: 733x162 pixels
[DETECT] input.webm | dur=3364.6s, fps=59.9
[FOUND] Kill at 10.50s (confidence: 0.85)
[FOUND] Kill at 25.00s (confidence: 0.82)
...
[DETECT] Found 30 kills

=== SMART CLIP MERGING ===
[SMART MERGE] 30 kills → 12 optimized clips
  Clip 1: 5.5s → 20.5s (duration: 15.0s)
  Clip 2: 20.0s → 30.0s (duration: 10.0s)
  ...

=== EXTRACTING CLIPS ===
[EXTRACT] extracted_clips/clip_001.webm  (5.50s → 20.50s)
[EXTRACT] extracted_clips/clip_002.webm  (20.00s → 30.00s)
...

======================================================================
BRANCH A: KILL COMPILATION
======================================================================
[MERGE] Merging clips using Concat Demuxer (INSTANT)...
[MERGED] → kill_compilation/compilation_raw.webm
[OPTIMIZED] Applying 1.25× speed + Sharpening + mixing BGM...
[BGM] Using: song1.mp3 (70% game / 30% BGM)
[ENCODING] |##############################| 100.0%  ETA:   0.0m  Elapsed:  12.3m
[ENCODING COMPLETE] → kill_compilation/final_with_bgm.webm

✅ Kill Compilation: kill_compilation/final_with_bgm.webm

======================================================================
BRANCH B: AUTO SHORTS
======================================================================
[INFO] Total merged shorts clips: 4
[CONVERT] merged_shorts_1.webm → merged_shorts_1_vertical.mp4
[CONVERT] merged_shorts_2.webm → merged_shorts_2_vertical.mp4
[CONVERT] merged_shorts_3.webm → merged_shorts_3_vertical.mp4
[CONVERT] merged_shorts_4.webm → merged_shorts_4_vertical.mp4

✅ Auto Shorts: shorts

=== CLEANUP ===
[DELETED] Temporary extracted clips

======================================================================
UNIFIED PIPELINE COMPLETE!
======================================================================
📊 Total kills detected: 30
📊 Total clips extracted: 12
✅ Kill Compilation: kill_compilation/final_with_bgm.webm
✅ Auto Shorts: shorts/*.mp4
======================================================================
```

---

## 🐛 Troubleshooting

### **"Template not found"**
```bash
cp ../Kill_Compilation_4K/enemy_downed_template.png .
```

### **"No kills detected"**
- Check template quality
- Lower threshold: `--threshold 0.6`
- Verify input video has kills

### **Missing overlays in shorts**
```bash
cp ../Auto_Shorts_Pipeline/generic_icon.png .
cp ../Auto_Shorts_Pipeline/channel_logo.jpg .
```

### **No background music**
```bash
cp -r ../Kill_Compilation_4K/background_musics .
```

---

## 📋 Requirements

- Python 3.6+
- FFmpeg
- OpenCV (`pip install opencv-python`)
- ffmpeg-python (`pip install ffmpeg-python`)

---

## 🎬 Next Steps

After the pipeline completes:

1. **Kill Compilation**: Upload `kill_compilation/final_with_bgm.webm` to YouTube
2. **Shorts**: Upload `shorts/*.mp4` to YouTube Shorts or Instagram Reels

---

**Enjoy 40% faster processing with the unified pipeline!** 🚀
