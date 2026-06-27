# FindFlow

Lost-person detection, coordination & dispatch for the **Nashik Kumbh Mela 2027**
(80M+ pilgrims). Connects a separated person — most often a child or an elder who
cannot ask for help — with the nearest booth / volunteer / police, and stops cases
from rotting unseen across isolated reporting centers.

## The five capabilities

| # | Capability | 
|---|------------|
| 1 | STT + multilingual intake (structured follow-ups) |
| 2 | Shared booth data pool (one fabric, all centers) | 
| 3 | Matching + verification (entity resolution, handover gate) |
| 4 | **Long-missing alerting** (vulnerability SLA + LLM escalation) |
| 5 | **Predictive alarm** (hotspot risk + volunteer pre-positioning) |

Acceptance criteria for #1–3 are in `docs/` (the team builds, we verify).
This repo implements **#4 and #5**.

---

## Architecture

```
DETERMINISTIC FLOOR (always runs, reproducible, ~0ms)
   #4 vulnerability-SLA timers   #5 structural risk surface
                    │
                    ▼
LLM REASONING LAYER (Anthropic Claude / DeepSeek V4 / vLLM / OpenRouter)
   raises urgency on context · narrates alarms · can only ADD, never suppress
                    │
                    ▼  unavailable → falls back to the floor (still safe)
              Signal JSON  (one fixed schema for all outputs)
```

**Safety invariant:** `severity = max(floor_tier, llm_tier)` — the LLM can never
lower urgency below what the deterministic rules already decided.

**LLM value-add:** The primary case is the *mislabel* problem — 416 of 2,500
historic cases have `age_band=18-40` but a description that says "child, crying".
The SLA floor under-triages these; the LLM layer, seeing the preprocessing warning,
correctly escalates.

---

## Input schema

### #4 — Case triage (`reasoning.triage`)

Raw case rows come from `data/missing_persons.csv` or live booth intake. They are
validated in `findflow/preprocess.py` before reaching the LLM.

```python
# schema.TriageInput  (what the LLM sees — already validated)
case_id:             str
age_band:            "0-12" | "13-17" | "18-40" | "41-60" | "61-70" | "71-80" | "80+"
                     → "unknown" if out-of-vocabulary (with a warning)
mins_open:           float   # minutes since reported; 0 if unknown
last_seen_location:  str     # free-text location from the case
high_risk_ctx:       bool    # ghat / Shahi Snan / surge context
has_phone:           bool    # guardian has a reachable mobile
language:            str     # volunteer routing
status:              str     # Pending | Unresolved | Transferred | open
physical_description:str
warnings:            list[str]  # deterministic preprocessing flags
```

**Preprocessing rules** (all issues become warnings, never crashes):

| Problem | Behaviour |
|---------|-----------|
| `age_band` out of vocabulary | → `"unknown"` + warning |
| `mins_open` negative | → clamped to 0 + warning |
| `mins_open` missing | → derived from `resolution_hours`; else 0 + warning |
| description says "child" but `age_band` is adult | warning (LLM must weigh; floor unchanged) |
| `status` not canonical | warning |

### #5 — Zone alarm (`reasoning.alarm_signal`)

```python
zone_name:    str           # e.g. "Zone 30 (Ramkund cluster)"
risk_score:   float 0–1    # from hotspot.build_risk_surface()
live_signals: dict          # optional runtime context:
                            #   hour: int 0-23
                            #   shahi_snan: bool
                            #   open_cases_last_hr: int
                            #   crowd_density: "low"|"moderate"|"high"|"very high"
```

**Risk score formula:**
```
base_risk = norm( 0.45 × choke_pressure
                + 0.35 × resp_eta_norm
                + 0.20 × cam_gap )

shift_risk = base_risk × time_multiplier(hour, shahi_snan)
```
`time_multiplier`: dawn 5–8am ×1.4–1.9, aarti 18–21 ×1.4–1.8, Shahi Snan day ×2.1.

