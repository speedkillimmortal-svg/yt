# Maximum Quality Optimizations - compile_kills_1.25x.py

## ✅ Applied Optimizations

Your `compile_kills_1.25x.py` script has been upgraded with **maximum quality settings** for 4K WebM (VP9) output.

---

## 🚀 Changes Made

### 1. **Encoder Settings (VP9 for YouTube 4K)**

**BEFORE:**
```python
"-c:v", "libvpx-vp9",
"-b:v", "20M",                # Fixed bitrate
"-crf", "31",                 # Standard quality
"-cpu-used", "2",             # Faster encoding
```

**AFTER:**
```python
"-c:v", "libvpx-vp9",
"-b:v", "0",                  # Constrained Quality (CRF controlled)
"-crf", "18",                 # Near-lossless quality
"-cpu-used", "1",             # High quality (slower)
```

**Benefit:** Near-lossless 4K quality with adaptive bitrate.

---

### 2. **Audio Improvements**

**BEFORE:**
```python
"-b:a", "192k",               # Standard audio
"volume=0.5" / "volume=0.5"   # 50/50 mix
```

**AFTER:**
```python
"-b:a", "320k",               # Max quality audio
"volume=0.7" / "volume=0.3"   # 70% Game / 30% BGM
```

**Benefit:** Clearer game audio, balanced BGM, higher fidelity sound.

---

### 3. **Sharpening Filter Added**

**NEW:**
```python
unsharp=luma_msize_x=5:luma_msize_y=5:luma_amount=1.0:...
```

**Benefit:** Enhanced detail and sharpness, crucial for 4K content.

---

## 📊 Quality Improvements

| Aspect | Before | After |
|--------|--------|-------|
| **Video Quality** | Good (CRF 31) | **Near-Lossless (CRF 18)** |
| **Bitrate Control** | Fixed 20M | **Adaptive (Constrained Quality)** |
| **Encoding Speed** | Fast (cpu-used 2) | **Slower (cpu-used 1)** |
| **Audio Quality** | 192k | **320k** |
| **Audio Mix** | 50/50 | **70/30 (Better Balance)** |
| **Sharpening** | None | **Unsharp Mask** |

---

## ⚡ Performance Note

- **Processing time:** Will be slower (VP9 `cpu-used 1` is intensive)
- **Quality improvement:** Significant for 4K uploads
- **File size:** Variable (depends on complexity), likely larger than before

---

## 🎬 Usage

Run as usual:
```bash
cd /Users/anshgarewal/Desktop/research/kill_compilation_individual_1.25x
python3 compile_kills_1.25x.py
```

Output will be a **high-quality 4K WebM** file ready for YouTube! 🚀
