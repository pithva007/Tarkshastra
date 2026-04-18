import time
import math
import random
from datetime import datetime

# 8 buses with real Gujarat route waypoints
# Each bus moves along its route continuously
# When it reaches destination it loops back
BUSES = [
    {
        "id": "GJ-01-BUS-042",
        "driver": "Ramesh Patel",
        "route": "Ahmedabad to Ambaji",
        "destination": "Ambaji",
        "destination_coords": [23.7267, 72.8503],
        "speed_kmh": 55,
        "passengers": 48,
        "capacity": 52,
        "waypoints": [
            [23.0225, 72.5714],
            [23.2156, 72.6412],
            [23.4521, 72.7234],
            [23.5812, 72.7891],
            [23.6534, 72.8012],
            [23.7267, 72.8503]
        ]
    },
    {
        "id": "GJ-05-BUS-118",
        "driver": "Suresh Modi",
        "route": "Rajkot to Dwarka",
        "destination": "Dwarka",
        "destination_coords": [22.2394, 68.9678],
        "speed_kmh": 60,
        "passengers": 41,
        "capacity": 52,
        "waypoints": [
            [22.3039, 70.8022],
            [22.2712, 70.2341],
            [22.2523, 69.6234],
            [22.2394, 68.9678]
        ]
    },
    {
        "id": "GJ-12-BUS-067",
        "driver": "Vijay Shah",
        "route": "Surat to Somnath",
        "destination": "Somnath",
        "destination_coords": [20.8880, 70.4013],
        "speed_kmh": 58,
        "passengers": 45,
        "capacity": 52,
        "waypoints": [
            [21.1702, 72.8311],
            [21.0423, 71.9812],
            [20.9412, 71.3821],
            [20.8880, 70.4013]
        ]
    },
    {
        "id": "GJ-08-BUS-234",
        "driver": "Mahesh Trivedi",
        "route": "Vadodara to Pavagadh",
        "destination": "Pavagadh",
        "destination_coords": [22.4673, 73.5315],
        "speed_kmh": 45,
        "passengers": 38,
        "capacity": 52,
        "waypoints": [
            [22.3072, 73.1812],
            [22.3891, 73.3421],
            [22.4673, 73.5315]
        ]
    },
    {
        "id": "GJ-03-BUS-089",
        "driver": "Dinesh Chauhan",
        "route": "Gandhinagar to Ambaji",
        "destination": "Ambaji",
        "destination_coords": [23.7267, 72.8503],
        "speed_kmh": 52,
        "passengers": 50,
        "capacity": 52,
        "waypoints": [
            [23.2156, 72.6369],
            [23.4012, 72.7123],
            [23.6012, 72.7891],
            [23.7267, 72.8503]
        ]
    },
    {
        "id": "GJ-07-BUS-156",
        "driver": "Kiran Joshi",
        "route": "Bhavnagar to Somnath",
        "destination": "Somnath",
        "destination_coords": [20.8880, 70.4013],
        "speed_kmh": 56,
        "passengers": 33,
        "capacity": 52,
        "waypoints": [
            [21.7645, 72.1519],
            [21.3456, 71.6234],
            [20.8880, 70.4013]
        ]
    },
    {
        "id": "GJ-09-BUS-301",
        "driver": "Amit Desai",
        "route": "Anand to Dwarka",
        "destination": "Dwarka",
        "destination_coords": [22.2394, 68.9678],
        "speed_kmh": 62,
        "passengers": 29,
        "capacity": 52,
        "waypoints": [
            [22.5645, 72.9289],
            [22.4712, 71.6234],
            [22.2394, 68.9678]
        ]
    },
    {
        "id": "GJ-11-BUS-445",
        "driver": "Pravin Patel",
        "route": "Surat to Pavagadh",
        "destination": "Pavagadh",
        "destination_coords": [22.4673, 73.5315],
        "speed_kmh": 50,
        "passengers": 44,
        "capacity": 52,
        "waypoints": [
            [21.1702, 72.8311],
            [21.8923, 73.0234],
            [22.4673, 73.5315]
        ]
    }
]

def haversine_km(lat1, lng1, lat2, lng2) -> float:
    """Calculate distance in km between two coordinates."""
    R = 6371
    dlat = math.radians(lat2 - lat1)
    dlng = math.radians(lng2 - lng1)
    a = (math.sin(dlat/2)**2 +
         math.cos(math.radians(lat1)) *
         math.cos(math.radians(lat2)) *
         math.sin(dlng/2)**2)
    return R * 2 * math.asin(math.sqrt(a))

def interpolate(p1, p2, t) -> list:
    """Linearly interpolate between two [lat, lng] points.
    t = 0.0 returns p1, t = 1.0 returns p2."""
    return [p1[0] + (p2[0] - p1[0]) * t,
            p1[1] + (p2[1] - p1[1]) * t]

