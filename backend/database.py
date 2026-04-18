"""
SQLite schema and async helpers for TS-11 Stampede Predictor.

Tables:
  alerts  — one row per fired alert, tracks 3-agency ack times
  cpi_log — rolling 10-minute CPI readings (pruned automatically)
"""
import aiosqlite
from datetime import datetime, timezone

DB_PATH = "./stampede.db"


async def init_db():
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS alerts (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                alert_id    TEXT    UNIQUE NOT NULL,
                corridor    TEXT    NOT NULL,
                cpi         REAL    NOT NULL,
                fired_at    TEXT    NOT NULL,
                surge_type  TEXT    NOT NULL DEFAULT 'UNKNOWN',
                police_ack  TEXT,
                temple_ack  TEXT,
                gsrtc_ack   TEXT,
                ml_confidence REAL  DEFAULT NULL
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS cpi_log (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                corridor        TEXT NOT NULL,
                cpi             REAL NOT NULL,
                flow_rate       REAL NOT NULL,
                transport_burst REAL NOT NULL,
                chokepoint_density REAL NOT NULL,
                surge_type      TEXT NOT NULL,
                alert_fired     INTEGER DEFAULT 0,
                logged_at       TEXT NOT NULL
            )
        """)
        # Migration: add ml_confidence column if it doesn't exist yet
        try:
            await db.execute("ALTER TABLE alerts ADD COLUMN ml_confidence REAL DEFAULT NULL")
        except Exception:
            pass
        await db.commit()


# ── Alert table ───────────────────────────────────────────────────────────────

async def insert_alert(
    alert_id: str,
    corridor: str,
    cpi: float,
    surge_type: str,
    ml_confidence: float | None = None,
) -> int:
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            """INSERT OR IGNORE INTO alerts
               (alert_id, corridor, cpi, fired_at, surge_type, ml_confidence)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (alert_id, corridor, round(cpi, 4), _now(), surge_type, ml_confidence),
        )
        await db.commit()
        return cur.lastrowid or 0


async def ack_alert(alert_id: str, agency: str) -> bool:
    col = f"{agency}_ack"
    if col not in ("police_ack", "temple_ack", "gsrtc_ack"):
        return False
    ts = _now()
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            f"UPDATE alerts SET {col} = ? WHERE alert_id = ? AND {col} IS NULL",
            (ts, alert_id),
        )
        await db.commit()
    return True


async def get_alerts(limit: int = 50) -> list:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM alerts ORDER BY id DESC LIMIT ?", (limit,)
        ) as cur:
            return [dict(r) for r in await cur.fetchall()]


async def get_alert_by_id(alert_id: str) -> dict | None:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM alerts WHERE alert_id = ? LIMIT 1", (alert_id,)
        ) as cur:
            row = await cur.fetchone()
            return dict(row) if row else None


# ── CPI log ───────────────────────────────────────────────────────────────────

async def log_cpi(
    corridor: str,
    cpi: float,
    flow_rate: float,
    transport_burst: float,
    chokepoint_density: float,
    surge_type: str,
    alert_fired: bool = False,
):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """INSERT INTO cpi_log
               (corridor, cpi, flow_rate, transport_burst, chokepoint_density,
                surge_type, alert_fired, logged_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                corridor, round(cpi, 4), round(flow_rate, 2),
                round(transport_burst, 4), round(chokepoint_density, 4),
                surge_type, int(alert_fired), _now(),
            ),
        )
        # Keep only the last 3000 rows to prevent unbounded growth
        await db.execute(
            "DELETE FROM cpi_log WHERE id <= (SELECT MAX(id) - 3000 FROM cpi_log)"
        )
        await db.commit()


async def get_events(limit: int = 50) -> list:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM cpi_log ORDER BY id DESC LIMIT ?", (limit,)
        ) as cur:
            return [dict(r) for r in await cur.fetchall()]


# ── Helpers ────────────────────────────────────────────────────────────────────

def _now() -> str:
    return datetime.now(timezone.utc).isoformat()
