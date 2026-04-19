# Crowd Counter Vision Integration - Complete

## Files Created/Modified

### Backend Files

1. **backend/vision_bridge.py** (NEW)
   - Bridges crowd_counter module with main CPI engine
   - Converts live_count to flow_rate using corridor calibration
   - Stores vision readings with 5-minute TTL
   - VisionProcessor class for async video processing
   - Integrates with YOLOv8 + ByteTrack from crowd_counter

2. **backend/simulator.py** (MODIFIED)
   - Added vision data check in update() method
   - Uses vision flow_rate when available instead of simulated data
   - Returns data_source field ("vision" or "simulation")
   - Includes vision metadata in frame results

3. **backend/main.py** (MODIFIED)
   - Added vision_bridge imports
   - Created VISION_UPLOAD_DIR for video storage
   - Added POST /api/vision/upload endpoint
   - Added GET /api/vision/status endpoint
   - Added DELETE /api/vision/clear/{corridor} endpoint
   - Added GET /api/vision/readings endpoint
   - Background task process_vision_video() for async processing
   - WebSocket broadcasts for vision_started, vision_progress, vision_complete

### Frontend Files

4. **frontend/src/components/VisionUpload.jsx** (NEW)
   - Collapsible upload panel with video file selection
   - Corridor selection with width calibration display
   - Real-time progress bar during processing
   - Live count and flow rate display when active
   - Clear button to revert to simulation
   - Supports MP4, AVI, MOV, MKV, WEBM formats

5. **frontend/src/App.jsx** (MODIFIED)
   - Added VisionUpload import
   - Added VisionUpload component to Dashboard tab
   - Added vision WebSocket message handlers:
     - vision_started
     - vision_progress
     - vision_complete
   - Notifications for vision completion

6. **frontend/src/hooks/useWebSocket.js** (MODIFIED)
   - Added vision message types to forwarding list
   - Forwards vision_progress, vision_complete, vision_started to window events

## How It Works

### Flow Rate Calculation

```
Flow Rate (pax/min) = live_count × calibration_multiplier

Calibration per corridor:
- Ambaji (4m):   multiplier = 12
- Dwarka (3m):   multiplier = 10
- Somnath (5m):  multiplier = 14
- Pavagadh (2.5m): multiplier = 8

Occlusion correction:
- live_count > 30: flow_rate × 1.4 (heavy occlusion)
- live_count > 15: flow_rate × 1.2 (moderate occlusion)
```

### Integration Points

1. **Video Upload**
   - User uploads video via VisionUpload component
   - Backend saves to vision_uploads/ directory
   - Starts async processing with VisionProcessor

2. **Processing**
   - YOLOv8 detects people frame by frame
   - ByteTrack tracks unique individuals
   - Converts count to flow_rate using corridor width
   - Updates vision_readings dict every frame

3. **CPI Integration**
   - simulator.py checks vision_readings before computing CPI
   - If vision data exists and not expired (5 min TTL):
     - Uses vision flow_rate instead of simulated
     - Keeps simulated transport_burst and chokepoint_density
   - If no vision data:
     - Uses normal simulation

4. **Dashboard Display**
   - VisionUpload shows LIVE badge when active
   - Displays current live_count and flow_rate
   - CPI gauge updates with real vision data
   - data_source field shows "vision" vs "simulation"

## API Endpoints

### POST /api/vision/upload
Upload video for crowd counting
- Query params: corridor, corridor_width_m (optional)
- Body: multipart/form-data with video file
- Returns: processing_started status

### GET /api/vision/status
Get current processing status
- Returns: processing, current_corridor, progress, active_readings

### DELETE /api/vision/clear/{corridor}
Clear vision data for corridor
- Reverts to simulation mode

### GET /api/vision/readings
Get all active vision readings
- Returns dict of corridor → reading data

## WebSocket Messages

### vision_started
```json
{
  "type": "vision_started",
  "corridor": "Ambaji",
  "message": "Vision analysis started for Ambaji"
}
```

### vision_progress
```json
{
  "type": "vision_progress",
  "corridor": "Ambaji",
  "progress": 45,
  "live_count": 23,
  "flow_rate": 276,
  "cpi": 0.65
}
```

### vision_complete
```json
{
  "type": "vision_complete",
  "corridor": "Ambaji",
  "result": {
    "status": "complete",
    "peak_live_count": 35,
    "average_live_count": 18.5,
    "peak_flow_rate": 420,
    "average_flow_rate": 222,
    "frames_processed": 450,
    "processing_time": 45.2
  },
  "message": "Vision analysis complete..."
}
```

## Features Preserved

- All existing simulation features work unchanged
- No breaking changes to existing APIs
- Vision data is optional enhancement
- Automatic fallback to simulation when vision expires
- Multiple corridors can have vision data simultaneously
- Each corridor tracks independently

## Testing

1. Start backend: `cd backend && uvicorn main:app --reload`
2. Start frontend: `cd frontend && npm run dev`
3. Login to dashboard
4. Navigate to Dashboard tab
5. Expand "Vision Input" panel
6. Select corridor and upload video
7. Watch progress bar and live updates
8. See CPI gauge update with real vision data
9. Clear to revert to simulation

## Dependencies

Backend:
- crowd_counter module (already exists)
- YOLOv8 model files (yolov8m.pt)
- OpenCV (cv2)
- asyncio for async processing

Frontend:
- React hooks (useState, useEffect, useRef)
- Existing WebSocket infrastructure
- No new npm packages required

## Notes

- Vision data expires after 5 minutes (configurable via VISION_READING_TTL)
- Only one video can be processed at a time
- Uploaded videos stored in backend/vision_uploads/
- Processing runs in background thread pool
- Progress updates every frame via WebSocket
- Fallback mode if YOLOv8 not available (uses file metadata estimate)
