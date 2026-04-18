"""
Historical incident data and seasonal prediction engine for TS-11.
"""
from datetime import datetime, timezone
from typing import Optional

HISTORICAL_DATA = [
    {
        "year": 2023,
        "event": "Navratri",
        "corridor": "Ambaji",
        "date_label": "Ashtami (Oct 22)",
        "peak_time": "19:30-21:00",
        "peak_cpi": 0.91,
        "surge_type": "GENUINE_CRUSH",
        "incident": "Near-stampede at North Gate. 4000 pilgrims in 3m corridor.",
        "action_taken": "Police deployed 20 officers. Gate closed 18 min.",
        "pilgrims_affected": 4200,
        "buses_held": 12,
        "resolution_time_minutes": 23,
    },
    {
        "year": 2023,
        "event": "Navratri",
        "corridor": "Ambaji",
        "date_label": "Navami (Oct 23)",
        "peak_time": "20:00-21:30",
        "peak_cpi": 0.87,
        "surge_type": "GENUINE_CRUSH",
        "incident": "Surge at East Corridor. Self-resolved after bus hold.",
        "action_taken": "GSRTC held 8 buses. Pressure reduced in 15 min.",
        "pilgrims_affected": 3100,
        "buses_held": 8,
        "resolution_time_minutes": 15,
    },
    {
        "year": 2022,
        "event": "Navratri",
        "corridor": "Dwarka",
        "date_label": "Ashtami (Oct 3)",
        "peak_time": "18:45-20:15",
        "peak_cpi": 0.89,
        "surge_type": "GENUINE_CRUSH",
        "incident": "Heavy rush post Aarti. Main gate bottleneck.",
        "action_taken": "Darshan hold 25 min. Alternate route opened.",
        "pilgrims_affected": 2800,
        "buses_held": 6,
        "resolution_time_minutes": 25,
    },
    {
        "year": 2022,
        "event": "Navratri",
        "corridor": "Somnath",
        "date_label": "Saptami (Oct 2)",
        "peak_time": "19:00-20:00",
        "peak_cpi": 0.83,
        "surge_type": "SELF_RESOLVING",
        "incident": "Temporary surge. Resolved without intervention.",
        "action_taken": "Monitored only. No action required.",
        "pilgrims_affected": 1900,
        "buses_held": 0,
        "resolution_time_minutes": 12,
    },
    {
        "year": 2024,
        "event": "Navratri",
        "corridor": "Pavagadh",
        "date_label": "Ashtami (Oct 12)",
        "peak_time": "20:30-22:00",
        "peak_cpi": 0.93,
        "surge_type": "GENUINE_CRUSH",
        "incident": "Highest recorded CPI at Pavagadh. Ropeway closure caused overflow.",
        "action_taken": "Emergency protocol. All 3 agencies responded in 4 min.",
        "pilgrims_affected": 5600,
        "buses_held": 18,
        "resolution_time_minutes": 31,
    },
]


def _parse_peak_hours(peak_time: str):
    """Parse '19:30-21:00' → (19.5, 21.0) as float hours."""
    try:
        parts = peak_time.split("-")
        def to_float(t):
            h, m = t.strip().split(":")
            return int(h) + int(m) / 60
        return to_float(parts[0]), to_float(parts[1])
    except Exception:
        return None, None


def get_historical_for_corridor(corridor: str) -> list:
    return [d for d in HISTORICAL_DATA if d["corridor"] == corridor]


def get_seasonal_prediction(corridor: str, current_hour: Optional[int] = None) -> dict:
    if current_hour is None:
        current_hour = datetime.now(timezone.utc).hour

    incidents = get_historical_for_corridor(corridor)
    if not incidents:
        return {
            "corridor": corridor,
            "current_hour": current_hour,
            "historical_risk_score": 0.3,
            "prediction": "No historical data available for this corridor.",
            "recommendation": "Monitor standard protocols.",
            "similar_year": None,
            "probability_of_surge": 20,
            "expected_peak_time": "Unknown",
            "buses_to_hold_preemptively": 0,
        }

    # Find incidents where current hour falls within 2 hours of peak window
    matching = []
    for inc in incidents:
        start_h, end_h = _parse_peak_hours(inc["peak_time"])
        if start_h is None:
            continue
        # Check if current hour is within 2 hours before peak start
        if (start_h - 2) <= current_hour <= end_h:
            matching.append(inc)

    total_years = len(set(i["year"] for i in incidents))
    matching_years = len(set(i["year"] for i in matching))

    if matching:
        probability = min(95, int((matching_years / max(total_years, 1)) * 100))
        best = max(matching, key=lambda x: x["peak_cpi"])
        avg_cpi = sum(i["peak_cpi"] for i in matching) / len(matching)
        risk_score = round(avg_cpi * (probability / 100), 3)

        if probability >= 60:
            risk_label = "HIGH RISK"
        elif probability >= 35:
            risk_label = "MEDIUM RISK"
        else:
            risk_label = "LOW RISK"

        cpi_history_str = ", ".join(
            f"{i['year']}: {i['peak_cpi']}" for i in sorted(matching, key=lambda x: x["year"])
        )

        prediction_text = (
            f"{risk_label} — Historical data shows {corridor} experiences peak CPI "
            f"between {best['peak_time']} ({cpi_history_str}). "
            f"Current conditions match {best['year']} pattern."
        )

        avg_buses = int(sum(i["buses_held"] for i in matching) / len(matching))

        # Build recommendation from best historical action
        recommendation = (
            f"Pre-deploy police to North Gate by {int(best['peak_time'].split('-')[0].split(':')[0])}:00. "
            f"Brief GSRTC to hold buses from {best['peak_time'].split('-')[0]}. "
            f"Activate Queue C redirect system. "
            f"Based on {best['year']}: {best['action_taken']}"
        )

        return {
            "corridor": corridor,
            "current_hour": current_hour,
            "historical_risk_score": risk_score,
            "prediction": prediction_text,
            "recommendation": recommendation,
            "similar_year": best["year"],
            "probability_of_surge": probability,
            "expected_peak_time": best["peak_time"],
            "buses_to_hold_preemptively": avg_buses,
        }
    else:
        # No matching window — low risk
        avg_cpi = sum(i["peak_cpi"] for i in incidents) / len(incidents)
        return {
            "corridor": corridor,
            "current_hour": current_hour,
            "historical_risk_score": round(avg_cpi * 0.2, 3),
            "prediction": (
                f"LOW RISK — Current hour ({current_hour}:00) is outside historical peak windows for {corridor}. "
                f"Historical peaks occur at: {', '.join(set(i['peak_time'] for i in incidents))}."
            ),
            "recommendation": "Standard monitoring. No pre-emptive action required at this hour.",
            "similar_year": None,
            "probability_of_surge": 15,
            "expected_peak_time": incidents[0]["peak_time"] if incidents else "Unknown",
            "buses_to_hold_preemptively": 0,
        }
