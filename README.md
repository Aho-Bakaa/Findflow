# FindFlow — Lost Person System, Nashik Kumbh Mela 2027

Real-time detection, coordination, and dispatch for separated persons across 80M+ pilgrims. A separated child or elder is located, matched, and reunited — without relying on anyone to walk to the right booth or make a phone call.

---

## Branches

| Branch | Contents | Who owns it |
|--------|----------|-------------|
| `master` | Merged codebase — Node.js backend + Python engine together | Both |
| `python-engine` | Python AI engine, FastAPI sidecar, kiosk frontend | This team (Anmol) |
| `nodejs-backend` | Express/SQLite backend, matching engine, WebSocket broadcast | Rohit's team |

**If you're running the full system:** clone `master`.  
**If you're working on the AI/kiosk layer only:** use `python-engine`.

---

## What it does

Five capabilities, split across two codebases:

| # | Capability | Where |
|---|-----------|-------|
| 1 | Voice intake — multilingual STT via ElevenLabs agent, structured follow-up, camera capture | `frontend/kiosk.html` |
| 2 | Shared booth data pool — SQLite with WebSocket broadcast across all centers | Node.js backend |
| 3 | Matching — entity resolution across open cases, handover gate | Node.js backend |
| 4 | **Long-missing alerting** — vulnerability SLA + LLM escalation | `findflow/` Python engine |
| 5 | **Predictive alarm** — hotspot risk surface + volunteer pre-positioning | `findflow/` Python engine |

The Python engine runs as a FastAPI sidecar (`port 8001`) that the Node.js backend calls after every new report.

---

## Architecture

```
Kiosk (browser)
  └─ ElevenLabs voice agent  ←→  operator speaks, agent collects details
       ├─ capture_missing_person_photo  (camera Flow A)
       ├─ capture_self_photo            (camera Flow B)
       └─ submit_report
             │
             ▼
      Node.js / Express  (port 3001)
        ├─ db.save()          → SQLite
        ├─ findMatches()      → entity resolution across open cases
        └─ POST /triage  ──► Python FastAPI sidecar  (port 8001)
                                  ├─ POST /triage      → #4 alert Signal
                                  └─ POST /zones/risk  → #5 prediction Signal
                                        │
                                 deterministic SLA floor
                                        │
                                 LLM reasoning layer (Claude / DeepSeek / floor-only)
                                        │
                                  Signal JSON  ──► WebSocket broadcast to all booths
```

**Safety invariant:** `severity = max(floor_tier, llm_tier)` — the LLM can only raise urgency, never lower it. If the LLM is down, the deterministic floor still emits valid Signal JSON.

---

## Kiosk (Feature #1)

A fullscreen single-page app served from `frontend/kiosk.html`. No build step — open in Chrome over `localhost`.

**Two camera flows built in:**
- **Flow A** — Operator reporting a missing person: agent asks if they have a photo → `capture_missing_person_photo` tool fires → camera overlay opens, 3-2-1 countdown, JPEG captured and stored in report payload
- **Flow B** — Lost person at the booth: `capture_self_photo` fires automatically → mirrored selfie preview, photo attached to record for identification

**To run the kiosk:**
```bash
py -m http.server 8080 --directory frontend
# open http://localhost:8080/kiosk.html in Chrome
```

**ElevenLabs agent setup** — the agent (`agent_1101kw43fhmafg7s5n8554ctygc9`) needs three **Client Tools** registered on the ElevenLabs dashboard:

| Tool name | Trigger | Parameters |
|-----------|---------|------------|
| `capture_missing_person_photo` | User confirms they have a photo | none |
| `capture_self_photo` | User says they are lost | none |
| `submit_report` | All details collected | name, gender, age_band, language, physical_description, last_seen_location, reporter_mobile |

---

## Python Engine (Features #4 and #5)

```
findflow/
  config.py       paths, crowd constants, LLM endpoint selection
  schema.py       TriageInput + Signal dataclasses
  preprocess.py   raw row → TriageInput (validates, never raises)
  alerting.py     #4 deterministic SLA floor
  reasoning.py    LLM layer — triage() and alarm_signal()
  hotspot.py      #5 risk surface + volunteer allocation
  api.py          FastAPI sidecar — exposes /triage and /zones/risk
  data.py         CSV loaders for all datasets
```

**Install and run:**
```bash
pip install -r requirements.txt

# Start the FastAPI sidecar (Node.js backend calls this)
uvicorn findflow.api:app --port 8001

# Offline test — deterministic floor + mock LLM, no API key needed
py tests/test_pipeline.py          # 9/9 tests
py scripts/run_mock_triage.py      # 6 hand-crafted cases + zone alarm
```

**LLM backend selection** (in `.env`):
```bash
# Option A — Anthropic Claude (default)
ANTHROPIC_API_KEY=sk-...

# Option B — DeepSeek / OpenRouter / any OpenAI-compatible endpoint
LLM_BASE_URL=https://api.deepseek.com/v1
LLM_API_KEY=...
LLM_MODEL=deepseek-chat
```
Without any key the deterministic floor runs and emits valid Signal JSON.

---

## Signal schema

Every output from the Python engine — alert or prediction — is one fixed JSON shape:

```jsonc
{
  "type":        "alert" | "prediction",
  "ref":         "<case_id or zone name>",
  "severity":    "OK" | "WARN" | "ESCALATE" | "CRITICAL",
  "description": "<situation>\n<recommended response>",
  "actions":     ["action 1", "action 2"],
  "confidence":  0.85,
  "min_tier":    "ESCALATE",   // SLA floor (alerts only; null for predictions)
  "raised":      true,         // did LLM lift above the floor?
  "model":       "claude-opus-4-8",
  "warnings":    ["preprocessing flags"]
}
```

---

## Node.js integration

The Node.js backend calls the Python sidecar in two places. Full diff is in `docs/integration.md`.

**After `db.save()` in `POST /api/reports`:**
```js
if (saved.report_type === "missing") {
  const resp = await fetch("http://localhost:8001/triage", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(saved),
    signal: AbortSignal.timeout(5000),
  });
  if (resp.ok) triageSignal = await resp.json();
}
```

**New proxy endpoint `GET /api/zones/risk`:**
```js
app.post("/api/zones/risk", asyncHandler(async (req, res) => {
  const resp = await fetch("http://localhost:8001/zones/risk", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ hour: req.body.hour ?? null, shahi_snan: req.body.shahi_snan ?? false }),
    signal: AbortSignal.timeout(10000),
  });
  res.json(await resp.json());
}));
```

If the Python sidecar is down, Node.js logs a warning and continues — `triage_signal` is `null` in the response, not an error.

---

## Running the full stack

```bash
# Terminal 1 — Node.js backend (Rohit's repo)
cd path/to/nodejs-backend
npm install && node server/server.js

# Terminal 2 — Python AI sidecar
cd path/to/Findflow
uvicorn findflow.api:app --port 8001

# Terminal 3 — Kiosk frontend
py -m http.server 8080 --directory frontend
```

Then open `http://localhost:8080/kiosk.html`.

---

## Data

`data/` holds five CSVs — 2,500 synthetic missing-person cases plus zone, CCTV, chokepoint, and police-station tables. See `docs/SCHEMA.md` for the full field reference.

Three analytical notes that shaped the design:
- Case locations are statistically uniform (χ² p≈0.46) — #5 uses structural signals, not learned history
- `is_duplicate_report` is random noise — not a trainable label
- `physical_description` contradicts `age_band` in 416 / 2,500 cases — the LLM reconciles; the SLA floor trusts `age_band`
