# Crowd Counter — Vision Module

Standalone computer vision module using YOLOv8 + ByteTrack.  
Runs on port **8001** — separate from main backend (port 8000).

---

## Setup

```bash
cd crowd_counter
pip install -r requirements.txt
```

---

## Run Web UI

```bash
python api.py
```

Then open: **http://localhost:8001**

---

## Run CLI (no browser)

```bash
# Basic
python counter.py --video path/to/video.mp4

# Save annotated output video
python counter.py --video video.mp4 --output annotated.mp4

# Show live window (local machine only)
python counter.py --video video.mp4 --show
```

---

## Outputs

- Live head count per frame
- Total unique people in video (no double counting via ByteTrack IDs)
- CPI score (0.0 = safe, 1.0 = crush capacity)
- Annotated output video with bounding boxes + ID labels
- JSON summary file (`<videoname>_summary.json`)

---

## Density Levels

| Level    | Count     | Color  |
|----------|-----------|--------|
| LOW      | 0–19      | Green  |
| MODERATE | 20–49     | Amber  |
| HIGH     | 50–99     | Red    |
| CRITICAL | 100+      | Purple |

---

## Integration with Main System

Send CPI output from crowd_counter to the main backend:

```bash
POST http://localhost:8000/api/sensor-input
{
  "corridor": "Ambaji",
  "source": "cctv_vision",
  "flow_rate": <live_count * 10>,
  "timestamp": "..."
}
```

---

## Notes

- YOLOv8n model (~6MB) downloads automatically on first run
- ByteTrack tracker is bundled with `ultralytics` — no extra install needed
- Processing is CPU-compatible; GPU (CUDA/MPS) used automatically if available
