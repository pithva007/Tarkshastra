"""
Twilio phone call alert service for TS-11 Stampede Predictor.
Fires role-specific voice calls when CPI crosses 0.85 (GENUINE_CRUSH).
"""
import os
import time

ACCOUNT_SID  = os.getenv("TWILIO_ACCOUNT_SID", "")
AUTH_TOKEN   = os.getenv("TWILIO_AUTH_TOKEN", "")
FROM_NUMBER  = os.getenv("TWILIO_FROM_NUMBER", "")

# Only init client if credentials exist
try:
    from twilio.rest import Client
    client = Client(ACCOUNT_SID, AUTH_TOKEN) if ACCOUNT_SID else None
except ImportError:
    client = None

# Cooldown tracker — prevent spam calls
# Format: { "phone_number": last_called_timestamp }
last_called: dict = {}
COOLDOWN_SECONDS = 300  # 5 minutes

# Pre-registered numbers per role per corridor
# In production these come from DB — for hackathon hardcoded
REGISTERED_NUMBERS = {
    "police": {
        "Ambaji":   os.getenv("POLICE_AMBAJI_NUMBER", ""),
        "Dwarka":   os.getenv("POLICE_DWARKA_NUMBER", ""),
        "Somnath":  os.getenv("POLICE_SOMNATH_NUMBER", ""),
        "Pavagadh": os.getenv("POLICE_PAVAGADH_NUMBER", ""),
    },
    "temple": {
        "Ambaji":   os.getenv("TEMPLE_AMBAJI_NUMBER", ""),
        "Dwarka":   os.getenv("TEMPLE_DWARKA_NUMBER", ""),
        "Somnath":  os.getenv("TEMPLE_SOMNATH_NUMBER", ""),
        "Pavagadh": os.getenv("TEMPLE_PAVAGADH_NUMBER", ""),
    },
    "gsrtc": {
        "Ambaji":   os.getenv("GSRTC_AMBAJI_NUMBER", ""),
        "Dwarka":   os.getenv("GSRTC_DWARKA_NUMBER", ""),
        "Somnath":  os.getenv("GSRTC_SOMNATH_NUMBER", ""),
        "Pavagadh": os.getenv("GSRTC_PAVAGADH_NUMBER", ""),
    },
    "driver": {
        "Ambaji":   os.getenv("DRIVER_AMBAJI_NUMBER", ""),
        "Dwarka":   os.getenv("DRIVER_DWARKA_NUMBER", ""),
        "Somnath":  os.getenv("DRIVER_SOMNATH_NUMBER", ""),
        "Pavagadh": os.getenv("DRIVER_PAVAGADH_NUMBER", ""),
    },
}


def build_message(
    role: str,
    corridor: str,
    cpi: float,
    ttb_minutes: float,
    surge_type: str,
    alert_id: str,
) -> str:
    """Build role-specific alert message."""
    cpi_str = f"{cpi:.2f}"
    ttb_str = f"{int(ttb_minutes)}"

    messages = {
        "police": (
            f"Urgent alert from Stampede Predictor System. "
            f"Genuine crush risk detected at {corridor} corridor. "
            f"Corridor Pressure Index is {cpi_str}. "
            f"Estimated crush in {ttb_str} minutes. "
            f"Deploy officers to Choke Point Bravo immediately. "
            f"Alert ID: {alert_id}. "
            f"This is an automated alert. Please acknowledge on dashboard."
        ),
        "temple": (
            f"Urgent alert from Stampede Predictor System. "
            f"High crowd pressure at {corridor} temple. "
            f"Pressure Index {cpi_str}. Crush risk in {ttb_str} minutes. "
            f"Activate darshan hold at inner gate immediately. "
            f"Redirect pilgrims to Queue Charlie. "
            f"Alert ID: {alert_id}."
        ),
        "gsrtc": (
            f"Urgent alert from Stampede Predictor System. "
            f"{corridor} corridor is at critical capacity. "
            f"Pressure Index {cpi_str}. "
            f"Hold all incoming buses at the 3 kilometre checkpoint now. "
            f"Do not dispatch additional vehicles until further notice. "
            f"Alert ID: {alert_id}."
        ),
        "driver": (
            f"Attention bus driver. Your destination {corridor} "
            f"has critical crowd pressure. Pressure Index {cpi_str}. "
            f"Stop at the designated checkpoint immediately. "
            f"Do not proceed to temple area. "
            f"Await instructions from control room. "
            f"This is an automated safety alert."
        ),
    }

    return messages.get(role, messages["police"])


