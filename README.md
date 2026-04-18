# TS-11 — Stampede Window Predictor
**Gujarat Pilgrimage Corridors · Navratri Crowd Intelligence System**

Predicts stampede risk 8–12 minutes ahead for Ambaji, Dwarka, Somnath, and Pavagadh using a real-time Corridor Pressure Index (CPI) engine backed by 50,000 historical crowd observations.

---

## Architecture

```
Browser ──WS──▶ FastAPI (Render) ──▶ CPI Simulator ──▶ SQLite
          HTTP ◀───────────────────────────────────────
```

- **Backend** — Python 3.11 + FastAPI + WebSockets + aiosqlite  
- **Frontend** — React 18 + Vite + TailwindCSS + Recharts + Leaflet

---

## CPI Formula

```
CPI = (flow_rate_ppm / corridor_capacity_ppm) × 0.5
    + transport_burst_factor              × 0.3
    + chokepoint_density_norm             × 0.2
```

Colour zones: **Green** (0–0.40) · **Amber** (0.40–0.70) · **Red** (0.70–1.0)  
Breach threshold: **0.85**

---

## Features

| # | Feature | Status |
|---|---------|--------|
| F1 | CPI engine — 4 corridors, WebSocket broadcast every 2 s | ✅ |
| F2 | Crush risk prediction 8–12 min ahead, slope-based TTB | ✅ |
| F3 | Surge classifier: GENUINE_CRUSH / SELF_RESOLVING / PREDICTED_BREACH | ✅ |
| F4 | Shared dashboard with `?agency=` routing, animated arc gauge | ✅ |
| F5 | Alert-to-ack tracking in SQLite, 90 s countdown per agency | ✅ |
| F6 | Agency-specific action cards (Police / Temple / GSRTC) | ✅ |
| F7 | 20-min replay mode: play/pause/2×/4×, PREDICTION + PEAK markers | ✅ |
| F8 | Event log archive, sortable table, CSV export | ✅ |

---

## Local Development

### Backend
```bash
cd backend
pip install -r requirements.txt
cp .env.example .env
uvicorn main:app --reload --port 8000
```

### Frontend
```bash
cd frontend
npm install
cp .env.example .env       # set VITE_WS_URL and VITE_API_URL
npm run dev
```

Agency views:
- `http://localhost:5173/?agency=police`
- `http://localhost:5173/?agency=temple`
- `http://localhost:5173/?agency=gsrtc`

---

## Deploy to Render

A `render.yaml` is included at the repo root. Connect your GitHub repo to Render and both services deploy automatically.

**Backend env vars** (Render dashboard):
| Key | Value |
|-----|-------|
| `FRONTEND_URL` | `https://ts11-frontend.onrender.com` |

**Frontend env vars** (Render dashboard):
| Key | Value |
|-----|-------|
| `VITE_WS_URL`  | `wss://ts11-backend.onrender.com/ws` |
| `VITE_API_URL` | `https://ts11-backend.onrender.com` |

> The frontend pings `/health` on load to wake Render from cold start.

---

## API Reference

| Method | Path | Description |
|--------|------|-------------|
| `GET`  | `/health` | Health check + wake endpoint |
| `WS`   | `/ws` | Live CPI stream (every 2 s) |
| `GET`  | `/api/corridors` | Corridor configs |
| `GET`  | `/api/events` | Last 50 CPI log entries |
| `GET`  | `/api/events/export` | Download events as CSV |
| `GET`  | `/api/alerts` | Last 50 fired alerts |
| `POST` | `/api/ack/{alert_id}/{agency}` | Acknowledge alert |
| `GET`  | `/api/replay?frame=N` | Single replay frame |
| `GET`  | `/api/replay/all` | All 240 replay frames |
# Tarkshastra