class BusSimulator:
    """Simulates 8 buses moving along Gujarat pilgrimage routes.
    Each bus has a progress value 0.0 to 1.0 across all waypoints.
    Progress advances based on speed and elapsed time."""
    
    def __init__(self):
        self.bus_states = {}
        now = time.time()
        
        for bus in BUSES:
            # Calculate total route distance
            waypoints = bus["waypoints"]
            total_dist = 0
            segment_distances = []
            
            for i in range(len(waypoints) - 1):
                d = haversine_km(waypoints[i][0], waypoints[i][1],
                               waypoints[i+1][0], waypoints[i+1][1])
                segment_distances.append(d)
                total_dist += d
            
            # Random starting progress so buses are
            # spread across their routes at startup
            start_progress = random.uniform(0.05, 0.85)
            
            self.bus_states[bus["id"]] = {
                "config": bus,
                "progress": start_progress,
                "total_distance_km": total_dist,
                "segment_distances": segment_distances,
                "last_update": now,
                "alert_status": "normal",
                "held": False,
                "hold_reason": ""
            }
        
        print(f"[BUS SIM] Initialized {len(self.bus_states)} buses")
    
    def _get_position_from_progress(self, waypoints: list,
                                   segment_distances: list,
                                   progress: float) -> list:
        """Convert overall progress (0-1) to lat/lng position.
        Handles multi-segment routes correctly."""
        if progress <= 0:
            return waypoints[0]
        if progress >= 1:
            return waypoints[-1]
        
        total = sum(segment_distances)
        if total == 0:
            return waypoints[0]
        
        target_dist = progress * total
        covered = 0
        
        for i, seg_dist in enumerate(segment_distances):
            if covered + seg_dist >= target_dist:
                # Position is within this segment
                seg_progress = ((target_dist - covered) / seg_dist
                               if seg_dist > 0 else 0)
                return interpolate(waypoints[i],
                                 waypoints[i + 1],
                                 seg_progress)
            covered += seg_dist
        
        return waypoints[-1]
    
    def _get_alert_status(self,
                         destination: str,
                         cpi_data: dict = None) -> tuple:
        """Determine bus alert status based on destination CPI.
        Returns (status, message)."""
        if cpi_data and destination in cpi_data:
            cpi = cpi_data[destination]
            if cpi >= 0.85:
                return ("hold",
                       f"{destination} CRITICAL — "
                       f"Stop at checkpoint immediately")
            elif cpi >= 0.70:
                return ("caution",
                       f"{destination} WARNING — "
                       f"Slow down, prepare to hold")
        
        return ("normal", "Proceed — corridor clear")
    
    def update(self, cpi_data: dict = None) -> list:
        """Advance all bus positions and return current state.
        Call this every 5 seconds.
        cpi_data: dict of corridor → current CPI value"""
        now = time.time()
        result = []
        
        for bus_id, state in self.bus_states.items():
            config = state["config"]
            elapsed = now - state["last_update"]
            state["last_update"] = now
            
            # Advance progress unless bus is held
            if not state["held"]:
                # Distance covered in elapsed time
                speed_ms = config["speed_kmh"] / 3.6
                dist_covered = speed_ms * elapsed / 1000
                total_dist = state["total_distance_km"]
                
                if total_dist > 0:
                    progress_delta = dist_covered / total_dist
                else:
                    progress_delta = 0.001
                
                state["progress"] = min(state["progress"] + progress_delta,
                                      1.0)
                
                # Loop bus back to start when it reaches destination
                if state["progress"] >= 1.0:
                    state["progress"] = 0.0
                    print(f"[BUS] {bus_id} completed route, "
                         f"restarting")
            
            # Get current lat/lng
            pos = self._get_position_from_progress(
                config["waypoints"],
                state["segment_distances"],
                state["progress"]
            )
            
            # Calculate distance remaining to destination
            dest = config["destination_coords"]
            dist_remaining = haversine_km(pos[0], pos[1], dest[0], dest[1])
            
            # ETA
            speed = config["speed_kmh"]
            eta_hours = dist_remaining / speed if speed > 0 else 0
            eta_minutes = int(eta_hours * 60)
            
            # Alert status from CPI
            alert_status, alert_msg = self._get_alert_status(
                config["destination"], cpi_data)
            state["alert_status"] = alert_status
            
            # Auto-hold buses when destination is critical
            if alert_status == "hold" and not state["held"]:
                state["held"] = True
                state["hold_reason"] = (f"Corridor critical — "
                                      f"held at checkpoint")
            elif alert_status == "normal" and state["held"]:
                state["held"] = False
                state["hold_reason"] = ""
            
            result.append({
                "id": bus_id,
                "driver": config["driver"],
                "route": config["route"],
                "destination": config["destination"],
                "lat": round(pos[0], 6),
                "lng": round(pos[1], 6),
                "progress": round(state["progress"], 4),
                "eta_minutes": eta_minutes,
                "distance_km": round(dist_remaining, 1),
                "speed_kmh": (0 if state["held"]
                            else config["speed_kmh"]),
                "passengers": config["passengers"],
                "capacity": config["capacity"],
                "alert_status": alert_status,
                "alert_message": alert_msg,
                "held": state["held"],
                "hold_reason": state["hold_reason"]
            })
        
        return result