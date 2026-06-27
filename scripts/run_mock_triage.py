"""Run the triage pipeline over the hand-crafted mock OPEN cases.

Uses whatever backend is active (mock / DeepSeek / Anthropic). Prints each
emitted Signal as the fixed JSON schema.
"""
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))

from findflow.preprocess import to_triage_input
from findflow.reasoning import triage, alarm_signal, backend_mode
from mock_cases import MOCK_CASES


def main():
    print("=" * 72)
    print("FindFlow mock-case triage  |  backend:", backend_mode())
    print("=" * 72)
    for c in MOCK_CASES:
        signal = triage(to_triage_input(c["row"]))
        print(f"\n# {c['label']}")
        print(signal.to_json())

    print("\n" + "=" * 72)
    print("# predictive alarm")
    print(alarm_signal("Zone 30 (Ramkund cluster)", 0.92,
                       {"hour": 6, "shahi_snan": True,
                        "open_cases_last_hr": 14, "crowd_density": "very high"}).to_json())


if __name__ == "__main__":
    main()
