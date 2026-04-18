import os
import time
from datetime import datetime
from twilio.rest import Client

ACCOUNT_SID = os.getenv("TWILIO_ACCOUNT_SID", "")
AUTH_TOKEN  = os.getenv("TWILIO_AUTH_TOKEN", "")
FROM_NUMBER = os.getenv("TWILIO_FROM_NUMBER", "")

client = None
if ACCOUNT_SID and AUTH_TOKEN:
    try:
        client = Client(ACCOUNT_SID, AUTH_TOKEN)
        print("[TWILIO] Client initialized")
    except Exception as e:
        print(f"[TWILIO] Init failed: {e}")
else:
    print("[TWILIO] No credentials — mock mode")

# Read all 3 numbers from environment
# These must be set in Render environment variables
DEMO_NUMBERS = {
    "police": os.getenv("DEMO_POLICE_NUMBER", ""),
    "temple": os.getenv("DEMO_TEMPLE_NUMBER", ""),
    "gsrtc":  os.getenv("DEMO_GSRTC_NUMBER",  ""),
    "driver": os.getenv("DEMO_DRIVER_NUMBER",  ""),
}

# Print on startup so you can verify in Render logs
print("[TWILIO] Registered numbers:")
for role, number in DEMO_NUMBERS.items():
    masked = number[:6] + "****" if len(number) > 6 else "NOT SET"
    print(f"  {role:10} → {masked}")

# Cooldown per number — 5 minutes
last_called: dict = {}
COOLDOWN_SECONDS = 300

def is_on_cooldown(phone: str) -> bool:
    if phone not in last_called:
        return False
    return (time.time() - last_called[phone]) < COOLDOWN_SECONDS

def cooldown_remaining(phone: str) -> int:
    if phone not in last_called:
        return 0
    return int(COOLDOWN_SECONDS - (time.time() - last_called[phone]))

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
            f"Genuine crush risk detected at {corridor} "
            f"corridor. "
            f"Corridor Pressure Index is {cpi_str}. "
            f"Crush predicted in {ttb_str} minutes. "
            f"Incident report has been sent to your "
            f"dashboard. "
            f"Deploy officers to Choke Point Bravo "
            f"immediately. "
            f"Alert ID {alert_id}. "
            f"This is an automated alert."
        ),
        "temple": (
            f"Urgent alert from Stampede Predictor System. "
            f"High crowd pressure at {corridor} temple. "
            f"Pressure Index {cpi_str}. "
            f"Crush risk in {ttb_str} minutes. "
            f"PDF report sent to your dashboard. "
            f"Activate darshan hold at inner gate "
            f"immediately. "
            f"Alert ID {alert_id}."
        ),
        "gsrtc": (
            f"Urgent alert from Stampede Predictor System. "
            f"{corridor} corridor is at critical capacity. "
            f"Pressure Index {cpi_str}. "
            f"Incident report sent to your dashboard. "
            f"Hold all incoming buses at the 3 kilometre "
            f"checkpoint now. "
            f"Do not dispatch additional vehicles. "
            f"Alert ID {alert_id}."
        ),
        "driver": (
            f"Attention bus driver. "
            f"Your destination {corridor} has critical "
            f"crowd pressure. "
            f"Pressure Index {cpi_str}. "
            f"Stop at the designated checkpoint immediately. "
            f"Do not proceed to temple area. "
            f"Alert ID {alert_id}."
        ),
    }
    
    return messages.get(role, messages["police"])

