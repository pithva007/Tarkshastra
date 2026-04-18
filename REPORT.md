# TS-11 Stampede Window Predictor

## Table of Contents
1. [Overview](#overview)
2. [Project Architecture](#project-architecture)
3. [Key Features](#key-features)
4. [Tech Stack](#tech-stack)
5. [Installation & Setup](#installation--setup)
6. [Usage & Components](#usage--components)

---

## Overview
**TS-11 Stampede Window Predictor** is a real-time tracking, prediction, and coordination system designed to avert stampedes across major pilgrimage corridors in Gujarat (e.g., Ambaji, Dwarka, Somnath, Pavagadh) during high-density events like Navratri.

The application computes a live **Crowd Pressure Index (CPI)** and provides an early warning window (Time to Breach) before a critical crush situation develops. It facilitates multi-agency coordination among the **Police**, **Temple Trust**, and **GSRTC (Transport)**.

---

## Project Architecture
The project is divided into a robust `backend` API and an interactive `frontend` dashboard:

### 1. Backend
- **Data Engine:** Simulates and ingests continuous feeds of crowd metrics (flow rate, chokepoint density, transport burst).
- **Predictive Model:** Employs an intelligent algorithm (with optional Machine Learning integration) to calculate the CPI.
- **WebSocket Broadcaster:** Streams CPI batches to connected clients every 2 seconds.
- **Alert & Coordination API:** Exposes endpoints to trigger alerts and log agency acknowledgments.
- **Historical DB:** Records events, triggered alerts, and tracks historical metrics.

### 2. Frontend
- **Real-Time Dashboard:** Consumes WebSocket data to render live gauges, metric pills, and historical trend charts (via Recharts).
- **Agency Control Panels:** Role-based views allowing the Police, Temple Trust, and GSRTC to acknowledge alerts independently.
- **Topographical Map:** A spatial view mapping current CPI values to physical corridor locations.
- **Replay & Event Logs:** An analytical module that logs all past surges and exports them as CSV.

---

## Key Features
- **Live CPI Calculation:** Ranges from `0.0` (Safe) to `1.0` (Crush).
- **Predictive Breach Windows:** Calculates exact "Time to Breach (TTB)" if currents trends maintain.
- **Multi-Agency Workflow:** Generates individual actionable alerts. A crisis is considered "resolved" only when all three core agencies acknowledge the alert via the API.
- **Surge Classifications:** Automatically classifies data as `SAFE`, `SELF_RESOLVING`, `GENUINE_CRUSH`, `PREDICTED_BREACH`, or `HIGH_PRESSURE`.
- **"What-If" Simulation Endpoint:** Allows agencies to simulate different scenarios (e.g., what if transport burst increases by 20%?) without affecting the live state.
- **Exportable Metrics:** Event logs can be easily exported as `.csv` files for post-incident reporting.

---

## Tech Stack
### Backend
- **Framework:** Python, FastAPI, Uvicorn
- **Real-Time:** WebSockets
- **Data/Logic:** Numpy, Pandas (via `TS-PS11.csv`), Custom Simulator
- **Database:** SQLite (via internal DB module)

### Frontend
- **Framework:** React + Vite
- **Styling:** Tailwind CSS, PostCSS
- **Data Visualization:** Recharts, custom SVG Gauges
- **Networking:** Axios, native WebSocket API

---

## Installation & Setup

### 1. Backend Setup
```bash
cd backend
python -m venv venv
source venv/bin/activate  # On Windows use `venv\Scripts\activate`
pip install -r requirements.txt

# Start the server (runs on port 8000 by default)
python main.py
```

### 2. Frontend Setup
Make sure you have Node installed, then:
```bash
cd frontend
npm install

# Start the development server
npm run dev
```

The frontend will run by default on `http://localhost:5173`. Make sure the backend is running concurrently so that WebSockets can connect properly.

---

## Usage & Components

1. **Dashboard (`/`)**: Displays the overarching view for the selected corridor. Contains the Pressure Gauge, vital stats (Transport Burst, Flow Rate), and the Live CPI chart.
2. **Agency URL Param**: Add `?agency=police` (or `temple`, `gsrtc`) to the URL to simulate logging in as that respective agency. This filters the action panel.
3. **Map Tab**: Select different corridors visually and gauge their heat signatures.
4. **Events Tab**: A sortable, auto-refreshing table holding historic CPI events and Alert Acknowledgments. Click "Export CSV" to download the logs.
5. **Replay Tab**: Used for reviewing historical offline `.json` or `.csv` data for training and post-mortem analysis.