"""Typed schema + canonical value sets for the reasoning layer.

`TriageInput`  — validated input handed to the LLM (built in preprocess.py).
`Signal`       — the ONE fixed output schema for everything the system emits,
                 whether it's an alert (#4) or a prediction (#5).
"""
import json
from dataclasses import asdict, dataclass, field
from typing import List, Optional

# Canonical vocabularies (anything outside these is flagged in preprocessing)
VALID_AGE_BANDS = ("0-12", "13-17", "18-40", "41-60", "61-70", "71-80", "80+")
VALID_STATUSES = ("Reunited", "Pending", "Unresolved", "Transferred to hospital",
                  "open", "matched", "resolved")
VALID_TIERS = ("OK", "WARN", "ESCALATE", "CRITICAL")
VALID_SIGNAL_TYPES = ("alert", "prediction")

# Age bands considered "adult" for the description-conflict heuristic
ADULT_BANDS = ("18-40", "41-60", "61-70")


@dataclass
class TriageInput:
    """Validated, preprocessed case — the only thing passed to the LLM."""
    case_id: str
    age_band: str            # canonical band or "unknown"
    mins_open: float
    last_seen_location: str
    high_risk_ctx: bool
    has_phone: bool
    language: str
    status: str
    physical_description: str
    warnings: List[str] = field(default_factory=list)

    @property
    def is_clean(self) -> bool:
        return not self.warnings


@dataclass
class Signal:
    """The fixed output schema. Same shape for an alert or a prediction.

    Fields:
      type        : "alert" (#4 triage) | "prediction" (#5 alarm)
      ref         : case_id (alert) or zone name (prediction)
      severity    : OK | WARN | ESCALATE | CRITICAL
      description : exactly two lines — line 1 the situation, line 2 the response
      actions     : concrete next steps
      confidence  : 0.0-1.0
      min_tier    : deterministic floor (alerts only; audit trail)
      raised      : did the reasoning layer lift severity above min_tier?
      model       : which backend produced it (mock / model id)
      warnings    : preprocessing warnings carried through
    """
    type: str
    ref: str
    severity: str
    description: str
    actions: List[str]
    confidence: float
    min_tier: Optional[str] = None
    raised: bool = False
    model: str = ""
    warnings: List[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=2)
