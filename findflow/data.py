"""Dataset loaders — return clean, typed DataFrames with derived fields.

These are the single source of truth for the schema used across #4 and #5.
See docs/SCHEMA.md for the field reference.
"""
import re
import pandas as pd

from . import config as C
from .kml import parse_points

_RISK_NUM = {"very high": 4, "high": 3, "medium": 2, "low": 1}


# ── #4 — Missing-person cases ─────────────────────────────────────────────────
def load_cases() -> pd.DataFrame:
    """Historic case records + derived alerting fields."""
    df = pd.read_csv(C.CASES_CSV)
    df["reported_at"] = pd.to_datetime(df["reported_at"])
    df["date"] = df["reported_at"].dt.date
    df["hour"] = df["reported_at"].dt.hour
    # derived signals used by the alerting layer
    df["has_phone"] = df["reporter_mobile"].notna()
    df["high_risk_ctx"] = (
        df["last_seen_location"].isin(C.HIGH_RISK_LOCATIONS)
        | df["date"].astype(str).isin(C.SHAHI_SNAN_DATES)
    )
    # open-duration: resolution_hours when present, else treated as still-open
    df["mins_open"] = (df["resolution_hours"] * 60)
    return df


# ── #5 — Spatial infrastructure ───────────────────────────────────────────────
def load_zones() -> pd.DataFrame:
    z = pd.read_csv(C.ZONES_CSV).rename(
        columns={"zone_name": "name", "centroid_lat": "lat", "centroid_lng": "lon"})
    return z


def load_cameras() -> pd.DataFrame:
    c = pd.read_csv(C.CAMERAS_CSV).rename(
        columns={"longitude": "lon", "latitude": "lat", "camera_id": "name"})
    c["zone"] = c["name"].str.extract(r"^Z(\d+)-").astype(float)
    return c


def load_police() -> pd.DataFrame:
    return parse_points(C.POLICE_KML)


def load_rrc() -> pd.DataFrame:
    """Rapid Response Cells (booth/dispatch grid) from the CCTV KML."""
    cctv = parse_points(C.CCTV_KML)
    return cctv[cctv["name"].str.match(r"^RRC\s", na=False)].reset_index(drop=True)


def load_responders() -> pd.DataFrame:
    """Unified dispatch endpoints = RRC booths + police stations."""
    rrc = load_rrc().assign(rtype="RRC")
    pol = load_police().assign(rtype="POLICE")
    return pd.concat([rrc, pol], ignore_index=True)


def load_chokepoints() -> pd.DataFrame:
    """Chokepoints/parking with parsed risk + category; bad coords dropped."""
    ch = parse_points(C.CHOKEPOINTS_KML)
    ch = ch[ch["lat"].between(C.LAT_MIN, C.LAT_MAX)].reset_index(drop=True)

    def _field(desc, key):
        m = re.search(rf"{key}:\s*([^|]+)", desc or "")
        return m.group(1).strip() if m else ""

    ch["category"] = ch["description"].apply(lambda d: _field(d, "Category"))
    ch["risk"] = ch["description"].apply(lambda d: _field(d, "Risk") or "medium")
    ch["risk_num"] = ch["risk"].map(_RISK_NUM).fillna(2)
    return ch
