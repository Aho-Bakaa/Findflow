"""Demo: #4 reasoning-layer triage with preprocessing + validation.

Pipeline:  raw row  ->  preprocess.to_triage_input (validate)  ->  reasoning.triage
Emits the fixed Signal JSON schema. The LLM only sees validated fields and is
used for reasoning, not data shaping.
"""
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from findflow.data import load_cases
from findflow.preprocess import to_triage_input, validate_frame
from findflow.reasoning import triage, alarm_signal, backend_mode


def main():
    print("=" * 70)
    print("FindFlow triage  |  backend:", backend_mode())
    print("=" * 70)

    df = load_cases()

    report = validate_frame(df)
    print(f"\nVALIDATION  {report['clean']}/{report['total']} rows clean")
    for issue, n in report["issues"].items():
        print(f"  - {n:4d}  {issue}")

    picks = []
    picks += df[(df.age_band == "0-12") & df.high_risk_ctx].head(1).to_dict("records")
    picks += df[df.age_band == "80+"].head(1).to_dict("records")
    picks += df[df.age_band == "18-40"].head(1).to_dict("records")

    print("\n" + "=" * 70 + "\nTRIAGE (fixed Signal schema)\n" + "=" * 70)
    for raw in picks:
        signal = triage(to_triage_input(raw))
        print(signal.to_json())
        print("-" * 40)

    print("\n" + "=" * 70 + "\nPREDICTIVE ALARM\n" + "=" * 70)
    print(alarm_signal("Zone 30 (Ramkund cluster)", 0.92,
                       {"hour": 6, "shahi_snan": True,
                        "open_cases_last_hr": 14, "crowd_density": "very high"}).to_json())


if __name__ == "__main__":
    main()
