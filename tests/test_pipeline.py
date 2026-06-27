"""End-to-end pipeline tests using the mock LLM backend (no API key needed).

Run:  python tests/test_pipeline.py     (plain asserts, exits non-zero on failure)
      pytest tests/                       (also works if pytest is installed)
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from findflow import config as C
C.LLM_MOCK = True   # force the deterministic mock backend for all tests

from findflow.preprocess import to_triage_input              # noqa: E402
from findflow.reasoning import (triage, alarm_signal,         # noqa: E402
                                _valid_triage_output, backend_mode)
from findflow.alerting import TIER_RANK                       # noqa: E402
from findflow.schema import VALID_SIGNAL_TYPES, VALID_TIERS   # noqa: E402
from mock_cases import MOCK_CASES                             # noqa: E402


def test_backend_is_mock():
    assert backend_mode() == "MOCK"


def test_preprocess_flags_issues():
    for c in MOCK_CASES:
        inp = to_triage_input(c["row"])
        if "expect_warning" in c:
            assert any(c["expect_warning"] in w for w in inp.warnings), \
                f"{c['label']}: missing warning {c['expect_warning']!r} ({inp.warnings})"


def test_floor_matches_expectation():
    for c in MOCK_CASES:
        s = triage(to_triage_input(c["row"]))
        assert s.min_tier == c["expect_floor"], \
            f"{c['label']}: floor {s.min_tier} != {c['expect_floor']}"


def test_invariant_never_below_floor():
    for c in MOCK_CASES:
        s = triage(to_triage_input(c["row"]))
        assert TIER_RANK[s.severity] >= TIER_RANK[s.min_tier], \
            f"{c['label']}: severity {s.severity} below floor {s.min_tier}"


def test_final_meets_minimum():
    for c in MOCK_CASES:
        s = triage(to_triage_input(c["row"]))
        assert TIER_RANK[s.severity] >= TIER_RANK[c["expect_final_min"]], \
            f"{c['label']}: severity {s.severity} < expected {c['expect_final_min']}"


def test_mislabel_case_is_raised():
    c = next(c for c in MOCK_CASES if c["row"]["case_id"] == "M2")
    s = triage(to_triage_input(c["row"]))
    assert s.raised and s.severity != "OK", \
        f"mislabel case not raised: {s.severity} (raised={s.raised})"


def test_signal_schema_is_fixed():
    """Every emitted Signal has the fixed shape: valid type/severity + 2-line desc."""
    signals = [triage(to_triage_input(c["row"])) for c in MOCK_CASES]
    signals.append(alarm_signal("Zone 30", 0.92, {"hour": 6, "shahi_snan": True}))
    for s in signals:
        assert s.type in VALID_SIGNAL_TYPES
        assert s.severity in VALID_TIERS
        assert isinstance(s.actions, list)
        assert 0.0 <= s.confidence <= 1.0
        assert len(s.description.split("\n")) == 2, \
            f"description not two lines: {s.description!r}"
        assert set(s.to_dict()) == {"type", "ref", "severity", "description",
                                    "actions", "confidence", "min_tier", "raised",
                                    "model", "warnings"}


def test_prediction_severity_from_score():
    assert alarm_signal("Z", 0.92, {}).severity == "CRITICAL"
    assert alarm_signal("Z", 0.10, {}).severity == "OK"


def test_output_validation_rejects_garbage():
    assert not _valid_triage_output({"urgency_tier": "BOGUS", "description": "x", "actions": []})
    assert not _valid_triage_output({"description": "x"})              # missing tier
    assert not _valid_triage_output({"urgency_tier": "WARN", "actions": []})  # no desc
    assert _valid_triage_output({"urgency_tier": "WARN", "description": "a\nb", "actions": []})


def _run():
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    passed = 0
    for t in tests:
        try:
            t(); print(f"  PASS  {t.__name__}"); passed += 1
        except AssertionError as e:
            print(f"  FAIL  {t.__name__}: {e}")
    print(f"\n{passed}/{len(tests)} passed")
    return passed == len(tests)


if __name__ == "__main__":
    print("=" * 64)
    print("FindFlow pipeline tests  (backend:", backend_mode(), ")")
    print("=" * 64)
    sys.exit(0 if _run() else 1)
