"""#5 — Hotspot risk surface & volunteer pre-positioning.

Risk is built from STRUCTURAL signals (chokepoint pressure, responder-coverage
gap, camera density) modulated by a TIME-OF-DAY crowd-flow prior. It is NOT
learned from the historic case data, which we showed is spatiotemporally uniform.
"""
import math
import numpy as np
from scipy.spatial import cKDTree

from . import config as C
from .geo import to_meters

INFLUENCE_RADIUS_M = 2500   # chokepoints within this radius pressure a zone


def _project(df, lat0, lon0):
    xy = df.apply(lambda r: to_meters(r["lat"], r["lon"], lat0, lon0), axis=1)
    df = df.copy()
    df["x"] = [t[0] for t in xy]
    df["y"] = [t[1] for t in xy]
    return df


def _normalise(s):
    return (s - s.min()) / (s.max() - s.min() + 1e-9)


def time_multiplier(hour: int, shahi_snan: bool = False) -> float:
    """Crowd-flow prior: twin peaks at dawn bathing (5-8) and aarti (18-21)."""
    base = {0: .3, 1: .2, 2: .2, 3: .3, 4: .5, 5: 1.4, 6: 1.8, 7: 1.9, 8: 1.5,
            9: 1.2, 10: 1.1, 11: 1.1, 12: 1.3, 13: 1.2, 14: 1.1, 15: 1.2,
            16: 1.3, 17: 1.4, 18: 1.7, 19: 1.8, 20: 1.4, 21: 1.0, 22: .7, 23: .5}
    m = base.get(hour, 1.0)
    return m * 2.1 if shahi_snan else m


def build_risk_surface(zones, chokepoints, responders, cameras):
    """Return `zones` with base_risk + component columns added."""
    lat0, lon0 = zones["lat"].mean(), zones["lon"].mean()
    zones = _project(zones, lat0, lon0)
    chokepoints = _project(chokepoints, lat0, lon0)
    responders = _project(responders, lat0, lon0)
    cameras = _project(cameras, lat0, lon0)

    resp_tree = cKDTree(responders[["x", "y"]].values)
    cam_tree = cKDTree(cameras[["x", "y"]].values)
    choke_tree = cKDTree(chokepoints[["x", "y"]].values)

    pressure, eta, density = [], [], []
    for _, z in zones.iterrows():
        # chokepoint pressure (inverse-distance-weighted risk within radius)
        idxs = choke_tree.query_ball_point([z.x, z.y], r=INFLUENCE_RADIUS_M)
        if idxs:
            near = chokepoints.iloc[idxs]
            d = np.maximum(np.hypot(near.x - z.x, near.y - z.y), 50)
            pressure.append((near.risk_num.values / d).sum())
        else:
            pressure.append(0.0)
        # responder ETA (minutes) and camera density (within 500 m)
        dist, _ = resp_tree.query([z.x, z.y], k=1)
        eta.append((dist * C.CROWD_PATH_FACTOR) / C.RESPONDER_SPEED_MPS / 60)
        density.append(len(cam_tree.query_ball_point([z.x, z.y], r=500)))

    zones["choke_pressure"] = pressure
    zones["resp_eta_min"] = eta
    zones["cam_density"] = density
    zones["cam_gap"] = 1 / (zones["cam_density"] + 1)

    zones["base_risk"] = _normalise(
        _normalise(zones["choke_pressure"]) * 0.45
        + _normalise(zones["resp_eta_min"]) * 0.35
        + _normalise(zones["cam_gap"]) * 0.20
    )
    return zones


def allocate(zones, total_volunteers: int, hour_start: int, hour_end: int,
             shahi_snan: bool = False):
    """Allocate `total_volunteers` across zones proportional to time-weighted risk."""
    mult = np.mean([time_multiplier(h, shahi_snan)
                    for h in range(hour_start, hour_end + 1)])
    risk = zones["base_risk"].values * mult
    alloc = np.round(total_volunteers * risk / risk.sum()).astype(int)
    out = zones[["name", "base_risk"]].copy()
    out["shift_risk"] = risk
    out["volunteers"] = alloc
    return out.sort_values("volunteers", ascending=False).reset_index(drop=True)
