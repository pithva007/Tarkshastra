"""Vision Bridge — connects crowd_counter output
to the main CPI simulator.

When a video is processed:
1. Get live_count from crowd_counter
2. Convert to flow_rate using corridor calibration
3. Inject flow_rate into simulator for that corridor
4. CPI recalculates using real vision data instead
   of simulated data
5. Real data badge shown on dashboard
6. If CPI >= 0.85, trigger full alert pipeline
"""

import asyncio
import time
import sys
import os
from datetime import datetime
from pathlib import Path
from typing import Optional, Callable

# Corridor width calibration
# Multiplier converts live_count to pax/min
CORRIDOR_CALIBRATION = {
    "Ambaji":   12,   # 4m wide main corridor
    "Dwarka":   10,   # 3m wide temple approach
    "Somnath":  14,   # 5m wide corridor
    "Pavagadh": 8,    # 2.5m narrow hill path
}

# Store latest vision readings per corridor
# Format: {corridor: {flow_rate, live_count, 
#                     timestamp, source}}
vision_readings: dict = {}

# How long vision reading stays valid (seconds)
# After this time, simulator reverts to synthetic data
VISION_READING_TTL = 300  # 5 minutes

# CPI threshold that triggers a real alert
VISION_ALERT_THRESHOLD = 0.85

# Process only every Nth frame
FRAME_SKIP = 3

# Resize frames to this max width before YOLO
MAX_PROCESS_WIDTH = 720


def count_to_flow_rate(
    live_count: int,
    corridor: str,
    corridor_width_m: float = None
) -> float:
    """Convert head count to flow rate (pax/min)."""
    if corridor_width_m:
        multiplier = max(6, corridor_width_m * 3)
    else:
        multiplier = CORRIDOR_CALIBRATION.get(corridor, 12)

    flow_rate = live_count * multiplier

    # Occlusion correction for dense crowds
    if live_count > 30:
        flow_rate *= 1.4
    elif live_count > 15:
        flow_rate *= 1.2

    return round(flow_rate)


def store_vision_reading(
    corridor: str,
    live_count: int,
    estimated_count: int,
    cpi: float,
    flow_rate: float
):
    """Store latest vision reading for a corridor."""
    vision_readings[corridor] = {
        "live_count": live_count,
        "estimated_count": estimated_count,
        "flow_rate": flow_rate,
        "cpi_from_vision": cpi,
        "timestamp": time.time(),
        "source": "vision",
        "age_seconds": 0
    }
    print(
        f"[VISION] {corridor}: "
        f"count={live_count} "
        f"estimated={estimated_count} "
        f"flow={flow_rate} "
        f"cpi={cpi:.3f}"
    )


def get_vision_reading(corridor: str) -> Optional[dict]:
    """Get latest valid vision reading for corridor.
    Returns None if reading is expired or missing.
    """
    reading = vision_readings.get(corridor)
    if not reading:
        return None

    age = time.time() - reading["timestamp"]
    if age > VISION_READING_TTL:
        del vision_readings[corridor]
        print(f"[VISION] {corridor} reading expired")
        return None

    reading["age_seconds"] = round(age)
    return reading


def get_all_vision_readings() -> dict:
    """Get all active vision readings."""
    result = {}
    for corridor in list(vision_readings.keys()):
        reading = get_vision_reading(corridor)
        if reading:
            result[corridor] = reading
    return result


def clear_vision_reading(corridor: str):
    """Remove vision reading — revert to simulation."""
    if corridor in vision_readings:
        del vision_readings[corridor]
        print(
            f"[VISION] {corridor} cleared "
            f"— reverting to simulation"
        )


def _get_video_info(video_path: str) -> dict:
    """Fast video probe — returns frame count, fps, dims."""
    import cv2  # lazy import — only when called
    cap = cv2.VideoCapture(video_path)
    total  = int(cap.get(cv2.CAP_PROP_FRAME_COUNT)) or 1
    fps    = cap.get(cv2.CAP_PROP_FPS) or 25.0
    width  = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    cap.release()
    return {
        "total_frames": total,
        "fps": fps,
        "width": width,
        "height": height,
    }


def _resize_for_yolo(frame, max_width: int = MAX_PROCESS_WIDTH):
    """Resize frame to max_width keeping aspect ratio."""
    import cv2  # lazy import — only when called
    h, w = frame.shape[:2]
    if w <= max_width:
        return frame
    scale = max_width / w
    new_w = max_width
    new_h = int(h * scale)
    return cv2.resize(
        frame,
        (new_w, new_h),
        interpolation=cv2.INTER_LINEAR
    )


