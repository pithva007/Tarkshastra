"""
Crowd Counter — YOLOv8 + ByteTrack + Density Estimation
Processes video and outputs live crowd count.

Run standalone: python counter.py --video path/to/video.mp4
Or imported by api.py for web interface.
"""

import cv2
import argparse
import json
import time
from pathlib import Path
from collections import defaultdict, deque
from ultralytics import YOLO
from density_estimator import DensityEstimator

MODEL_PATH = "yolov8m.pt"  # medium model — more accurate

DENSITY_LEVELS = {
    "LOW":      (0,   15,  "#22c55e"),
    "MODERATE": (15,  40,  "#f59e0b"),
    "HIGH":     (40,  80,  "#ef4444"),
    "CRITICAL": (80,  999, "#7c3aed"),
}


def get_density_level(count):
    for level, (low, high, color) in DENSITY_LEVELS.items():
        if low <= count < high:
            return {"level": level, "color": color}
    return {"level": "CRITICAL", "color": "#7c3aed"}


def get_cpi_from_count(count, capacity=100):
    return min(round(count / capacity, 3), 1.0)


def box_center(bbox):
    x1, y1, x2, y2 = bbox
    return ((x1+x2)//2, (y1+y2)//2)


def box_area(bbox):
    x1, y1, x2, y2 = bbox
    return (x2-x1) * (y2-y1)


def iou(box1, box2):
    """Intersection over Union between two boxes."""
    x1 = max(box1[0], box2[0])
    y1 = max(box1[1], box2[1])
    x2 = min(box1[2], box2[2])
    y2 = min(box1[3], box2[3])
    
    intersection = max(0, x2-x1) * max(0, y2-y1)
    if intersection == 0:
        return 0.0
    
    area1 = box_area(box1)
    area2 = box_area(box2)
    union = area1 + area2 - intersection
    return intersection / union if union > 0 else 0.0


def deduplicate_boxes(detections, iou_threshold=0.5):
    """Remove duplicate detections in same frame.
    If two boxes overlap > threshold, keep higher confidence."""
    if not detections:
        return detections
    
    # Sort by confidence descending
    detections = sorted(detections, key=lambda x: x["confidence"], reverse=True)
    kept = []
    
    for det in detections:
        duplicate = False
        for kept_det in kept:
            if iou(det["bbox"], kept_det["bbox"]) > iou_threshold:
                duplicate = True
                break
        if not duplicate:
            kept.append(det)
    
    return kept


class CrowdCounter:
    def __init__(self, model_path=MODEL_PATH,
                 conf_threshold=0.55,
                 stability_frames=3,
                 max_disappeared=15):
        """
        conf_threshold: min confidence to count a detection
        stability_frames: ID must appear N frames to be counted
                         (eliminates ghost detections)
        max_disappeared: frames before ID considered truly gone
        """
        print(f"[INIT] Loading {model_path}...")
        print("[INIT] First run downloads model (~50MB)...")
        self.model = YOLO(model_path)
        self.conf_threshold = conf_threshold
        self.stability_frames = stability_frames
        self.max_disappeared = max_disappeared
        self.density_estimator = DensityEstimator(calibration_factor=1.0)
        self.reset()
        print("[INIT] Ready")

    def reset(self):
        # IDs confirmed as real people (appeared 3+ frames)
        self.confirmed_ids = set()
        # Track consecutive frame count per ID
        self.id_frame_count = defaultdict(int)
        # Track last seen frame per ID
        self.id_last_seen = {}
        # IDs currently visible
        self.current_frame_ids = set()
        
        self.frame_count = 0
        self.total_frames = 0
        self.fps = 0
        self.processing = False
        self.results_history = []

    def process_frame(self, frame):
        self.frame_count += 1
        self.current_frame_ids = set()

        # Run YOLOv8 with ByteTrack
        results = self.model.track(
            frame,
            persist=True,
            tracker="bytetrack.yaml",
            classes=[0],                    # person only
            conf=self.conf_threshold,
            iou=0.45,
            verbose=False,
            imgsz=640                       # standard input size
        )

        raw_detections = []

        if (results[0].boxes is not None and
                results[0].boxes.id is not None):
            boxes = results[0].boxes
            for box in boxes:
                try:
                    pid = int(box.id[0])
                    conf = float(box.conf[0])
                    x1, y1, x2, y2 = map(int, box.xyxy[0])
                    
                    # Skip tiny boxes (likely noise)
                    # Minimum 40x80 pixels for a person
                    if (x2-x1) < 40 or (y2-y1) < 60:
                        continue
                    
                    raw_detections.append({
                        "id": pid,
                        "confidence": round(conf, 2),
                        "bbox": [x1, y1, x2, y2],
                        "center": box_center([x1, y1, x2, y2])
                    })
                except (IndexError, TypeError, ValueError):
                    continue

        # Remove duplicate boxes in same frame
        detections = deduplicate_boxes(raw_detections, iou_threshold=0.5)

        # Update tracking state
        seen_ids_this_frame = set()
        for det in detections:
            pid = det["id"]
            seen_ids_this_frame.add(pid)
            
            # Increment consecutive frame counter
            self.id_frame_count[pid] += 1
            self.id_last_seen[pid] = self.frame_count
            
            # Only count as real person after stability_frames
            if self.id_frame_count[pid] >= self.stability_frames:
                self.confirmed_ids.add(pid)
                self.current_frame_ids.add(pid)

        # Clean up IDs that disappeared too long
        # This prevents memory leak on long videos
        disappeared_ids = []
        for pid, last_seen in list(self.id_last_seen.items()):
            frames_gone = self.frame_count - last_seen
            if frames_gone > self.max_disappeared:
                disappeared_ids.append(pid)
        
        for pid in disappeared_ids:
            del self.id_last_seen[pid]
            # Note: do NOT remove from confirmed_ids
            # Once confirmed, always counted in total_unique

        # Current live count = confirmed IDs visible now
        live_count = len(self.current_frame_ids)
        total_unique = len(self.confirmed_ids)
        
        # Run density estimation
        estimation = self.density_estimator.estimate(
            frame=frame,
            yolo_live_count=live_count,
            yolo_boxes=detections
        )
        
        # Use estimated count instead of raw YOLO count
        estimated_live = estimation["estimated_count"]
        
        density = get_density_level(estimated_live)
        cpi = get_cpi_from_count(estimated_live)

        frame_result = {
            "frame": self.frame_count,
            "live_count": estimated_live,      # corrected count
            "yolo_raw_count": live_count,      # original YOLO
            "total_unique": total_unique,
            "density": density,
            "cpi": cpi,
            "boxes": detections,
            "estimation_details": estimation,
            "pending_ids": len([p for p, c in self.id_frame_count.items()
                               if c < self.stability_frames]),
            "timestamp": time.time()
        }

        self.results_history.append({
            "frame": self.frame_count,
            "live_count": estimated_live,
            "total_unique": total_unique,
            "cpi": cpi
        })

        return frame_result

    def draw_frame(self, frame, frame_result):
        annotated = frame.copy()
        live_count = frame_result["live_count"]
        density = frame_result["density"]
        cpi = frame_result["cpi"]

        # BGR colors per density
        color_map = {
            "LOW":      (34, 197, 94),
            "MODERATE": (36, 191, 251),
            "HIGH":     (68, 68, 239),
            "CRITICAL": (247, 85, 168),
        }
        box_color = color_map.get(density["level"], (255,255,255))

        for det in frame_result["boxes"]:
            x1, y1, x2, y2 = det["bbox"]
            pid = det["id"]
            conf = det["confidence"]
            
            # Check if this ID is confirmed
            is_confirmed = pid in self.confirmed_ids
            
            # Draw box — solid if confirmed, dashed if pending
            if is_confirmed:
                cv2.rectangle(annotated, (x1,y1), (x2,y2), box_color, 2)
                label = f"#{pid} {conf:.0%}"
                label_color = box_color
            else:
                # Pending — gray dashed box
                cv2.rectangle(annotated,
                            (x1,y1), (x2,y2),
                            (100,100,100), 1)
                label = f"?{pid}"
                label_color = (100,100,100)
            
            label_y = y1-8 if y1>20 else y1+20
            cv2.putText(annotated, label,
                       (x1, label_y),
                       cv2.FONT_HERSHEY_SIMPLEX,
                       0.45, label_color, 2)

        # Stats overlay
        overlay = annotated.copy()
        cv2.rectangle(overlay, (0,0), (280,150), (0,0,0), -1)
        cv2.addWeighted(overlay, 0.65, annotated, 0.35, 0, annotated)

        stats = [
            (f"LIVE: {live_count} people", (0,255,0)),
            (f"TOTAL UNIQUE: {frame_result['total_unique']}",
             (200,200,200)),
            (f"PENDING: {frame_result['pending_ids']}",
             (150,150,150)),
            (f"DENSITY: {density['level']}", (0,200,255)),
            (f"CPI: {cpi:.3f}", (255,200,0)),
            (f"FRAME: {self.frame_count}", (120,120,120)),
        ]
        for i, (text, color) in enumerate(stats):
            cv2.putText(annotated, text,
                       (8, 22 + i*22),
                       cv2.FONT_HERSHEY_SIMPLEX,
                       0.55, color, 2)

        # Add density overlay
        annotated = self.density_estimator.draw_density_overlay(
            annotated, frame_result["estimation_details"])

        return annotated

    def process_video(self, video_path, output_path=None,
                      show_window=False,
                      callback=None):
        self.reset()
        self.processing = True

        cap = cv2.VideoCapture(video_path)
        if not cap.isOpened():
            raise ValueError(f"Cannot open: {video_path}")

        self.total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        self.fps = cap.get(cv2.CAP_PROP_FPS) or 25
        width  = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))

        print(f"[VIDEO] {self.total_frames} frames | "
              f"{self.fps:.1f} FPS | {width}x{height}")

        writer = None
        if output_path:
            fourcc = cv2.VideoWriter_fourcc(*'mp4v')
            writer = cv2.VideoWriter(output_path, fourcc, self.fps, (width, height))

        start_time = time.time()

        try:
            while self.processing:
                ret, frame = cap.read()
                if not ret:
                    break

                frame_result = self.process_frame(frame)
                annotated = self.draw_frame(frame, frame_result)

                if writer:
                    writer.write(annotated)

                if show_window:
                    cv2.imshow("Crowd Counter", annotated)
                    if cv2.waitKey(1) & 0xFF == ord('q'):
                        break

                if callback:
                    callback(frame_result)

                if self.frame_count % 30 == 0:
                    pct = (self.frame_count / max(self.total_frames,1) * 100)
                    print(f"[{pct:.0f}%] Frame {self.frame_count}"
                          f" | Live:{frame_result['live_count']}"
                          f" | Unique:{frame_result['total_unique']}"
                          f" | Pending:{frame_result['pending_ids']}")

        finally:
            self.processing = False
            cap.release()
            if writer:
                writer.release()
            if show_window:
                cv2.destroyAllWindows()

        total_time = time.time() - start_time
        summary = {
            "video_path": video_path,
            "total_frames_processed": self.frame_count,
            "total_unique_people": len(self.confirmed_ids),
            "peak_live_count": max(
                (r["live_count"] for r in self.results_history), default=0),
            "average_live_count": round(
                sum(r["live_count"] for r in self.results_history) /
                max(len(self.results_history), 1), 1),
            "peak_cpi": max(
                (r["cpi"] for r in self.results_history), default=0.0),
            "processing_time_seconds": round(total_time, 1),
            "output_video": output_path,
            "history": self.results_history[-200:]
        }

        print(f"\n{'='*40}")
        print(f"Total unique (confirmed): {summary['total_unique_people']}")
        print(f"Peak live count: {summary['peak_live_count']}")
        print(f"Processing time: {summary['processing_time_seconds']}s")
        print(f"{'='*40}\n")

        return summary


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--video", required=True)
    parser.add_argument("--output", default=None)
    parser.add_argument("--show", action="store_true")
    parser.add_argument("--conf", type=float, default=0.55)
    parser.add_argument("--stability", type=int, default=3)
    args = parser.parse_args()

    counter = CrowdCounter(
        conf_threshold=args.conf,
        stability_frames=args.stability
    )
    summary = counter.process_video(
        video_path=args.video,
        output_path=args.output,
        show_window=args.show
    )

    out = Path(args.video).stem + "_summary.json"
    with open(out, "w") as f:
        json.dump(summary, f, indent=2)
    print(f"Summary saved: {out}")
