"""#4 — Long-missing alerting: deterministic vulnerability-SLA floor.

This is the safety guarantee. It always runs, is fully reproducible, and sets a
MINIMUM urgency tier per case. The LLM reasoning layer (reasoning.py) may only
RAISE the tier above this floor, never lower it.
"""
import pandas as pd

# Tier ordering
TIER_RANK = {"OK": 0, "WARN": 1, "ESCALATE": 2, "CRITICAL": 3}
RANK_TIER = {v: k for k, v in TIER_RANK.items()}

# (warn, escalate, critical) thresholds in MINUTES open, by vulnerability.
# Tightest for those who cannot self-advocate: youngest children, oldest elders.
SLA = {
    "0-12":  (20, 40, 60),
    "13-17": (30, 60, 90),
    "80+":   (30, 60, 90),
    "71-80": (40, 80, 120),
    "61-70": (60, 120, 180),
    "41-60": (90, 180, 360),
    "18-40": (90, 180, 360),
}
_DEFAULT_SLA = (90, 180, 360)

# High-risk context (ghat / surge) shrinks every threshold to this fraction.
HIGH_RISK_TIGHTEN = 0.6

ESCALATION_ACTIONS = {
    "WARN":     "Notify zone head · widen cross-booth query",
    "ESCALATE": "Zone-wide PA announcement · alert adjacent zones",
    "CRITICAL": ("ALL-zone PA · police control room · child-protection protocol "
                 "· verification-gated handover"),
}

# resolution_hours is NaN for never-resolved cases -> treat as effectively infinite
OPEN_INF = 10 ** 9


def open_minutes(resolution_hours) -> float:
    """Minutes a case ran open; never-resolved -> OPEN_INF."""
    if pd.isna(resolution_hours):
        return OPEN_INF
    return resolution_hours * 60


def floor_tier(age_band: str, mins_open: float, high_risk_ctx: bool = False) -> str:
    """Deterministic minimum tier. Pure function of (age, time, context)."""
    warn, esc, crit = SLA.get(age_band, _DEFAULT_SLA)
    if high_risk_ctx:
        warn, esc, crit = warn * HIGH_RISK_TIGHTEN, esc * HIGH_RISK_TIGHTEN, crit * HIGH_RISK_TIGHTEN
    if mins_open >= crit:
        return "CRITICAL"
    if mins_open >= esc:
        return "ESCALATE"
    if mins_open >= warn:
        return "WARN"
    return "OK"


def risk_to_severity(score: float) -> str:
    """Map a #5 risk score (0-1) onto the shared severity vocabulary."""
    if score >= 0.75:
        return "CRITICAL"
    if score >= 0.50:
        return "ESCALATE"
    if score >= 0.25:
        return "WARN"
    return "OK"


def classify(cases: pd.DataFrame) -> pd.DataFrame:
    """Add `open_min` and `tier` columns by replaying the SLA over a case frame."""
    out = cases.copy()
    out["open_min"] = out["resolution_hours"].apply(open_minutes)
    out["tier"] = out.apply(
        lambda r: floor_tier(r["age_band"], r["open_min"], r.get("high_risk_ctx", False)),
        axis=1,
    )
    return out
