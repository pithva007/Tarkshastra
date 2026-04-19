"""
Density-based crowd estimation.
Works for occluded crowds where YOLO undercounts.
No ML model download needed — pure OpenCV math.
"""

import cv2
import numpy as np


class DensityEstimator:
    """Estimates crowd count using image analysis.
    More accurate than detection in dense scenes."""

    def __init__(self, calibration_factor: float = 1.0):
        """
        calibration_factor: multiply final estimate by this.
        Tune this based on your specific camera height/angle.
        Default 1.0 = no adjustment.
        """
        self.calibration_factor = calibration_factor
        self.bg_subtractor = cv2.createBackgroundSubtractorMOG2(
            history=500,
            varThreshold=50,
            detectShadows=False
        )
        self.frame_count = 0
        self.avg_person_area = None  # learned from YOLO boxes

    def set_avg_person_area(self, yolo_boxes: list):
        """Learn average person size from YOLO detections.
        Used to calibrate density estimates.
        Called from CrowdCounter when YOLO detects people."""
        if not yolo_boxes:
            return

        areas = []
        for box in yolo_boxes:
            x1, y1, x2, y2 = box["bbox"]
            area = (x2-x1) * (y2-y1)
            areas.append(area)

        if areas:
            self.avg_person_area = np.mean(areas)

    def estimate_edge_density(self, frame: np.ndarray) -> float:
        """Count people using edge detection.
        More edges = more people boundaries = more people."""
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)

        # Gaussian blur to remove noise
        blurred = cv2.GaussianBlur(gray, (5, 5), 0)

        # Canny edge detection
        edges = cv2.Canny(blurred, 50, 150)

        # Count edge pixels as fraction of frame
        h, w = frame.shape[:2]
        total_pixels = h * w
        edge_pixels = np.count_nonzero(edges)
        edge_ratio = edge_pixels / total_pixels

        return edge_ratio

    def estimate_foreground_density(self, frame: np.ndarray) -> float:
        """Use background subtraction to find moving people.
        Returns ratio of foreground pixels."""
        self.frame_count += 1
        fg_mask = self.bg_subtractor.apply(frame)

        # Remove noise
        kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))
        fg_clean = cv2.morphologyEx(fg_mask, cv2.MORPH_OPEN, kernel)
        fg_clean = cv2.morphologyEx(fg_clean, cv2.MORPH_CLOSE, kernel)

        h, w = frame.shape[:2]
        fg_pixels = np.count_nonzero(fg_clean)
        fg_ratio = fg_pixels / (h * w)

        return fg_ratio

    def estimate_hog_density(self, frame: np.ndarray) -> float:
        """Use HOG (Histogram of Oriented Gradients) to estimate person density.
        HOG captures human body shape patterns even in crowds."""
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)

        # Resize to standard size for HOG
        h, w = frame.shape[:2]
        scale = 320 / max(h, w)
        small = cv2.resize(gray, (int(w*scale), int(h*scale)))

        # HOG descriptor
        hog = cv2.HOGDescriptor()
        hog.setSVMDetector(cv2.HOGDescriptor_getDefaultPeopleDetector())

        # Detect people using HOG (fast, handles occlusion
        # better than deep learning for packed crowds)
        try:
            rects, weights = hog.detectMultiScale(
                small,
                winStride=(8, 8),
                padding=(4, 4),
                scale=1.05,
                hitThreshold=0.0,
                # finalThreshold=2
            )
        except TypeError:
            # Older OpenCV versions use different parameter name
            rects, weights = hog.detectMultiScale(
                small,
                winStride=(8, 8),
                padding=(4, 4),
                scale=1.05
            )

        hog_count = len(rects)
        return hog_count, rects, scale

    def estimate(self, frame: np.ndarray, yolo_live_count: int,
                 yolo_boxes: list) -> dict:
        """Main estimation function.
        Combines YOLO count + density estimation.
        Returns corrected crowd count estimate."""
        h, w = frame.shape[:2]
        frame_area = h * w

        # Update learned person size from YOLO
        if yolo_boxes:
            self.set_avg_person_area(yolo_boxes)

        # Get density signals
        edge_ratio = self.estimate_edge_density(frame)

        # HOG count (handles partial occlusion)
        hog_count, hog_rects, hog_scale = self.estimate_hog_density(frame)

        # Calculate occlusion factor from YOLO boxes
        # If boxes overlap a lot → many people hidden behind
        occlusion_factor = 1.0
        if len(yolo_boxes) >= 2:
            overlap_count = 0
            boxes = [b["bbox"] for b in yolo_boxes]
            for i in range(len(boxes)):
                for j in range(i+1, len(boxes)):
                    x1 = max(boxes[i][0], boxes[j][0])
                    y1 = max(boxes[i][1], boxes[j][1])
                    x2 = min(boxes[i][2], boxes[j][2])
                    y2 = min(boxes[i][3], boxes[j][3])
                    if x2 > x1 and y2 > y1:
                        overlap_count += 1

            total_pairs = len(boxes) * (len(boxes)-1) / 2
            overlap_ratio = overlap_count / max(total_pairs, 1)

            # More overlap = more hidden people
            # Factor range: 1.0 (no overlap) to 2.5 (heavy)
            occlusion_factor = 1.0 + (overlap_ratio * 1.5)

        # Estimate using average person area
        area_estimate = yolo_live_count
        if self.avg_person_area and self.avg_person_area > 0:
            # Estimate how many person-sized regions fit
            # in the crowd area
            crowd_pixel_area = edge_ratio * frame_area * 3
            area_estimate = int(crowd_pixel_area / self.avg_person_area)

        # Combine estimates:
        # - Use max of YOLO × occlusion and HOG count
        # - Weight YOLO higher when few people
        # - Weight HOG higher when dense crowd
        yolo_corrected = int(yolo_live_count * occlusion_factor)

        if yolo_live_count < 5:
            # Low density: trust YOLO completely
            final_estimate = yolo_live_count
            method = "yolo_direct"
        elif yolo_live_count < 15:
            # Medium density: average YOLO×occlusion + HOG
            final_estimate = int(
                (yolo_corrected * 0.6) +
                (max(hog_count, yolo_live_count) * 0.4)
            )
            method = "hybrid"
        else:
            # High density: use area-based estimation
            # YOLO severely undercounts here
            candidates = [
                yolo_corrected,
                hog_count * 2,  # HOG also undercounts dense
                area_estimate
            ]
            # Take median to avoid outliers
            final_estimate = int(np.median(candidates))
            method = "density"

        # Apply calibration
        final_estimate = int(final_estimate * self.calibration_factor)

        # Sanity bounds — never report 0 if YOLO saw people
        if yolo_live_count > 0:
            final_estimate = max(final_estimate, yolo_live_count)

        return {
            "estimated_count": final_estimate,
            "yolo_raw": yolo_live_count,
            "yolo_corrected": yolo_corrected,
            "hog_count": hog_count,
            "area_estimate": area_estimate,
            "occlusion_factor": round(occlusion_factor, 2),
            "edge_ratio": round(edge_ratio, 3),
            "method": method
        }

    def draw_density_overlay(self, frame: np.ndarray,
                            estimation: dict) -> np.ndarray:
        """Draw density estimation info on frame.
        Shows correction factor so judges understand."""
        annotated = frame.copy()

        method_colors = {
            "yolo_direct": (34, 197, 94),    # green
            "hybrid":      (251, 191, 36),   # amber
            "density":     (239, 68, 68),    # red
        }
        color = method_colors.get(estimation["method"], (255,255,255))

        # Draw estimation panel
        overlay = annotated.copy()
        cv2.rectangle(overlay, (0,0), (320, 180), (0,0,0), -1)
        cv2.addWeighted(overlay, 0.7, annotated, 0.3, 0, annotated)

        lines = [
            (f"ESTIMATED: {estimation['estimated_count']}", color, 0.7),
            (f"YOLO RAW: {estimation['yolo_raw']}", (150,150,150), 0.5),
            (f"HOG COUNT: {estimation['hog_count']}", (150,150,150), 0.5),
            (f"OCCLUSION x{estimation['occlusion_factor']}",
             (200,200,100), 0.5),
            (f"METHOD: {estimation['method'].upper()}", (100,200,255), 0.5),
            (f"EDGE DENSITY: {estimation['edge_ratio']}",
             (120,120,120), 0.45),
        ]

        for i, (text, col, scale) in enumerate(lines):
            cv2.putText(annotated, text,
                       (8, 25 + i*25),
                       cv2.FONT_HERSHEY_SIMPLEX,
                       scale, col, 2)

        return annotated
