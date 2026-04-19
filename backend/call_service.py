"""
call_service.py — Twilio voice call service for Tarkshastra
============================================================
Fixes applied:
  1. Async-safe: make_single_call_async wraps blocking Twilio I/O in executor
  2. Retry logic: up to 2 retries with 3-second back-off
  3. Credential validation logged at startup (no secrets exposed)
  4. Supports both DEMO_*_NUMBER and corridor-specific *_AMBAJI_NUMBER env vars
  5. Full structured logging at every stage
  6. Loads .env file automatically via python-dotenv
"""

import asyncio
import os
import time
from datetime import datetime

# Load .env file if present (local dev + Render both work)
try:
    from dotenv import load_dotenv
    load_dotenv()
    print("[ENV] .env file loaded")
except ImportError:
    print("[ENV] python-dotenv not installed — relying on system env vars")

# ── Twilio client init ────────────────────────────────────────────────────────
ACCOUNT_SID = os.getenv("TWILIO_ACCOUNT_SID", "").strip()
AUTH_TOKEN  = os.getenv("TWILIO_AUTH_TOKEN", "").strip()
FROM_NUMBER = os.getenv("TWILIO_FROM_NUMBER", "").strip()

# Startup credential check — logs presence without exposing values
print("=" * 50)
print("[TWILIO] Credential check at startup:")
print(f"  TWILIO_ACCOUNT_SID  : {'SET (' + ACCOUNT_SID[:6] + '...)' if ACCOUNT_SID else 'NOT SET ❌'}")
print(f"  TWILIO_AUTH_TOKEN   : {'SET' if AUTH_TOKEN else 'NOT SET ❌'}")
print(f"  TWILIO_FROM_NUMBER  : {FROM_NUMBER if FROM_NUMBER else 'NOT SET ❌'}")
print("=" * 50)

client = None
if ACCOUNT_SID and AUTH_TOKEN:
    try:
        from twilio.rest import Client
        client = Client(ACCOUNT_SID, AUTH_TOKEN)
        print("[TWILIO] ✅ Client initialized successfully")
    except Exception as e:
        print(f"[TWILIO] ❌ Client init failed: {e}")
        print("[TWILIO]    → Check TWILIO_ACCOUNT_SID and TWILIO_AUTH_TOKEN in Render env vars")
else:
    missing = []
    if not ACCOUNT_SID: missing.append("TWILIO_ACCOUNT_SID")
    if not AUTH_TOKEN:  missing.append("TWILIO_AUTH_TOKEN")
    print(f"[TWILIO] ⚠️  Mock mode — missing: {', '.join(missing)}")
    print("[TWILIO]    → Add these in Render → Environment → Add Environment Variable")

# ── Phone number registry ─────────────────────────────────────────────────────
# Supports two env var patterns:
#   1. DEMO_POLICE_NUMBER   (single number for all corridors — demo/test)
#   2. POLICE_AMBAJI_NUMBER (per-corridor numbers — production)
# Pattern 2 takes priority over pattern 1.

def _get_number(role: str, corridor: str = "") -> str:
    """Resolve phone number for a role+corridor combination.
    Falls back gracefully through multiple env var patterns."""
    role_upper = role.upper()
    corridor_upper = corridor.upper().replace(" ", "_") if corridor else ""

    # Priority 1: corridor-specific number (e.g. POLICE_AMBAJI_NUMBER)
    if corridor_upper:
        specific = os.getenv(f"{role_upper}_{corridor_upper}_NUMBER", "").strip()
        if specific:
            return specific

    # Priority 2: generic demo number (e.g. DEMO_POLICE_NUMBER)
    demo = os.getenv(f"DEMO_{role_upper}_NUMBER", "").strip()
    if demo:
        return demo

    # Priority 3: plain role number (e.g. POLICE_NUMBER)
    plain = os.getenv(f"{role_upper}_NUMBER", "").strip()
    return plain

# Log registered numbers at startup
print("[TWILIO] Registered demo numbers:")
for _role in ["police", "temple", "gsrtc", "driver"]:
    _num = _get_number(_role)
    _masked = _num[:6] + "****" if len(_num) > 6 else ("NOT SET ❌" if not _num else _num)
    print(f"  {_role:10} → {_masked}")

