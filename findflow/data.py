"""Dataset loaders — return clean, typed DataFrames with derived fields.

Adapts the team's CSV schema (Synthetic_Missing_Persons_2500 etc.) to the
field names expected by findflow's alerting and hotspot modules.
See docs/SCHEMA.md for the full field reference.
"""
import pandas as pd
import numpy as np

from . import config as C

# Maps the team's 5-band age vocabulary to our 7-band SLA vocabulary.
# We lose the adult 41-60/61-70 split and the elderly 71-80 split — not in
# the new data. The SLA floor falls back to the 18-40 / 80+ tier respectively.
_BAND_MAP = {
    "child_0_5":  "0-12",
    "child_6_12": "0-12",
    "teen":       "13-17",
    "adult":      "18-40",
    "elderly":    "80+",
}


# ── #4 — Missing-person cases ─────────────────────────────────────────────────
def load_cases() -> pd.DataFrame:
    """Live case records + derived alerting fields."""
    df = pd.read_csv(C.CASES_CSV)

    # Normalise field names to what the alerting layer expects
    df = df.rename(columns={
        "report_id":   "case_id",
        "timestamp":   "reported_at",
        "name":        "missing_person_name",
    })

    df["reported_at"] = pd.to_datetime(df["reported_at"], utc=False)
    df["date"] = df["reported_at"].dt.date
    df["hour"] = df["reported_at"].dt.hour

    # Map 5-band vocabulary → our 7-band SLA vocabulary
    df["age_band"] = df["age_band"].map(_BAND_MAP).fillna("unknown")

    # Derived alerting signals
    df["has_phone"] = df["reporter_mobile"].notna()
    df["high_risk_ctx"] = (
        df["last_seen_location"].isin(C.HIGH_RISK_LOCATIONS)
        | df["date"].astype(str).isin(C.SHAHI_SNAN_DATES)
    )

    # Open duration: resolution_time_mins is already in minutes
    df["mins_open"] = pd.to_numeric(df["resolution_time_mins"], errors="coerce")

    # Keep only missing reports for triage (found_unaccompanied is the resolution side)
    df = df[df["report_type"] == "missing"].reset_index(drop=True)
    return df


# ── #5 — Spatial infrastructure ───────────────────────────────────────────────
def load_zones() -> pd.DataFrame:
    z = pd.read_csv(C.ZONES_CSV)
    z = z.rename(columns={
        "zone_name":   "name",
        "lat_center":  "lat",
        "lng_center":  "lon",
    })
    return z


def load_cameras() -> pd.DataFrame:
    c = pd.read_csv(C.CAMERAS_CSV)
    c = c.rename(columns={
        "cctv_id":       "name",
        "location_name": "description",
        "lng":           "lon",
    })
    return c


def load_chokepoints() -> pd.DataFrame:
    """Booths + chokepoints + parking. Derives risk_num from capacity."""
    ch = pd.read_csv(C.CHOKEPOINTS_CSV)
    ch = ch.rename(columns={"lng": "lon"})
    ch = ch[ch["lat"].between(C.LAT_MIN, C.LAT_MAX)].reset_index(drop=True)

    # Capacity → pressure proxy: quartile buckets 1-4
    cap = ch["capacity"].fillna(500)
    q = cap.quantile([0.25, 0.50, 0.75]).values
    ch["risk_num"] = np.select(
        [cap <= q[0], cap <= q[1], cap <= q[2]],
        [1, 2, 3],
        default=4,
    ).astype(float)
    return ch


def load_police() -> pd.DataFrame:
    p = pd.read_csv(C.POLICE_CSV)
    p = p.rename(columns={"lng": "lon"})
    return p


def load_responders() -> pd.DataFrame:
    """Dispatch endpoints: active booths (from Chokepoints_Parking) + police."""
    ch = load_chokepoints()
    booths = ch[ch["type"] == "booth"][["name", "lat", "lon"]].copy()
    booths["rtype"] = "BOOTH"

    pol = load_police()[["name", "lat", "lon"]].copy()
    pol["rtype"] = "POLICE"

    return pd.concat([booths, pol], ignore_index=True)