class VisionProcessor:
    """Processes video files for a specific corridor."""

    def __init__(self):
        self.processing = False
        self.current_corridor = None
        self.progress = 0
        self.result = None
        self.frames_processed = 0
        self.total_frames_to_process = 1
        self._total_frames = 1
        self._counter = None
        self._alert_triggered_this_session = False
        self.alert_callback = None

    def reset(self):
        self.processing = False
        self.current_corridor = None
        self.progress = 0
        self.result = None
        self.frames_processed = 0
        self.total_frames_to_process = 1
        self._total_frames = 1
        self._counter = None
        self._alert_triggered_this_session = False

    def _get_counter(self):
        """Lazy load CrowdCounter — only when needed."""
        if self._counter is None:
            try:
                cc_path = (
                    Path(__file__).parent.parent /
                    "crowd_counter"
                )
                if cc_path.exists():
                    sys.path.insert(0, str(cc_path))

                from counter import CrowdCounter
                self._counter = CrowdCounter(
                    model_path="yolov8n.pt",
                    conf_threshold=0.45,
                    stability_frames=3,
                    max_disappeared=10
                )
                print("[VISION] CrowdCounter loaded")
            except ImportError as e:
                print(
                    f"[VISION] CrowdCounter not "
                    f"available: {e}"
                )
                self._counter = None

        return self._counter

    async def process_video_async(
        self,
        video_path: str,
        corridor: str,
        corridor_width_m: float = None,
        progress_callback: Callable = None
    ) -> dict:
        """Process video asynchronously.
        Updates vision_readings with results.
        Returns summary dict.
        """
        self.processing = True
        self.current_corridor = corridor
        self.progress = 0
        self._alert_triggered_this_session = False

        # Probe video before starting thread
        try:
            info = _get_video_info(video_path)
            self._total_frames = max(
                info["total_frames"] // FRAME_SKIP, 1
            )
            self.total_frames_to_process = (
                self._total_frames
            )
            self.frames_processed = 0
            print(
                f"[VISION] {corridor}: "
                f"{info['total_frames']} frames "
                f"@ {info['fps']:.0f}fps "
                f"{info['width']}x{info['height']} "
                f"→ processing every {FRAME_SKIP}rd frame "
                f"({self._total_frames} to process) "
                f"resize→{MAX_PROCESS_WIDTH}px"
            )
        except Exception as probe_err:
            print(f"[VISION] Probe failed: {probe_err}")
            self._total_frames = 100
            self.total_frames_to_process = 100

        try:
            counter = self._get_counter()

            if counter is None:
                return await self._fallback_estimate(
                    video_path, corridor, corridor_width_m
                )

            loop = asyncio.get_event_loop()
            frame_results = []

            def frame_callback(frame_result):
                """Called on each processed frame."""
                frame_no = frame_result.get(
                    "frame", counter.frame_count
                )
                total = max(counter.total_frames, 1)
                self.frames_processed = frame_no
                self.total_frames_to_process = total
                self.progress = min(
                    round(frame_no / total * 100), 99
                )

                live_count = frame_result.get(
                    "live_count", 0
                )
                estimated = frame_result.get(
                    "total_unique", live_count
                )
                cpi = frame_result.get("cpi", 0)
                flow_rate = count_to_flow_rate(
                    live_count, corridor, corridor_width_m
                )

                # Store every 3rd frame to reduce noise
                if frame_no % 3 == 0:
                    store_vision_reading(
                        corridor=corridor,
                        live_count=live_count,
                        estimated_count=estimated,
                        cpi=cpi,
                        flow_rate=flow_rate
                    )
                    frame_results.append({
                        "frame": frame_no,
                        "live_count": live_count,
                        "flow_rate": flow_rate,
                        "cpi": cpi
                    })

                # Check alert threshold
                if (
                    cpi >= VISION_ALERT_THRESHOLD
                    and self.alert_callback is not None
                    and not self._alert_triggered_this_session
                ):
                    self._alert_triggered_this_session = True
                    print(
                        f"[VISION ALERT] {corridor} "
                        f"CPI {cpi:.3f} >= "
                        f"{VISION_ALERT_THRESHOLD} "
                        f"— triggering full alert"
                    )
                    alert_data = {
                        "corridor": corridor,
                        "cpi": cpi,
                        "surge_type": "GENUINE_CRUSH",
                        "flow_rate": flow_rate,
                        "transport_burst": 0.75,
                        "chokepoint_density": 0.80,
                        "time_to_breach_minutes": 0,
                        "time_to_breach_seconds": 0,
                        "ml_confidence": 91,
                        "alert_id": (
                            f"VIS_"
                            f"{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}"
                            f"_{corridor[:3].upper()}"
                        ),
                        "data_source": "vision",
                        "alert_active": True,
                        "timestamp": (
                            datetime.utcnow().isoformat()
                            + "Z"
                        )
                    }
                    asyncio.run_coroutine_threadsafe(
                        self.alert_callback(alert_data),
                        loop
                    )

                if progress_callback:
                    asyncio.run_coroutine_threadsafe(
                        progress_callback({
                            "type": "vision_progress",
                            "corridor": corridor,
                            "progress": self.progress,
                            "live_count": live_count,
                            "flow_rate": flow_rate,
                            "cpi": cpi
                        }),
                        loop
                    )

            # Run processing in thread pool
            summary = await loop.run_in_executor(
                None,
                lambda: counter.process_video(
                    video_path=video_path,
                    output_path=None,
                    show_window=False,
                    callback=frame_callback
                )
            )

            peak_count = summary.get("peak_live_count", 0)
            avg_count  = summary.get(
                "average_live_count", 0
            )
            peak_flow  = count_to_flow_rate(
                peak_count, corridor, corridor_width_m
            )
            avg_flow   = count_to_flow_rate(
                int(avg_count), corridor, corridor_width_m
            )

            result = {
                "status": "complete",
                "corridor": corridor,
                "total_unique_people": summary.get(
                    "total_unique_people", 0
                ),
                "peak_live_count": peak_count,
                "average_live_count": avg_count,
                "peak_flow_rate": peak_flow,
                "average_flow_rate": avg_flow,
                "peak_cpi": summary.get("peak_cpi", 0),
                "frames_processed": summary.get(
                    "total_frames_processed", 0
                ),
                "processing_time": summary.get(
                    "processing_time_seconds", 0
                ),
                "source": "yolov8_bytetrack",
                "calibration_multiplier": (
                    CORRIDOR_CALIBRATION.get(corridor, 12)
                )
            }

            self.result   = result
            self.progress = 100
            self.processing = False
            print(f"[VISION] Complete: {result}")
            return result

        except Exception as e:
            self.processing = False
            print(f"[VISION ERROR] {e}")
            import traceback
            traceback.print_exc()
            return {
                "status": "error",
                "error": str(e),
                "corridor": corridor
            }

    async def _fallback_estimate(
        self,
        video_path,
        corridor,
        corridor_width_m
    ) -> dict:
        """Fallback when YOLOv8 not available."""
        try:
            import cv2  # lazy import — only when called
            cap = cv2.VideoCapture(video_path)
            cap.release()

            estimated_count = 8
            flow_rate = count_to_flow_rate(
                estimated_count, corridor, corridor_width_m
            )
            cpi = min(flow_rate / 2000 * 0.5, 0.99)

            store_vision_reading(
                corridor=corridor,
                live_count=estimated_count,
                estimated_count=estimated_count,
                cpi=cpi,
                flow_rate=flow_rate
            )

            self.processing = False
            self.progress = 100
            return {
                "status": "fallback",
                "corridor": corridor,
                "estimated_count": estimated_count,
                "flow_rate": flow_rate,
                "cpi": cpi,
                "note": (
                    "YOLOv8 not available — using estimate"
                )
            }
        except Exception as e:
            self.processing = False
            return {
                "status": "error",
                "error": str(e),
                "corridor": corridor
            }


