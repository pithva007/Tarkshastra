"""
FastAPI server for crowd counter web UI.
Runs on port 8001 (separate from main backend on 8000).
"""

import asyncio
import json
import os
import shutil
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, File, UploadFile, WebSocket
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, FileResponse
from fastapi.staticfiles import StaticFiles

from counter import CrowdCounter

app = FastAPI(title="Crowd Counter API", version="1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Serve static files
app.mount("/static", StaticFiles(directory="static"), name="static")

# Global counter instance
counter = CrowdCounter(
    model_path="yolov8m.pt",
    conf_threshold=0.60,    # was 0.55 — stricter
    stability_frames=5,     # was 3 — needs 5 frames to confirm
    max_disappeared=8       # was 15 — forget IDs faster
)

# Active WebSocket connections
ws_clients: list[WebSocket] = []

# Store latest frame result for polling
latest_result: dict = {}
processing_summary: dict = {}
is_processing: bool = False

UPLOAD_DIR = Path("uploads")
OUTPUT_DIR = Path("outputs")
UPLOAD_DIR.mkdir(exist_ok=True)
OUTPUT_DIR.mkdir(exist_ok=True)


async def broadcast(data: dict):
    """Send data to all connected WebSocket clients."""
    dead = []
    for ws in ws_clients:
        try:
            await ws.send_json(data)
        except Exception:
            dead.append(ws)
    for ws in dead:
        ws_clients.remove(ws)


@app.get("/", response_class=HTMLResponse)
async def home():
    """Serve the main UI."""
    html_path = Path("static/index.html")
    return HTMLResponse(content=html_path.read_text())


@app.post("/api/upload")
async def upload_video(file: UploadFile = File(...)):
    """Upload a video file for processing."""
    global is_processing

    if is_processing:
        return {"status": "error", "message": "Already processing a video. Wait."}

    # Validate file type
    allowed = [".mp4", ".avi", ".mov", ".mkv", ".webm"]
    suffix = Path(file.filename).suffix.lower()
    if suffix not in allowed:
        return {
            "status": "error",
            "message": f"File type {suffix} not supported. Use: {', '.join(allowed)}"
        }

    # Save uploaded file
    save_path = UPLOAD_DIR / f"input{suffix}"
    with open(save_path, "wb") as f:
        shutil.copyfileobj(file.file, f)

    file_size_mb = os.path.getsize(save_path) / 1024 / 1024

    return {
        "status": "uploaded",
        "filename": file.filename,
        "size_mb": round(file_size_mb, 1),
        "path": str(save_path),
        "message": "Video uploaded. Call /api/process to start."
    }


@app.post("/api/process")
async def start_processing(capacity: int = 100):
    """Start processing the uploaded video."""
    global is_processing, processing_summary, latest_result

    if is_processing:
        return {"status": "error", "message": "Already running"}

    # Find uploaded video
    video_path = None
    for ext in [".mp4", ".avi", ".mov", ".mkv", ".webm"]:
        candidate = UPLOAD_DIR / f"input{ext}"
        if candidate.exists():
            video_path = str(candidate)
            break

    if not video_path:
        return {"status": "error", "message": "No video uploaded. Upload first."}

    output_path = str(OUTPUT_DIR / "output.mp4")
    is_processing = True
    processing_summary = {}
    latest_result = {}
    counter.reset()

    # Process in background so API stays responsive
    async def run():
        global is_processing, processing_summary
        try:
            loop = asyncio.get_event_loop()

            def frame_callback(frame_result):
                """Called on each frame — broadcast to WS."""
                global latest_result
                latest_result = frame_result
                # Schedule broadcast
                asyncio.run_coroutine_threadsafe(
                    broadcast({"type": "frame_update", **frame_result}),
                    loop
                )

            # Run in thread pool (blocking operation)
            summary = await loop.run_in_executor(
                None,
                lambda: counter.process_video(
                    video_path=video_path,
                    output_path=output_path,
                    show_window=False,
                    callback=frame_callback
                )
            )

            processing_summary = summary
            await broadcast({"type": "processing_complete", **summary})

        except Exception as e:
            await broadcast({"type": "error", "message": str(e)})
        finally:
            is_processing = False

    asyncio.create_task(run())

    return {
        "status": "started",
        "video": video_path,
        "message": "Processing started. Connect to WebSocket for live updates."
    }


@app.get("/api/status")
async def get_status():
    """Get current processing status."""
    return {
        "is_processing": is_processing,
        "latest": latest_result,
        "summary": processing_summary,
        "frame_count": counter.frame_count,
        "total_frames": counter.total_frames,
        "progress_pct": round(
            counter.frame_count / max(counter.total_frames, 1) * 100, 1)
    }


@app.get("/api/summary")
async def get_summary():
    """Get final processing summary."""
    if is_processing:
        return {"status": "still_processing"}
    if not processing_summary:
        return {"status": "no_results_yet"}
    return processing_summary


@app.get("/api/download-output")
async def download_output():
    """Download annotated output video."""
    output = OUTPUT_DIR / "output.mp4"
    if not output.exists():
        return {"error": "No output video yet"}
    return FileResponse(
        path=str(output),
        media_type="video/mp4",
        filename="crowd_annotated.mp4"
    )


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """WebSocket for live frame-by-frame updates."""
    await websocket.accept()
    ws_clients.append(websocket)

    # Send current state immediately on connect
    await websocket.send_json({
        "type": "connected",
        "is_processing": is_processing,
        "latest": latest_result
    })

    try:
        while True:
            await asyncio.sleep(0.5)
            # Send status ping every 0.5s
            if is_processing:
                await websocket.send_json({
                    "type": "status",
                    "is_processing": is_processing,
                    "frame": counter.frame_count,
                    "total": counter.total_frames,
                    "progress": round(
                        counter.frame_count /
                        max(counter.total_frames, 1) * 100, 1)
                })
    except Exception:
        ws_clients.remove(websocket)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("api:app", host="0.0.0.0", port=8001, reload=True)