# ── Cooldown tracker ──────────────────────────────────────────────────────────
last_called: dict = {}
COOLDOWN_SECONDS = 300  # 5 minutes per number

def is_on_cooldown(phone: str) -> bool:
    if phone not in last_called:
        return False
    return (time.time() - last_called[phone]) < COOLDOWN_SECONDS

def cooldown_remaining(phone: str) -> int:
    if phone not in last_called:
        return 0
    return int(COOLDOWN_SECONDS - (time.time() - last_called[phone]))

# ── TwiML message builder ─────────────────────────────────────────────────────
def build_message(
    role: str,
    corridor: str,
    cpi: float,
    ttb_minutes: float,
    alert_id: str
) -> str:
    cpi_str = f"{cpi:.2f}"
    ttb_str = str(int(ttb_minutes))

    messages = {
        "police": (
            f"Urgent alert from Stampede Predictor System. "
            f"Genuine crush risk detected at {corridor} corridor. "
            f"Corridor Pressure Index is {cpi_str}. "
            f"Crush predicted in {ttb_str} minutes. "
            f"Incident report has been sent to your dashboard. "
            f"Deploy officers to Choke Point Bravo immediately. "
            f"Alert ID {alert_id}. This is an automated alert."
        ),
        "temple": (
            f"Urgent alert from Stampede Predictor System. "
            f"High crowd pressure at {corridor} temple. "
            f"Pressure Index {cpi_str}. Crush risk in {ttb_str} minutes. "
            f"PDF report sent to your dashboard. "
            f"Activate darshan hold at inner gate immediately. "
            f"Alert ID {alert_id}."
        ),
        "gsrtc": (
            f"Urgent alert from Stampede Predictor System. "
            f"{corridor} corridor is at critical capacity. "
            f"Pressure Index {cpi_str}. "
            f"Incident report sent to your dashboard. "
            f"Hold all incoming buses at the 3 kilometre checkpoint now. "
            f"Do not dispatch additional vehicles. "
            f"Alert ID {alert_id}."
        ),
        "driver": (
            f"Attention bus driver. "
            f"Your destination {corridor} has critical crowd pressure. "
            f"Pressure Index {cpi_str}. "
            f"Stop at the designated checkpoint immediately. "
            f"Do not proceed to temple area. "
            f"Alert ID {alert_id}."
        ),
    }

    return messages.get(role, messages["police"])

