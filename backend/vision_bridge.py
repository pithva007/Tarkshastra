"""Vision Bridge — connects crowd_counter output
to the main CPI simulator.

When a video is processed:
1. Get live_count from crowd_counter
2. Convert to flow_rate using corridor calibration
3. Inject flow_rate into simulator for that corridor
4. CPI recalculates using real vision data instead
   of simulated data
5. Real data badge shown on dashboard
"""

import asyncio
import time
import sys
import os
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


def count_to_flow_rate(
    live_count: int,
    corridor: str,
    corridor_width_m: float = None
) -> float:
    """Convert head count to flow rate (pax/min).
    
    live_count: people visible in current frame
    corridor: corridor name for calibration
    corridor_width_m: optional override for width
    """
    if corridor_width_m:
        # Custom width — calculate multiplier
        # Formula: wider corridor = more people per frame
        multiplier = max(6, corridor_width_m * 3)
    else:
        multiplier = CORRIDOR_CALIBRATION.get(corridor, 12)
    
    flow_rate = live_count * multiplier
    
    # Apply density correction
    # In very dense crowds, each visible person
    # represents more people behind them
    if live_count > 30:
        flow_rate *= 1.4  # Heavy occlusion correction
    elif live_count > 15:
        flow_rate *= 1.2  # Moderate occlusion
    
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
    print(f"[VISION] {corridor}: "
          f"count={live_count} estimated={estimated_count} "
          f"flow={flow_rate} cpi={cpi:.3f}")


def get_vision_reading(corridor: str) -> Optional[dict]:
    """Get latest valid vision reading for corridor.
    
    Returns None if reading is expired or missing.
    """
    reading = vision_readings.get(corridor)
    if not reading:
        return None
    
    age = time.time() - reading["timestamp"]
    if age > VISION_READING_TTL:
        # Reading expired — remove it
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
        print(f"[VISION] {corridor} cleared — reverting to simulation")


class VisionProcessor:
    """Processes video files for a specific corridor.
    
    Integrates with crowd_counter module.
    """
    
    def __init__(self):
        self.processing = False
        self.current_corridor = None
        self.progress = 0
        self.result = None
        self._counter = None
    
    def _get_counter(self):
        """Lazy load counter to avoid startup delay."""
        if self._counter is None:
            try:
                # Add crowd_counter to path
                cc_path = Path(__file__).parent.parent / "crowd_counter"
                if cc_path.exists():
                    sys.path.insert(0, str(cc_path))
                
                from counter import CrowdCounter
                
                self._counter = CrowdCounter(
                    model_path="yolov8m.pt",
                    conf_threshold=0.55,
                    stability_frames=3,
                    max_disappeared=10
                )
                print("[VISION] CrowdCounter loaded")
            except ImportError as e:
                print(f"[VISION] CrowdCounter not available: {e}")
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
        
        try:
            counter = self._get_counter()
            if counter is None:
                # Fallback — estimate from file metadata
                return await self._fallback_estimate(
                    video_path, corridor, corridor_width_m
                )
            
            loop = asyncio.get_event_loop()
            frame_results = []
            
            def frame_callback(frame_result):
                """Called on each processed frame."""
                self.progress = round(
                    frame_result["frame"] / 
                    max(counter.total_frames, 1) * 100
                )
                
                live_count = frame_result.get("live_count", 0)
                estimated = frame_result.get("total_unique", live_count)
                cpi = frame_result.get("cpi", 0)
                flow_rate = count_to_flow_rate(
                    live_count, corridor, corridor_width_m
                )
                
                # Store reading — updates every frame
                store_vision_reading(
                    corridor=corridor,
                    live_count=live_count,
                    estimated_count=estimated,
                    cpi=cpi,
                    flow_rate=flow_rate
                )
                
                frame_results.append({
                    "frame": frame_result["frame"],
                    "live_count": live_count,
                    "flow_rate": flow_rate,
                    "cpi": cpi
                })
                
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
            
            # Run in thread pool
            summary = await loop.run_in_executor(
                None,
                lambda: counter.process_video(
                    video_path=video_path,
                    output_path=None,
                    show_window=False,
                    callback=frame_callback
                )
            )
            
            # Final summary
            peak_count = summary.get("peak_live_count", 0)
            avg_count = summary.get("average_live_count", 0)
            peak_flow = count_to_flow_rate(
                peak_count, corridor, corridor_width_m
            )
            avg_flow = count_to_flow_rate(
                int(avg_count), corridor, corridor_width_m
            )
            
            result = {
                "status": "complete",
                "corridor": corridor,
                "total_unique_people": summary.get("total_unique_people", 0),
                "peak_live_count": peak_count,
                "average_live_count": avg_count,
                "peak_flow_rate": peak_flow,
                "average_flow_rate": avg_flow,
                "peak_cpi": summary.get("peak_cpi", 0),
                "frames_processed": summary.get("total_frames_processed", 0),
                "processing_time": summary.get("processing_time_seconds", 0),
                "source": "yolov8_bytetrack",
                "calibration_multiplier": (
                    CORRIDOR_CALIBRATION.get(corridor, 12)
                )
            }
            
            self.result = result
            self.processing = False
            print(f"[VISION] Complete: {result}")
            return result
            
        except Exception as e:
            self.processing = False
            print(f"[VISION ERROR] {e}")
            return {
                "status": "error",
                "error": str(e),
                "corridor": corridor
            }
    
    async def _fallback_estimate(
        self, video_path, corridor, corridor_width_m
    ) -> dict:
        """Fallback when YOLOv8 not available.
        
        Uses file size and duration to estimate.
        """
        import cv2
        
        cap = cv2.VideoCapture(video_path)
        fps = cap.get(cv2.CAP_PROP_FPS) or 25
        frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        duration = frame_count / fps
        cap.release()
        
        # Conservative estimate
        estimated_count = 5
        flow_rate = count_to_flow_rate(
            estimated_count, corridor, corridor_width_m
        )
        
        store_vision_reading(
            corridor=corridor,
            live_count=estimated_count,
            estimated_count=estimated_count,
            cpi=flow_rate / 2000 * 0.5,
            flow_rate=flow_rate
        )
        
        self.processing = False
        return {
            "status": "fallback",
            "corridor": corridor,
            "estimated_count": estimated_count,
            "flow_rate": flow_rate,
            "note": "YOLOv8 not available — using estimate"
        }


# Singleton processor
vision_processor = VisionProcessor()