def make_single_call(
    to_number: str,
    role: str,
    corridor: str,
    cpi: float,
    ttb_minutes: float,
    alert_id: str
) -> dict:
    """Make one call to one number.
    Returns result dict — never raises exception."""
    
    # Validate number
    if not to_number:
        print(f"[CALL SKIP] {role} — number not set "
              f"(add DEMO_{role.upper()}_NUMBER to Render)")
        return {
            "status": "skipped",
            "reason": "number_not_configured",
            "role": role,
            "number": "NOT SET"
        }
    
    if not to_number.startswith("+"):
        print(f"[CALL SKIP] {role} — invalid number format "
              f"'{to_number}' (must start with + country code)")
        return {
            "status": "skipped",
            "reason": "invalid_number_format",
            "role": role,
            "number": to_number
        }
    
    # Check cooldown
    if is_on_cooldown(to_number):
        remaining = cooldown_remaining(to_number)
        print(f"[CALL SKIP] {role} — on cooldown "
              f"({remaining}s remaining)")
        return {
            "status": "skipped",
            "reason": "cooldown",
            "cooldown_remaining": remaining,
            "role": role,
            "number": to_number[:6] + "****"
        }
    
    # Mock mode if no Twilio client
    if not client:
        print(f"[CALL MOCK] {role} → {to_number[:6]}**** "
              f"(Twilio not configured)")
        msg = build_message(role, corridor, cpi, ttb_minutes, alert_id)
        return {
            "status": "mock",
            "reason": "twilio_not_configured",
            "role": role,
            "number": to_number[:6] + "****",
            "message_preview": msg[:80] + "..."
        }
    
    # Make actual Twilio call
    message = build_message(role, corridor, cpi, ttb_minutes, alert_id)
    twiml = f"""<?xml version="1.0" encoding="UTF-8"?>
<Response>
  <Say voice="alice" language="en-IN">{message}</Say>
  <Pause length="1"/>
  <Say voice="alice" language="en-IN">{message}</Say>
</Response>"""
    
    try:
        call = client.calls.create(
            to=to_number,
            from_=FROM_NUMBER,
            twiml=twiml,
            timeout=30
        )
        
        last_called[to_number] = time.time()
        print(f"[CALL OK] {role} → {to_number[:6]}**** "
              f"SID:{call.sid}")
        
        return {
            "status": "calling",
            "sid": call.sid,
            "role": role,
            "number": to_number[:6] + "****",
            "corridor": corridor,
            "cpi": cpi
        }
        
    except Exception as e:
        error_msg = str(e)
        print(f"[CALL ERROR] {role} → {to_number[:6]}****: "
              f"{error_msg}")
        
        # Common Twilio errors with helpful messages
        if "21608" in error_msg:
            reason = "number_not_verified_in_twilio_trial"
            print(f"  FIX: Verify {to_number} at "
                  f"twilio.com/console/phone-numbers/verified")
        elif "21211" in error_msg:
            reason = "invalid_phone_number"
        elif "21214" in error_msg:
            reason = "number_not_reachable"
        else:
            reason = error_msg[:100]
        
        return {
            "status": "error",
            "reason": reason,
            "role": role,
            "number": to_number[:6] + "****",
            "error": error_msg[:200]
        }

def trigger_corridor_calls(
    corridor: str,
    cpi: float,
    ttb_minutes: float,
    surge_type: str,
    alert_id: str
) -> list:
    """Call ALL registered agencies for a corridor alert.
    Each call is independent — one failure does NOT
    stop the others.
    Returns list of results for all roles."""
    
    results = []
    
    print(f"[CALLS] Starting calls for {corridor} "
          f"alert {alert_id}")
    print(f"[CALLS] CPI:{cpi:.3f} TTB:{ttb_minutes:.1f}min "
          f"Type:{surge_type}")
    
    # Loop ALL 3 roles — each gets independent call
    for role in ["police", "temple", "gsrtc"]:
        number = DEMO_NUMBERS.get(role, "")
        print(f"[CALLS] Processing {role} → "
              f"{'SET' if number else 'NOT SET'}")
        
        # Each call wrapped in try/except independently
        # One role failing must NOT affect others
        try:
            result = make_single_call(
                to_number=number,
                role=role,
                corridor=corridor,
                cpi=cpi,
                ttb_minutes=ttb_minutes,
                alert_id=alert_id
            )
            results.append(result)
        except Exception as e:
            print(f"[CALLS] Unexpected error for {role}: {e}")
            results.append({
                "status": "error",
                "role": role,
                "reason": str(e)
            })
    
    # Also call driver if configured
    driver_number = DEMO_NUMBERS.get("driver", "")
    if driver_number:
        try:
            result = make_single_call(
                to_number=driver_number,
                role="driver",
                corridor=corridor,
                cpi=cpi,
                ttb_minutes=ttb_minutes,
                alert_id=alert_id
            )
            results.append(result)
        except Exception as e:
            results.append({
                "status": "error",
                "role": "driver",
                "reason": str(e)
            })
    
    # Summary log
    called = [r for r in results if r["status"] == "calling"]
    skipped = [r for r in results if r["status"] == "skipped"]
    errors = [r for r in results if r["status"] == "error"]
    mocked = [r for r in results if r["status"] == "mock"]
    
    print(f"[CALLS DONE] Called:{len(called)} "
          f"Skipped:{len(skipped)} "
          f"Errors:{len(errors)} "
          f"Mock:{len(mocked)}")
    
    return results