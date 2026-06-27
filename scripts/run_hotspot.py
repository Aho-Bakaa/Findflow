"""Demo: #5 hotspot risk surface + volunteer pre-positioning."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from findflow.data import load_zones, load_chokepoints, load_responders, load_cameras
from findflow.hotspot import build_risk_surface, allocate

SHIFTS = [(5, 8, "dawn_bathing"), (9, 14, "mid_morning"),
          (15, 17, "afternoon"), (18, 21, "aarti_evening")]
TOTAL_NORMAL = 200


def main():
    zones = build_risk_surface(
        load_zones(), load_chokepoints(), load_responders(), load_cameras())

    print("=" * 64)
    print("ZONE RISK (top 8 by base risk)")
    print("=" * 64)
    top = zones.nlargest(8, "base_risk")[
        ["name", "base_risk", "choke_pressure", "resp_eta_min", "cam_density"]]
    print(top.round(3).to_string(index=False))

    print("\n" + "=" * 64)
    print(f"VOLUNTEER ALLOCATION — dawn shift (normal {TOTAL_NORMAL} vs Shahi Snan)")
    print("=" * 64)
    normal = allocate(zones, TOTAL_NORMAL, 5, 8, shahi_snan=False)
    shahi = allocate(zones, int(TOTAL_NORMAL * 2.1), 5, 8, shahi_snan=True)
    merged = normal.merge(shahi[["name", "volunteers"]], on="name",
                          suffixes=("_normal", "_shahi"))
    for _, r in merged.head(8).iterrows():
        print(f"  {r['name']:14}  normal={r.volunteers_normal:3d}  "
              f"shahi={r.volunteers_shahi:3d}  (+{r.volunteers_shahi - r.volunteers_normal})")


if __name__ == "__main__":
    main()