# ── Core call function (sync, runs in executor) ───────────────────────────────
def _make_call_sync(
    to_number: str,
    role: str,
    corridor: str,
    cpi: float,
    ttb_minutes: float,
    alert_id: str,
    attempt: int = 1
) -> dict:
    """Blocking Twilio call — must be run via asyncio executor.
    Returns result dict, never raises."""

    tag = f"[CALL attempt={attempt}] {role} → {to_number[:6]}****"

    # ── Validation ────────────────────────────────────────────────────────────
    if not to_number:
        print(f"[CALL SKIP] {role} — number not configured. "
              f"Set DEMO_{role.upper()}_NUMBER in Render env vars.")
        return {"status": "skipped", "reason": "number_not_configured",
                "role": role, "number": "NOT SET"}

    if not to_number.startswith("+"):
        print(f"[CALL SKIP] {role} — invalid format '{to_number}' "
              f"(must start with + country code, e.g. +919876543210)")
        return {"status": "skipped", "reason": "invalid_number_format",
                "role": role, "number": to_number}

    if is_on_cooldown(to_number):
        remaining = cooldown_remaining(to_number)
        print(f"[CALL SKIP] {role} — cooldown active ({remaining}s remaining)")
        return {"status": "skipped", "reason": "cooldown",
                "cooldown_remaining": remaining, "role": role,
                "number": to_number[:6] + "****"}

    # ── Mock mode ─────────────────────────────────────────────────────────────
    if not client:
        msg = build_message(role, corridor, cpi, ttb_minutes, alert_id)
        print(f"[CALL MOCK] {role} → {to_number[:6]}**** "
              f"(Twilio not configured — would say: {msg[:60]}...)")
        return {"status": "mock", "reason": "twilio_not_configured",
                "role": role, "number": to_number[:6] + "****",
                "message_preview": msg[:80] + "..."}

    if not FROM_NUMBER:
        print("[CALL ERROR] TWILIO_FROM_NUMBER not set — cannot make calls")
        return {"status": "error", "reason": "from_number_not_configured",
                "role": role, "number": to_number[:6] + "****"}

    # ── Build TwiML ───────────────────────────────────────────────────────────
    message = build_message(role, corridor, cpi, ttb_minutes, alert_id)
    twiml = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        "<Response>"
        f'<Say voice="alice" language="en-IN">{message}</Say>'
        '<Pause length="1"/>'
        f'<Say voice="alice" language="en-IN">{message}</Say>'
        "</Response>"
    )

    # ── Make call ─────────────────────────────────────────────────────────────
    print(f"{tag} — initiating call...")
    try:
        call = client.calls.create(
            to=to_number,
            from_=FROM_NUMBER,
            twiml=twiml,
            timeout=30,
        )
        last_called[to_number] = time.time()
        print(f"{tag} ✅ Call initiated | SID: {call.sid} | Status: {call.status}")
        return {
            "status": "calling",
            "sid": call.sid,
            "call_status": call.status,
            "role": role,
            "number": to_number[:6] + "****",
            "corridor": corridor,
            "cpi": cpi,
            "attempt": attempt,
        }

    except Exception as e:
        error_msg = str(e)
        print(f"{tag} ❌ Call failed: {error_msg}")

        # Decode common Twilio error codes with actionable fixes
        if "20003" in error_msg:
            reason = "invalid_credentials"
            print(f"  → FIX: TWILIO_ACCOUNT_SID or TWILIO_AUTH_TOKEN is wrong. "
                  f"Verify at twilio.com/console")
        elif "21608" in error_msg:
            reason = "number_not_verified_in_trial"
            print(f"  → FIX: {to_number} must be verified at "
                  f"twilio.com/console/phone-numbers/verified "
                  f"(Trial accounts can only call verified numbers)")
        elif "21211" in error_msg:
            reason = "invalid_phone_number"
            print(f"  → FIX: Check number format — must be E.164 e.g. +919876543210")
        elif "21214" in error_msg:
            reason = "number_not_reachable"
            print(f"  → FIX: Number {to_number[:6]}**** is not reachable")
        elif "21219" in error_msg:
            reason = "from_number_not_verified"
            print(f"  → FIX: TWILIO_FROM_NUMBER {FROM_NUMBER} is not a valid "
                  f"Twilio number. Check twilio.com/console/phone-numbers")
        elif "21401" in error_msg:
            reason = "invalid_twiml"
            print(f"  → FIX: TwiML is malformed — check build_message() output")
        elif "Connection" in error_msg or "timeout" in error_msg.lower():
            reason = "network_error"
            print(f"  → FIX: Network issue reaching Twilio API. "
                  f"Check Render outbound connectivity.")
        else:
            reason = error_msg[:120]

        return {
            "status": "error",
            "reason": reason,
            "role": role,
            "number": to_number[:6] + "****",
            "error": error_msg[:200],
            "attempt": attempt,
        }

# ── Async wrapper with retry ──────────────────────────────────────────────────
async def make_single_call_async(
    to_number: str,
    role: str,
    corridor: str,
    cpi: float,
    ttb_minutes: float,
    alert_id: str,
    max_retries: int = 2,
) -> dict:
    """Async-safe call with retry.
    Runs blocking Twilio I/O in a thread executor so the event loop
    is never blocked. Retries up to max_retries times on transient errors."""

    loop = asyncio.get_event_loop()
    last_result = {}

    for attempt in range(1, max_retries + 2):  # attempts: 1, 2, 3
        print(f"[CALL] {role} attempt {attempt}/{max_retries + 1}")

        last_result = await loop.run_in_executor(
            None,
            lambda a=attempt: _make_call_sync(
                to_number, role, corridor, cpi, ttb_minutes, alert_id, a
            ),
        )

        # Don't retry on non-transient outcomes
        if last_result["status"] in ("calling", "mock", "skipped"):
            return last_result

        # Don't retry on permanent errors (bad number, bad credentials)
        permanent_errors = {
            "number_not_configured",
            "invalid_number_format",
            "invalid_credentials",
            "number_not_verified_in_trial",
            "invalid_phone_number",
            "from_number_not_verified",
            "invalid_twiml",
        }
        if last_result.get("reason") in permanent_errors:
            print(f"[CALL] {role} — permanent error, no retry: "
                  f"{last_result.get('reason')}")
            return last_result

        # Transient error — wait before retry
        if attempt <= max_retries:
            wait = 3 * attempt  # 3s, 6s
            print(f"[CALL] {role} — transient error, retrying in {wait}s...")
            await asyncio.sleep(wait)

    print(f"[CALL] {role} — all {max_retries + 1} attempts exhausted")
    return last_result

