"""Demo: #4 deterministic alerting replay over the historic case set."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from findflow.data import load_cases
from findflow.alerting import classify, ESCALATION_ACTIONS, OPEN_INF


def main():
    cases = classify(load_cases())
    tiers = ["OK", "WARN", "ESCALATE", "CRITICAL"]
    counts = cases["tier"].value_counts().reindex(tiers, fill_value=0)

    print("=" * 64)
    print(f"ALERTING REPLAY — {len(cases)} cases vs vulnerability SLAs")
    print("=" * 64)
    for t in tiers:
        print(f"  {t:9}: {counts[t]:4d}  ({100*counts[t]/len(cases):4.1f}%)")

    breached = counts["WARN"] + counts["ESCALATE"] + counts["CRITICAL"]
    print(f"\n  Breaching SLA (alert fires): {breached} ({100*breached/len(cases):.1f}%)")
    print(f"  Never cleanly resolved (auto-escalate): "
          f"{int((cases['open_min'] >= OPEN_INF).sum())}")

    print("\n  Breach rate by age band:")
    xt = cases.assign(breach=cases.tier != "OK").groupby("age_band")["breach"].mean()
    for ab, rate in xt.sort_index().items():
        print(f"    {ab:6}: {100*rate:.1f}%")

    print("\n  Escalation actions:")
    for t in ("WARN", "ESCALATE", "CRITICAL"):
        print(f"    [{t}] {counts[t]:4d} -> {ESCALATION_ACTIONS[t]}")


if __name__ == "__main__":
    main()
