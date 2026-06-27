# Data Schema — Capabilities #4 (Alerting) & #5 (Predictive Alarm)

All loaders live in `findflow/data.py`. Raw → derived fields are listed below.

---

## #4 — Long-Missing Alerting

**Source:** `data/missing_persons.csv` (2,500 historic case records)
**Loader:** `load_cases()`

### Raw fields (per case)
| Field | Type | Used for |
|-------|------|----------|
| `case_id` | str | identity / dedup key |
| `reported_at` | datetime | open-duration start, temporal context |
| `missing_person_name` | str (85% present) | matching (#3); not used by SLA |
| `gender` | str | matching / blocking |
| `age_band` | enum `0-12 … 80+` | **primary SLA driver** (vulnerability) |
| `state`, `district` | str | matching context |
| `language` | enum (10) | volunteer routing, LLM context |
| `last_seen_location` | str (20 places) | high-risk-context flag, dispatch |
| `reporting_center` | enum (10) | the A→B coordination signal |
| `reporter_mobile` | str (80% present) | → `has_phone` |
| `physical_description` | str (24 canned) | **LLM contradiction check** (noisy) |
| `status` | enum `Reunited/Pending/Unresolved/Transferred` | resolution outcome |
| `resolution_hours` | float (NaN if open) | → `mins_open` |
| `is_duplicate_report` | bool | dedup KPI (flag is noise — see analysis) |
| `remarks` | str | channel used (PA / app) |

### Derived fields (computed in `load_cases()`)
| Field | Rule |
|-------|------|
| `has_phone` | `reporter_mobile` is present |
| `high_risk_ctx` | `last_seen_location ∈ HIGH_RISK_LOCATIONS` **or** date ∈ Shahi Snan |
| `mins_open` | `resolution_hours × 60` (NaN → treated as still-open) |
| `open_min` | `alerting.classify()`: NaN → `OPEN_INF` (auto-escalate) |
| `tier` | `alerting.floor_tier()` → `OK/WARN/ESCALATE/CRITICAL` |

### Reasoning-layer input (`reasoning.triage()`)
`TriageInput` dataclass — see `findflow/schema.py`. Fields:
`case_id, age_band, mins_open, last_seen_location, high_risk_ctx,
has_phone, language, status, physical_description, warnings[]`

Returns `Signal` (see Output schema below).

---

## #5 — Predictive Alarm / Pre-positioning

**Sources & loaders:**
| File | Loader | Gives |
|------|--------|-------|
| `data/zones.csv` | `load_zones()` | `name, lat, lon` (32 zone centroids) |
| `data/chokepoints.kml` | `load_chokepoints()` | `name, lat, lon, category, risk, risk_num` |
| `data/cctv_locations.csv` | `load_cameras()` | `name, lat, lon, zone` (1,280 cameras) |
| `data/cctv.kml` (RRC) + `police_stations.kml` | `load_responders()` | `name, lat, lon, rtype` (599 RRC + 14 police) |

### Derived per-zone risk fields (`hotspot.build_risk_surface()`)
| Field | Meaning |
|-------|---------|
| `choke_pressure` | inverse-distance-weighted chokepoint risk within 2.5 km |
| `resp_eta_min` | crowd-walk ETA to nearest responder (min) |
| `cam_density` | cameras within 500 m |
| `cam_gap` | `1 / (cam_density + 1)` |
| `base_risk` | `norm(0.45·choke + 0.35·eta + 0.20·cam_gap)` ∈ [0,1] |

### Time / allocation
| Field | Source |
|-------|--------|
| `time_multiplier(hour, shahi_snan)` | crowd-flow prior (dawn + aarti peaks; ×2.1 on Shahi Snan) |
| `shift_risk` | `base_risk × time_multiplier` |
| `volunteers` | `total × shift_risk / Σ shift_risk` |

### Live signals (optional, fed to `reasoning.alarm_signal()`)
`hour, shahi_snan, open_cases_last_hr, crowd_density` — not in static data; supplied at runtime from the live system.

---

## Output schema — `Signal` (both #4 and #5)

Every output the system emits is a `Signal` dataclass (see `findflow/schema.py`):

```jsonc
{
  "type":        "alert" | "prediction",
  "ref":         "<case_id (alert) or zone name (prediction)>",
  "severity":    "OK" | "WARN" | "ESCALATE" | "CRITICAL",
  "description": "<line 1: situation>\n<line 2: recommended response>",
  "actions":     ["action 1", "action 2"],
  "confidence":  0.85,
  "min_tier":    "ESCALATE",   // deterministic SLA floor; null for predictions
  "raised":      true,         // LLM lifted above min_tier
  "model":       "claude-opus-4-8",
  "warnings":    ["age_band/description contradiction"]
}
```

**Invariant:** `severity >= min_tier` always (enforced in code, not by the LLM).
**`description`** is normalized to exactly two `\n`-separated lines.

---

## Preprocessing & validation pipeline (#4)

Raw rows never reach the LLM. The flow is:

```
raw row ──▶ preprocess.to_triage_input() ──▶ schema.TriageInput ──▶ reasoning.triage()
            (deterministic validate/normalize)   (typed, with warnings)   (LLM reasons only)
                                                                          └▶ schema.Signal
```

**`preprocess.to_triage_input(raw)`** — never raises; every problem becomes an explicit `warning`:
| Check | Behaviour |
|-------|-----------|
| `age_band` not in canonical set | → `"unknown"` + warning (floor uses default SLA) |
| `mins_open` missing | derive from `resolution_hours`; else 0 + warning |
| `mins_open` negative | clamp to 0 + warning |
| `status` not canonical | warning |
| description child-cue vs adult `age_band` | warning (LLM must weigh; floor unchanged) |
| missing strings/bools | safe defaults, no crash |

**`preprocess.validate_frame(df)`** → batch report `{total, clean, issues{}}`.
On the 2,500-row set: **1,775 clean**, 416 description/age conflicts, 376 unknown open-duration.

**Output validation** — `reasoning._valid_triage_output()` rejects any LLM JSON whose `urgency_tier` is out of vocabulary or whose `reasons`/`actions` aren't lists; invalid → floor fallback. The model is used for reasoning, never trusted for shape.

**Prompts** live in `findflow/prompts/*.txt` (`triage_system`, `triage_user`, `alarm_system`, `alarm_user`); variables are filled in Python via `string.Template`.

---

## Key analytical caveats (baked into the design)
- **Case location/time is statistically uniform** (χ² p≈0.46) → #5 risk uses *structural* signals, not learned history.
- **`is_duplicate_report` is random noise** (36% twin rate ≈ 35% base rate) → not a trainable label.
- **`physical_description` contradicts `age_band`** in places → the LLM layer reconciles; the SLA floor trusts `age_band`.
