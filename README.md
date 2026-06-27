# Findflow — Found-First Missing Persons System

> Real-time, offline-first console for lost-and-found operators at the
> Nashik–Trimbakeshwar Kumbh Mela. Prioritises **Found-First** reporting:
> an operator can register an unaccompanied child in seconds and broadcast
> an alert to every booth, while a description+geo matcher surfaces likely
> parent reports in the same instant.

---

## Architecture

- **Runtime**: Node 20 + Express + `ws` WebSocket (ES modules)
- **Datastore**: `better-sqlite3` with a JSON-file fallback (auto-detects). Seeds from CSV on first boot.
- **Matcher**: offline TF-IDF/Jaccard text + Haversine geo + gender/age hard gate. Optional Gemini embeddings blend when `MATCHER_ONLINE=1`.
- **Deployment**: multi-stage Docker image, non-root user, healthcheck on `/api/health`.

## Repo layout

```
data/         Synthetic CSVs (2500-row persons set with 100 ground-truth duplicate pairs)
              + generate_datasets.py to regenerate them
server/       Express + WebSocket backend, matcher, benchmark
Dockerfile    Multi-stage Alpine image
```

## REST + WebSocket API

| Method | Path                            | Notes                                                     |
|--------|---------------------------------|-----------------------------------------------------------|
| GET    | `/api/health`                   | `{ ok, backend, sockets, stats }`                         |
| GET    | `/api/booths`                   | Chokepoints + parking + booth coordinates                 |
| GET    | `/api/zones`                    | Zone adjacency map                                        |
| GET    | `/api/reports`                  | Query: `status`, `type`, `limit`                          |
| GET    | `/api/reports/:id`              | Single report                                             |
| POST   | `/api/reports`                  | Validated + rate-limited; returns `{ report, matches[] }` |
| POST   | `/api/reports/:id/match`        | Marks both reports as `matched`                           |
| POST   | `/api/reports/:id/resolve`      | Marks both reports as `resolved`                          |
| POST   | `/api/match-suggest`            | Preview matches without persisting                        |
| WS     | `ws://<host>:3001`              | `found_alert`, `report_added`, `report_matched`, `report_resolved` |

## Run locally

```bash
cd server
npm install --omit=optional   # JSON backend, no native build deps required
npm start                     # http://localhost:3001
npm run bench                 # 100-pair matcher benchmark
```

To use the SQLite backend instead of the JSON fallback, run `npm install`
with MSVC build tools available (Windows) or `apk add python3 make g++` first
(Alpine).

## Docker

```bash
docker build -t findflow-server .
docker run --rm -p 3001:3001 -e NODE_ENV=production findflow-server
```

For the SQLite-enabled image: `docker build --build-arg WITH_SQLITE=1 -t findflow-server .`

## Configuration

| Variable          | Default       | Purpose                                     |
|-------------------|---------------|---------------------------------------------|
| `PORT`            | 3001          | HTTP + WebSocket port                       |
| `NODE_ENV`        | development   | `production` switches pino to JSON logs    |
| `LOG_LEVEL`       | debug / info  | pino log level                              |
| `MAX_PHOTO_BYTES` | 8 MiB         | Raw photo size limit (base64-aware)         |
| `MATCHER_ONLINE`  | 0             | Set to `1` to blend Gemini embeddings       |
| `GEMINI_API_KEY`  | unset         | Required only if `MATCHER_ONLINE=1`         |

## Matcher benchmark

`npm run bench` evaluates the matcher against the 100 ground-truth duplicate
pairs embedded in `data/Synthetic_Missing_Persons_2500.csv`.

| Metric            | Result   |
|-------------------|----------|
| Top-1 hit rate    | **96.0%** |
| Top-3 hit rate    | **99.0%** (target ≥ 80%) |
| Pairs evaluated   | 100      |
| Runtime           | ~0.4s    |

Scoring is a weighted blend:

```
final = 0.50 * description  +  0.20 * location  +  0.15 * gender
      + 0.10 * age_band     +  0.05 * time_window
```

Gender and age band are also hard gates — mismatches score zero before
weights apply.

## Production hardening

- Pino + pino-http structured logging (pretty in dev, JSON in prod)
- Schema validation on every write with detailed `400` errors
- Base64-aware photo size cap (default 8 MiB raw)
- `express-rate-limit`: 60 writes/min/IP, standard `RateLimit-*` headers
- Typed `HttpError` middleware; stack traces masked in production
- Graceful SIGTERM/SIGINT shutdown: closes WS, drains HTTP, flushes DB

## Status

Backend, data, matcher, and Docker image are complete. Frontend (operator
console) is the next phase and not yet present.
