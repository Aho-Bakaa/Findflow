# FindFlow Integration — Node.js backend ↔ Python engine

## Overview

```
POST /api/reports  (Node.js, port 3001)
  → db.save()
  → matcher.findMatches()
  → POST http://localhost:8001/triage   ← NEW (Python engine, missing only)
       returns Signal JSON
  → broadcast found_alert / report_added + triage_signal over WS

GET /api/zones/risk  (Node.js, port 3001)  ← NEW proxy endpoint
  → POST http://localhost:8001/zones/risk
       returns zone risk + Signal per zone
```

---

## Python engine

Start it alongside the Node.js server:

```bash
pip install -r requirements.txt
uvicorn findflow.api:app --port 8001
```

Endpoints:

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/health` | Liveness check |
| POST | `/triage` | #4 — triage a missing report, returns Signal |
| POST | `/zones/risk` | #5 — zone risk surface, returns Signal per zone |

---

## Changes needed in `server/server.js`

### 1 — Add triage call inside `POST /api/reports`

Find the existing handler and add the block marked `NEW`:

```js
app.post("/api/reports", writeLimiter, asyncHandler(async (req, res) => {
    validateReportPayload(req.body);
    const db = getDb();
    const saved = db.save(req.body);
    const corpus = db.list({ status: "open" }).map(withReportId);
    const matches = await findMatches(
        withReportId(saved),
        corpus,
        db.chokepoints(),
        { online: ONLINE_MATCHER, topN: 3 },
    );

    // ── NEW: call Python triage engine for missing reports ────────────────
    let triageSignal = null;
    if (saved.report_type === "missing") {
        try {
            const resp = await fetch("http://localhost:8001/triage", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify(saved),
                signal: AbortSignal.timeout(5000),
            });
            if (resp.ok) triageSignal = await resp.json();
        } catch (e) {
            logger.warn({ err: e.message }, "triage engine unavailable — floor fallback");
        }
    }
    // ─────────────────────────────────────────────────────────────────────

    if (saved.report_type === "found_unaccompanied") {
        broadcast({
            type: "found_alert",
            report: saved,
            suggested_matches: matches.map(m => ({ id: m.report.id, score: m.score })),
            t: new Date().toISOString(),
        });
    } else {
        broadcast({
            type: "report_added",
            report: saved,
            triage_signal: triageSignal,          // NEW — null if engine is down
            t: new Date().toISOString(),
        });
    }

    res.json({ report: saved, matches, triage_signal: triageSignal }); // NEW field
}));
```

### 2 — Add `/api/zones/risk` proxy endpoint

Add this route before the error middleware:

```js
app.post("/api/zones/risk", asyncHandler(async (req, res) => {
    const resp = await fetch("http://localhost:8001/zones/risk", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
            hour: req.body.hour ?? null,
            shahi_snan: req.body.shahi_snan ?? false,
        }),
        signal: AbortSignal.timeout(10000),
    });
    if (!resp.ok) throw new HttpError(502, "engine_error", "Python engine error");
    res.json(await resp.json());
}));
```

---

## Discrepancies resolved

| Discrepancy | Resolution |
|-------------|------------|
| Age band vocabulary mismatch | `preprocess._normalise_raw()` translates `child_0_5/child_6_12 → 0-12`, `teen → 13-17`, `adult → 18-40`, `elderly → 80+` before any validation |
| `mins_open` not stored in DB | `api.py` computes `(now − timestamp) / 60` at triage time |
| `high_risk_ctx` not stored | `api.py` derives it from `last_seen_location` matching our canonical ghat set |
| `found_unaccompanied` sent to triage | `POST /triage` returns HTTP 400 for non-missing types; server.js guards with `if (saved.report_type === "missing")` |
| #4 never triggered | Fixed by the `POST /triage` call in the report handler |
| #5 not queryable | Fixed by the `POST /api/zones/risk` proxy endpoint |

---

## Signal schema (what the Python engine returns)

Both `/triage` and `/zones/risk` return `Signal` objects:

```jsonc
{
  "type":        "alert" | "prediction",
  "ref":         "<report id or zone name>",
  "severity":    "OK" | "WARN" | "ESCALATE" | "CRITICAL",
  "description": "<line 1: situation>\n<line 2: response>",
  "actions":     ["action 1", "..."],
  "confidence":  0.85,
  "min_tier":    "ESCALATE",   // triage only; null for predictions
  "raised":      true,
  "model":       "claude-opus-4-8",
  "warnings":    ["..."]
}
```

The `severity` field is the one the dashboard/PA controller should act on.