---

## Output schema

**Every output — whether an alert or a prediction — is one fixed `Signal` JSON:**

```jsonc
{
  "type":        "alert" | "prediction",
  "ref":         "<case_id or zone name>",
  "severity":    "OK" | "WARN" | "ESCALATE" | "CRITICAL",
  "description": "<line 1: the situation>\n<line 2: the recommended response>",
  "actions":     ["concrete action 1", "action 2", "..."],
  "confidence":  0.0,           // float 0–1 from the reasoning layer
  "min_tier":    "ESCALATE",    // deterministic SLA floor (alerts only; null for predictions)
  "raised":      true,          // did LLM lift severity above min_tier?
  "model":       "claude-opus-4-8",
  "warnings":    ["preprocessing warning 1", "..."]
}
```

**`description` is always exactly two lines** (`\n`-separated). Downstream systems
(dispatch API, PA controller, dashboard) can consume this without parsing.

**`severity` bands for #5 predictions:**

| risk_score | severity |
|------------|----------|
| < 0.30 | OK |
| 0.30–0.59 | WARN |
| 0.60–0.79 | ESCALATE |
| ≥ 0.80 | CRITICAL |

---

## Layout

```
findflow/          importable package (core logic, no side effects)
  config.py        paths, crowd constants, LLM endpoint selection
  schema.py        TriageInput + Signal dataclasses; canonical vocabularies
  preprocess.py    raw-row → TriageInput validation (never raises)
  alerting.py      #4 deterministic SLA floor (floor_tier, classify)
  reasoning.py     LLM layer — triage() and alarm_signal(), both return Signal
  hotspot.py       #5 risk surface + volunteer allocation
  prompts.py       template loader / renderer
  prompts/         triage_system.txt  triage_user.txt
                   alarm_system.txt   alarm_user.txt
  geo.py           haversine + local metric projection
  kml.py           KML point parser
  data.py          dataset loaders
scripts/
  run_mock_triage.py   run all 6 hand-crafted cases + predictive alarm (offline-safe)
  run_triage.py        live run over historic CSV
  run_alerting.py      #4 SLA replay over 2,500 cases
  run_hotspot.py       #5 zone risk + volunteer allocation
tests/
  test_pipeline.py     9 tests, all offline (LLM_MOCK=1)
  mock_cases.py        6 hand-crafted open-status cases with expected tiers
analysis/
  signal_test.py       chi-square uniformity tests on the historic data
data/                  CSV + KML datasets
docs/SCHEMA.md         full field reference
```

---

## Quickstart

```bash
pip install -r requirements.txt

# offline — deterministic floor + mock LLM (no key needed)
python tests/test_pipeline.py          # 9/9 tests
python scripts/run_mock_triage.py      # 6 mock cases + zone alarm

# live — Anthropic Claude (default)
echo ANTHROPIC_API_KEY=<key> > .env
python scripts/run_triage.py

# live — open-source SOTA (DeepSeek V4 / vLLM / OpenRouter)
echo LLM_BASE_URL=https://api.deepseek.com/v1 >> .env
echo LLM_API_KEY=<deepseek-key> >> .env
echo LLM_MODEL=deepseek-chat >> .env
python scripts/run_triage.py
```

**Backend resolution order:** Anthropic → OpenAI-compatible → floor-only fallback.
Without any key the deterministic floor still runs and emits valid `Signal` JSON.

---


---

## Data

See **`docs/SCHEMA.md`** for the full field reference, the risk formula, and three
analytical caveats that shaped the design:
- Case location/time is statistically uniform (χ² p≈0.46) — #5 uses structural signals, not learned history.
- `is_duplicate_report` is random noise (36% twin ≈ 35% base) — not a trainable label.
- `physical_description` contradicts `age_band` in 416/2,500 cases — the LLM reconciles; the SLA floor trusts `age_band`.
