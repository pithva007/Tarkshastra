"""
SQLite schema and async helpers for TS-11 Stampede Predictor.

Tables:
  alerts               — one row per fired alert, tracks 3-agency ack times
  cpi_log              — rolling 10-minute CPI readings (pruned automatically)
  notifications        — push notifications per role/unit
  historical_incidents — seeded historical Navratri incident data
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
        await db.execute("""
            CREATE TABLE IF NOT EXISTS notifications (
                id        INTEGER PRIMARY KEY AUTOINCREMENT,
                alert_id  TEXT,
                role      TEXT,
                unit_id   TEXT,
                message   TEXT,
                sent_at   TEXT,
                read_at   TEXT
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS historical_incidents (
                id                      INTEGER PRIMARY KEY AUTOINCREMENT,
                year                    INTEGER,
                event                   TEXT,
                corridor                TEXT,
                date_label              TEXT,
                peak_time               TEXT,
                peak_cpi                REAL,
                surge_type              TEXT,
                incident                TEXT,
                action_taken            TEXT,
                pilgrims_affected       INTEGER,
                buses_held              INTEGER,
                resolution_time_minutes INTEGER
            )
        """)

        await db.execute("""
            CREATE TABLE IF NOT EXISTS call_log (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                alert_id     TEXT    NOT NULL,
                corridor     TEXT    NOT NULL,
                role         TEXT    NOT NULL,
                phone_number TEXT,
                call_sid     TEXT,
                status       TEXT,
                reason       TEXT,
                cpi          REAL,
                surge_type   TEXT,
                called_at    TEXT    NOT NULL
            )
        """)

        # Migration: add ml_confidence column if it doesn't exist yet
        try:
            await db.execute("ALTER TABLE alerts ADD COLUMN ml_confidence REAL DEFAULT NULL")
        except Exception:
            pass

        await db.commit()

    # Seed historical incidents (idempotent)
    await _seed_historical()


async def _seed_historical():
    """Seed historical_incidents from HISTORICAL_DATA if table is empty."""
    from historical import HISTORICAL_DATA
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT COUNT(*) FROM historical_incidents") as cur:
            row = await cur.fetchone()
            if row and row[0] > 0:
                return  # already seeded

        for inc in HISTORICAL_DATA:
            await db.execute(
                """INSERT INTO historical_incidents
                   (year, event, corridor, date_label, peak_time, peak_cpi,
                    surge_type, incident, action_taken, pilgrims_affected,
                    buses_held, resolution_time_minutes)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    inc["year"], inc["event"], inc["corridor"], inc["date_label"],
                    inc["peak_time"], inc["peak_cpi"], inc["surge_type"],
                    inc["incident"], inc["action_taken"], inc["pilgrims_affected"],
                    inc["buses_held"], inc["resolution_time_minutes"],
                ),
            )
        await db.commit()
        print("[db] Historical incidents seeded.")


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


# ── Notifications ─────────────────────────────────────────────────────────────

async def insert_notification(
    alert_id: str,
    role: str,
    unit_id: str,
    message: str,
) -> int:
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            """INSERT INTO notifications (alert_id, role, unit_id, message, sent_at)
               VALUES (?, ?, ?, ?, ?)""",
            (alert_id, role, unit_id, message, _now()),
        )
        await db.commit()
        return cur.lastrowid or 0


async def mark_notification_read(notification_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE notifications SET read_at = ? WHERE id = ?",
            (_now(), notification_id),
        )
        await db.commit()


async def get_notifications(role: str = None, limit: int = 20) -> list:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        if role:
            async with db.execute(
                "SELECT * FROM notifications WHERE role = ? ORDER BY id DESC LIMIT ?",
                (role, limit),
            ) as cur:
                return [dict(r) for r in await cur.fetchall()]
        else:
            async with db.execute(
                "SELECT * FROM notifications ORDER BY id DESC LIMIT ?", (limit,)
            ) as cur:
                return [dict(r) for r in await cur.fetchall()]


# ── Historical incidents ──────────────────────────────────────────────────────

async def get_historical_incidents(corridor: str = None) -> list:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        if corridor:
            async with db.execute(
                "SELECT * FROM historical_incidents WHERE corridor = ? ORDER BY year DESC",
                (corridor,),
            ) as cur:
                return [dict(r) for r in await cur.fetchall()]
        else:
            async with db.execute(
                "SELECT * FROM historical_incidents ORDER BY year DESC"
            ) as cur:
                return [dict(r) for r in await cur.fetchall()]


# ── Helpers ────────────────────────────────────────────────────────────────────

def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


# ── Call log ──────────────────────────────────────────────────────────────────

async def log_call(
    db,
    alert_id: str,
    corridor: str,
    role: str,
    phone_number: str,
    call_sid: str,
    status: str,
    reason: str,
    cpi: float,
    surge_type: str,
):
    called_at = datetime.now(timezone.utc).isoformat()
    await db.execute(
        """INSERT INTO call_log
           (alert_id, corridor, role, phone_number, call_sid,
            status, reason, cpi, surge_type, called_at)
           VALUES (?,?,?,?,?,?,?,?,?,?)""",
        (
            alert_id, corridor, role, phone_number, call_sid,
            status, reason, cpi, surge_type, called_at,
        ),
    )
    await db.commit()


async def get_call_log(db, limit: int = 50) -> list:
    cursor = await db.execute(
        "SELECT * FROM call_log ORDER BY called_at DESC LIMIT ?",
        (limit,),
    )
    rows = await cursor.fetchall()
    return [
        dict(zip([col[0] for col in cursor.description], row))
        for row in rows
    ]