# ── Backward-compat sync wrapper (for /api/call-alert endpoint) ──────────────
def make_single_call(
    to_number: str,
    role: str,
    corridor: str,
    cpi: float,
    ttb_minutes: float,
    alert_id: str,
) -> dict:
    """Sync wrapper kept for backward compatibility with manual call endpoint.
    For background tasks use make_single_call_async instead."""
    return _make_call_sync(to_number, role, corridor, cpi, ttb_minutes, alert_id)

# ── Multi-agency async call dispatcher ───────────────────────────────────────
async def trigger_corridor_calls_async(
    corridor: str,
    cpi: float,
    ttb_minutes: float,
    surge_type: str,
    alert_id: str,
) -> list:
    """Async version — fires all agency calls concurrently.
    Each call is independent; one failure does NOT stop others.
    Returns list of results."""

    print(f"[CALLS] ── Starting calls for alert {alert_id} ──")
    print(f"[CALLS] Corridor: {corridor} | CPI: {cpi:.3f} | "
          f"TTB: {ttb_minutes:.1f}min | Type: {surge_type}")

    roles = ["police", "temple", "gsrtc"]
    driver_number = _get_number("driver", corridor)
    if driver_number:
        roles.append("driver")

    # Build tasks — resolve numbers now so we can log them
    tasks = []
    for role in roles:
        number = _get_number(role, corridor)
        status_str = number[:6] + "****" if len(number) > 6 else ("NOT SET" if not number else number)
        print(f"[CALLS] Queuing {role:10} → {status_str}")
        tasks.append(
            make_single_call_async(
                to_number=number,
                role=role,
                corridor=corridor,
                cpi=cpi,
                ttb_minutes=ttb_minutes,
                alert_id=alert_id,
            )
        )

    # Fire all calls concurrently
    results = await asyncio.gather(*tasks, return_exceptions=True)

    # Normalise any unexpected exceptions from gather
    normalised = []
    for role, result in zip(roles, results):
        if isinstance(result, Exception):
            print(f"[CALLS] Unexpected exception for {role}: {result}")
            normalised.append({
                "status": "error",
                "role": role,
                "reason": str(result),
            })
        else:
            normalised.append(result)

    # Summary
    called  = [r for r in normalised if r["status"] == "calling"]
    skipped = [r for r in normalised if r["status"] == "skipped"]
    errors  = [r for r in normalised if r["status"] == "error"]
    mocked  = [r for r in normalised if r["status"] == "mock"]
    print(f"[CALLS] ── Done: called={len(called)} skipped={len(skipped)} "
          f"errors={len(errors)} mock={len(mocked)} ──")

    return normalised

# ── Legacy sync wrapper (kept for import compatibility) ───────────────────────
def trigger_corridor_calls(
    corridor: str,
    cpi: float,
    ttb_minutes: float,
    surge_type: str,
    alert_id: str,
) -> list:
    """Sync shim — only use from sync contexts.
    Background tasks should call trigger_corridor_calls_async directly."""
    loop = asyncio.get_event_loop()
    if loop.is_running():
        # We're inside an async context — this should not be called here.
        # Log a warning; caller should use trigger_corridor_calls_async.
        print("[CALLS] ⚠️  trigger_corridor_calls called from async context! "
              "Use trigger_corridor_calls_async instead.")
        # Create a new event loop in a thread to avoid blocking
        import concurrent.futures
        with concurrent.futures.ThreadPoolExecutor() as pool:
            future = pool.submit(
                asyncio.run,
                trigger_corridor_calls_async(
                    corridor, cpi, ttb_minutes, surge_type, alert_id
                ),
            )
            return future.result()
    return asyncio.run(
        trigger_corridor_calls_async(
            corridor, cpi, ttb_minutes, surge_type, alert_id
        )
    )
