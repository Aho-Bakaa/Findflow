"""FindFlow Python microservice — exposes #4 triage and #5 zone risk over HTTP.

Node.js backend calls this after db.save() for every new missing report.
Run with:  uvicorn findflow.api:app --port 8001
"""
from __future__ import annotations

import datetime
from typing import Optional

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from . import config as C
from .data import load_zones, load_cameras, load_chokepoints, load_responders
from .hotspot import build_risk_surface, time_multiplier
from .preprocess import to_triage_input
from .reasoning import triage, alarm_signal
from .alerting import risk_to_severity

app = FastAPI(title="FindFlow Engine", version="1.0.0")


# ── Pydantic models matching the Node.js report schema ───────────────────────

class ReportIn(BaseModel):
    """Mirrors the Node.js db report object — only the fields we need."""
    id: str
    report_type: str                    # "missing" | "found_unaccompanied"
    timestamp: str                      # ISO-8601
    reporting_center: str
    gender: Optional[str] = "unknown"
    age_band: Optional[str] = None      # child_0_5 | child_6_12 | teen | adult | elderly
    age_estimate: Optional[int] = None
    language: Optional[str] = "unknown"
    physical_description: Optional[str] = ""
    last_seen_location: Optional[str] = ""
    last_seen_lat: Optional[float] = None
    last_seen_lng: Optional[float] = None
    reporter_mobile: Optional[str] = None
    status: Optional[str] = "open"


class ZoneRiskQuery(BaseModel):
    hour: Optional[int] = None          # defaults to current hour if omitted
    shahi_snan: bool = False


# ── Helpers ───────────────────────────────────────────────────────────────────

def _mins_open_from_timestamp(ts: str) -> float:
    """Compute minutes elapsed since the report timestamp."""
    try:
        reported = datetime.datetime.fromisoformat(ts.replace("Z", "+00:00"))
        if reported.tzinfo is None:
            reported = reported.replace(tzinfo=datetime.timezone.utc)
        now = datetime.datetime.now(datetime.timezone.utc)
        return max(0.0, (now - reported).total_seconds() / 60)
    except Exception:
        return 0.0


def _derive_high_risk(location: str, last_seen_lat: float | None,
                      last_seen_lng: float | None) -> bool:
    """Flag high-risk context from location name (matches our canonical set)."""
    if not location:
        return False
    return any(h.lower() in location.lower() for h in C.HIGH_RISK_LOCATIONS)


# ── Endpoints ─────────────────────────────────────────────────────────────────

@app.get("/health")
def health():
    return {"ok": True, "service": "findflow-python-engine"}


@app.post("/triage")
def triage_report(report: ReportIn):
    """
    Accepts a saved Node.js report (missing type only), runs the full
    #4 pipeline, returns a Signal JSON.

    Called by server.js after db.save() for report_type == "missing".
    """
    if report.report_type != "missing":
        raise HTTPException(status_code=400,
                            detail="triage only applies to missing reports")

    mins = _mins_open_from_timestamp(report.timestamp)
    high_risk = _derive_high_risk(
        report.last_seen_location or report.reporting_center,
        report.last_seen_lat,
        report.last_seen_lng,
    )

    raw = {
        "case_id":             report.id,
        "age_band":            report.age_band,
        "mins_open":           mins,
        "last_seen_location":  report.last_seen_location or report.reporting_center,
        "high_risk_ctx":       high_risk,
        "has_phone":           report.reporter_mobile is not None,
        "language":            report.language or "unknown",
        "status":              report.status or "open",
        "physical_description": report.physical_description or "",
    }

    inp = to_triage_input(raw)
    signal = triage(inp)
    return signal.to_dict()


@app.post("/zones/risk")
def zones_risk(query: ZoneRiskQuery = ZoneRiskQuery()):
    """
    Returns the current risk surface across all zones.
    Called by the dashboard or by server.js GET /api/zones/risk.

    hour defaults to the current UTC hour if not supplied.
    """
    hour = query.hour if query.hour is not None else datetime.datetime.utcnow().hour

    zones      = load_zones()
    cameras    = load_cameras()
    chokepoints = load_chokepoints()
    responders  = load_responders()

    zones = build_risk_surface(zones, chokepoints, responders, cameras)
    mult  = time_multiplier(hour, query.shahi_snan)

    results = []
    for _, z in zones.iterrows():
        shift_risk  = float(z["base_risk"]) * mult
        severity    = risk_to_severity(min(shift_risk, 1.0))
        sig = alarm_signal(
            zone_name  = str(z["name"]),
            risk_score = min(shift_risk, 1.0),
            live_signals = {"hour": hour, "shahi_snan": query.shahi_snan},
        )
        results.append({
            "zone":       str(z["name"]),
            "base_risk":  round(float(z["base_risk"]), 3),
            "shift_risk": round(shift_risk, 3),
            "severity":   severity,
            "signal":     sig.to_dict(),
        })

    results.sort(key=lambda r: r["shift_risk"], reverse=True)
    return {"hour": hour, "shahi_snan": query.shahi_snan, "zones": results}