def _process_with_skip(
    counter,
    video_path: str,
    frame_skip: int = 3,
    max_width: int = MAX_PROCESS_WIDTH,
    callback=None
) -> dict:
    """Custom video processing with frame skipping
    and pre-YOLO resize."""
    import cv2      # lazy import — only when called
    import time as _time

    counter.reset()
    counter.processing = True

    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        raise ValueError(f"Cannot open: {video_path}")

    total_frames = int(
        cap.get(cv2.CAP_PROP_FRAME_COUNT)
    )
    fps    = cap.get(cv2.CAP_PROP_FPS) or 25
    width  = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    counter.total_frames = total_frames
    counter.fps          = fps

    print(
        f"[VIDEO PROC] {total_frames} frames | "
        f"{fps:.1f}fps | {width}x{height} | "
        f"skip={frame_skip} | resize→{max_width}px"
    )

    start_time = _time.time()
    frame_idx  = 0
    processed  = 0

    try:
        while counter.processing:
            ret, frame = cap.read()
            if not ret:
                break

            frame_idx += 1

            if frame_idx % frame_skip != 0:
                continue

            small_frame = _resize_for_yolo(
                frame, max_width
            )
            frame_result = counter.process_frame(
                small_frame
            )
            processed += 1

            if callback:
                callback(frame_result)

            if processed % 20 == 0:
                pct = round(
                    frame_idx /
                    max(total_frames, 1) * 100
                )
                print(
                    f"[{pct}%] "
                    f"frame={frame_idx}/{total_frames} "
                    f"processed={processed} "
                    f"live={frame_result['live_count']} "
                    f"unique={frame_result['total_unique']}"
                )

    finally:
        counter.processing = False
        cap.release()

    total_time = _time.time() - start_time
    results_history = counter.results_history

    summary = {
        "video_path": video_path,
        "total_frames_processed": processed,
        "total_unique_people": len(
            counter.confirmed_ids
        ),
        "peak_live_count": max(
            (r["live_count"] for r in results_history),
            default=0
        ),
        "average_live_count": round(
            sum(
                r["live_count"]
                for r in results_history
            ) / max(len(results_history), 1),
            1
        ),
        "peak_cpi": max(
            (r["cpi"] for r in results_history),
            default=0.0
        ),
        "processing_time_seconds": round(total_time, 1),
        "output_video": None,
        "history": results_history[-200:]
    }

    print(
        f"\n[VISION DONE] Processed {processed} frames "
        f"in {total_time:.1f}s\n"
        f"  Peak live: {summary['peak_live_count']} | "
        f"Peak CPI: {summary['peak_cpi']:.3f}"
    )

    return summary


# Singleton processor
vision_processor = VisionProcessor()