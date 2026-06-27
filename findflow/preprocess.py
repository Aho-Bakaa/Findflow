"""Deterministic preprocessing & validation.

Turns a raw case row (dict or DataFrame row) into a validated `TriageInput`.
ALL data shaping happens here in Python — the LLM is never asked to parse,
coerce, or normalize. Problems become explicit `warnings`, never silent drops.
"""
import re
import pandas as pd

from . import config as C
from .schema import TriageInput, VALID_AGE_BANDS, VALID_STATUSES, ADULT_BANDS

# crude cues that a free-text description is about a child
_CHILD_CUES = re.compile(r"\b(child|baby|kid|girl|boy|infant|toddler|"
                         r"[1-9]\s*(?:-|to)?\s*1?[0-2]?\s*years?)\b", re.I)


def _as_float(v, default=None):
    try:
        f = float(v)
        return f if f == f else default  # NaN check
    except (TypeError, ValueError):
        return default


def _as_bool(v):
    if isinstance(v, bool):
        return v
    if v is None or (isinstance(v, float) and v != v):
        return False
    return str(v).strip().lower() in {"true", "1", "yes", "y"}


def _as_str(v):
    if v is None or (isinstance(v, float) and v != v):
        return ""
    return str(v).strip()


def to_triage_input(raw: dict) -> TriageInput:
    """Validate & normalize one case. Never raises — issues land in `warnings`."""
    warnings: list[str] = []

    # --- age band ---------------------------------------------------------
    age = _as_str(raw.get("age_band"))
    if age not in VALID_AGE_BANDS:
        warnings.append(f"unknown age_band {age!r}; default SLA applied")
        age = "unknown"

    # --- minutes open -----------------------------------------------------
    mins = _as_float(raw.get("mins_open"))
    if mins is None:
        rh = _as_float(raw.get("resolution_hours"))
        mins = rh * 60 if rh is not None else None
    if mins is None:
        warnings.append("mins_open unknown; treated as 0")
        mins = 0.0
    elif mins < 0:
        warnings.append(f"negative mins_open {mins}; clamped to 0")
        mins = 0.0

    # --- status -----------------------------------------------------------
    status = _as_str(raw.get("status")) or "open"
    if status not in VALID_STATUSES:
        warnings.append(f"unknown status {status!r}")

    # --- location & context ----------------------------------------------
    location = _as_str(raw.get("last_seen_location")) or "unknown"
    if "high_risk_ctx" in raw and raw.get("high_risk_ctx") is not None:
        high_risk = _as_bool(raw.get("high_risk_ctx"))
    else:
        high_risk = location in C.HIGH_RISK_LOCATIONS

    # --- phone ------------------------------------------------------------
    if "has_phone" in raw and raw.get("has_phone") is not None:
        has_phone = _as_bool(raw.get("has_phone"))
    else:
        has_phone = _as_str(raw.get("reporter_mobile")) != ""

    desc = _as_str(raw.get("physical_description"))

    # --- cross-field sanity: description vs age_band ----------------------
    if age in ADULT_BANDS and _CHILD_CUES.search(desc):
        warnings.append("description suggests a child but age_band is adult "
                        "(possible mislabel — LLM should weigh this)")

    return TriageInput(
        case_id=_as_str(raw.get("case_id")) or "unknown",
        age_band=age, mins_open=mins, last_seen_location=location,
        high_risk_ctx=high_risk, has_phone=has_phone,
        language=_as_str(raw.get("language")) or "unknown",
        status=status, physical_description=desc or "n/a",
        warnings=warnings,
    )


def validate_frame(df: pd.DataFrame) -> dict:
    """Batch validation summary — counts of each issue across a case frame."""
    inputs = [to_triage_input(r) for r in df.to_dict("records")]
    issues: dict[str, int] = {}
    for inp in inputs:
        for w in inp.warnings:
            key = w.split(";")[0].split("(")[0].strip()
            issues[key] = issues.get(key, 0) + 1
    return {"total": len(inputs),
            "clean": sum(i.is_clean for i in inputs),
            "issues": dict(sorted(issues.items(), key=lambda kv: -kv[1]))}