def is_on_cooldown(phone: str) -> bool:
    """Check if number was called recently."""
    if phone not in last_called:
        return False
    return (time.time() - last_called[phone]) < COOLDOWN_SECONDS


def make_alert_call(
    to_number: str,
    role: str,
    corridor: str,
    cpi: float,
    ttb_minutes: float,
    surge_type: str,
    alert_id: str,
) -> dict:
    """Make a Twilio call with role-specific message.
    Returns result dict with status and details."""

    # Validate inputs
    if not to_number or not to_number.startswith("+"):
        return {
            "status": "skipped",
            "reason": "invalid_number",
            "number": to_number,
        }

    # Check cooldown
    if is_on_cooldown(to_number):
        remaining = int(COOLDOWN_SECONDS - (time.time() - last_called[to_number]))
        return {
            "status": "skipped",
            "reason": "cooldown",
            "cooldown_remaining_seconds": remaining,
            "number": to_number,
        }

    # Check if Twilio is configured
    if not client:
        print(
            f"[CALL SKIPPED] Twilio not configured. "
            f"Would call {to_number} for {role} at {corridor}"
        )
        return {
            "status": "mock",
            "reason": "twilio_not_configured",
            "number": to_number,
            "message_preview": build_message(
                role, corridor, cpi, ttb_minutes, surge_type, alert_id
            )[:100] + "...",
        }

    # Build message
    message = build_message(role, corridor, cpi, ttb_minutes, surge_type, alert_id)

    # Build TwiML — Alice voice with en-IN accent, message repeated once
    twiml = f"""<?xml version="1.0" encoding="UTF-8"?>
<Response>
  <Say voice="alice" language="en-IN">{message}</Say>
  <Pause length="1"/>
  <Say voice="alice" language="en-IN">Repeating. {message}</Say>
</Response>"""

    try:
        call = client.calls.create(
            to=to_number,
            from_=FROM_NUMBER,
            twiml=twiml,
            timeout=30,
        )

        # Update cooldown
        last_called[to_number] = time.time()
        print(f"[CALL MADE] SID:{call.sid} → {to_number} ({role} at {corridor})")

        return {
            "status": "calling",
            "sid": call.sid,
            "number": to_number,
            "role": role,
            "corridor": corridor,
            "message_length_chars": len(message),
        }

    except Exception as e:
        print(f"[CALL ERROR] {to_number}: {e}")
        return {
            "status": "error",
            "error": str(e),
            "number": to_number,
        }


def trigger_corridor_calls(
    corridor: str,
    cpi: float,
    ttb_minutes: float,
    surge_type: str,
    alert_id: str,
) -> list:
    """Trigger calls to ALL registered roles for a corridor.
    Called automatically when CRITICAL alert fires.
    Returns list of call results."""
    results = []

    for role in ["police", "temple", "gsrtc", "driver"]:
        number = REGISTERED_NUMBERS.get(role, {}).get(corridor, "")
        if number:
            result = make_alert_call(
                to_number=number,
                role=role,
                corridor=corridor,
                cpi=cpi,
                ttb_minutes=ttb_minutes,
                surge_type=surge_type,
                alert_id=alert_id,
            )
            results.append({"role": role, "corridor": corridor, **result})
        else:
            results.append({
                "role": role,
                "corridor": corridor,
                "status": "skipped",
                "reason": "no_number_registered",
            })

    return results
