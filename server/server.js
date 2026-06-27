// server.js — Found-First Missing Persons System backend.
// Express REST + ws WebSocket broadcast for live "found unaccompanied" alerts.

import express from "express";
import cors from "cors";
import http from "http";
import { WebSocketServer } from "ws";
import pino from "pino";
import pinoHttp from "pino-http";
import rateLimit from "express-rate-limit";
import { initDb, getDb } from "./db.js";
import { findMatches } from "./matcher.js";

const PORT = Number(process.env.PORT) || 3001;
const NODE_ENV = process.env.NODE_ENV || "development";
const LOG_LEVEL = process.env.LOG_LEVEL || (NODE_ENV === "production" ? "info" : "debug");
const MAX_PHOTO_BYTES = Number(process.env.MAX_PHOTO_BYTES) || 8 * 1024 * 1024; // 8 MiB raw
const ONLINE_MATCHER = process.env.MATCHER_ONLINE === "1";

const logger = pino({
    level: LOG_LEVEL,
    transport: NODE_ENV === "production" ? undefined : {
        target: "pino-pretty",
        options: { translateTime: "SYS:HH:MM:ss.l", ignore: "pid,hostname" },
    },
});

const app = express();
app.disable("x-powered-by");
app.use(cors());
app.use(express.json({ limit: "12mb" })); // headroom for base64 photo + metadata
app.use(pinoHttp({ logger, autoLogging: { ignore: (req) => req.url === "/api/health" } }));

const server = http.createServer(app);
const wss = new WebSocketServer({ server });
const sockets = new Set();

wss.on("connection", (ws) => {
    sockets.add(ws);
    logger.debug({ open: sockets.size }, "ws connection opened");
    ws.on("close", () => { sockets.delete(ws); logger.debug({ open: sockets.size }, "ws connection closed"); });
    ws.on("error", (err) => { logger.warn({ err: err.message }, "ws error"); sockets.delete(ws); });
    ws.send(JSON.stringify({ type: "hello", t: new Date().toISOString() }));
});

function broadcast(msg) {
    const payload = JSON.stringify(msg);
    for (const ws of sockets) if (ws.readyState === 1) ws.send(payload);
}

// The matcher filters on `report_id`, but the DB stores reports under `id`.
const withReportId = (r) => (r ? { ...r, report_id: r.id } : r);

// ---------------------------------------------------------------------------
// Async handler wrapper + validation + custom errors
// ---------------------------------------------------------------------------
const asyncHandler = (fn) => (req, res, next) => Promise.resolve(fn(req, res, next)).catch(next);

class HttpError extends Error {
    constructor(status, code, message, details) {
        super(message);
        this.status = status;
        this.code = code;
        this.details = details;
    }
}

const VALID_REPORT_TYPES = new Set(["missing", "found_unaccompanied"]);
const VALID_GENDERS = new Set(["male", "female", "unknown"]);
const VALID_AGE_BANDS = new Set(["child_0_5", "child_6_12", "teen", "adult", "elderly"]);

function validateReportPayload(body) {
    const errs = [];
    if (!body || typeof body !== "object") errs.push("body must be an object");
    if (!VALID_REPORT_TYPES.has(body?.report_type)) errs.push("report_type must be 'missing' or 'found_unaccompanied'");
    if (!body?.reporting_center || typeof body.reporting_center !== "string") errs.push("reporting_center required");
    if (!body?.operator_id || typeof body.operator_id !== "string") errs.push("operator_id required");
    if (body?.gender && !VALID_GENDERS.has(body.gender)) errs.push(`gender must be one of ${[...VALID_GENDERS].join("|")}`);
    if (body?.age_band && !VALID_AGE_BANDS.has(body.age_band)) errs.push(`age_band must be one of ${[...VALID_AGE_BANDS].join("|")}`);
    if (!body?.physical_description || typeof body.physical_description !== "string" || body.physical_description.trim().length < 4) {
        errs.push("physical_description required (>= 4 chars)");
    }
    if (body?.photo_data) {
        if (typeof body.photo_data !== "string") errs.push("photo_data must be a base64 data URI string");
        else {
            // Approximate raw byte size from base64 length (every 4 base64 chars = 3 bytes)
            const b64 = body.photo_data.includes(",") ? body.photo_data.split(",", 2)[1] : body.photo_data;
            const approx = Math.ceil((b64.length * 3) / 4);
            if (approx > MAX_PHOTO_BYTES) {
                errs.push(`photo_data exceeds ${MAX_PHOTO_BYTES} bytes (got ~${approx})`);
            }
        }
    }
    if (errs.length) throw new HttpError(400, "invalid_payload", "Report failed validation", errs);
}

// ---------------------------------------------------------------------------
// Rate limiter — applied to write endpoints only
// ---------------------------------------------------------------------------
const writeLimiter = rateLimit({
    windowMs: 60 * 1000,
    limit: 60,                        // 60 writes/minute/IP — generous for booth operators
    standardHeaders: "draft-7",
    legacyHeaders: false,
    message: { error: "rate_limited", message: "Too many writes, slow down." },
});

// ---------------------------------------------------------------------------
// REST API
// ---------------------------------------------------------------------------
app.get("/api/health", (req, res) => {
    const db = getDb();
    res.json({ ok: true, backend: db.kind, sockets: sockets.size, stats: db.stats() });
});

app.get("/api/booths", (req, res) => res.json(getDb().chokepoints()));
app.get("/api/zones", (req, res) => res.json(getDb().zones()));

app.get("/api/reports", (req, res) => {
    const { status, type, limit } = req.query;
    const rows = getDb().list({ status, type });
    res.json(limit ? rows.slice(0, parseInt(limit, 10)) : rows);
});

app.get("/api/reports/:id", (req, res) => {
    const r = getDb().get(req.params.id);
    if (!r) throw new HttpError(404, "not_found", `report ${req.params.id} not found`);
    res.json(r);
});

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

    if (saved.report_type === "found_unaccompanied") {
        broadcast({
            type: "found_alert",
            report: saved,
            suggested_matches: matches.map(m => ({ id: m.report.id, score: m.score })),
            t: new Date().toISOString(),
        });
        req.log.info({ id: saved.id, booth: saved.reporting_center, matchCount: matches.length }, "found alert broadcast");
    } else {
        broadcast({ type: "report_added", report: saved, t: new Date().toISOString() });
        req.log.info({ id: saved.id, booth: saved.reporting_center, matchCount: matches.length }, "missing report saved");
    }

    res.json({ report: saved, matches });
}));

app.post("/api/reports/:id/match", writeLimiter, (req, res) => {
    const { candidateId } = req.body;
    if (!candidateId) throw new HttpError(400, "invalid_payload", "candidateId required");
    const db = getDb();
    if (!db.get(req.params.id)) throw new HttpError(404, "not_found", `report ${req.params.id} not found`);
    if (!db.get(candidateId)) throw new HttpError(404, "not_found", `report ${candidateId} not found`);
    const updated = db.markMatched(req.params.id, candidateId);
    broadcast({ type: "report_matched", a: req.params.id, b: candidateId });
    res.json({ report: updated });
});

app.post("/api/reports/:id/resolve", writeLimiter, (req, res) => {
    const { candidateId } = req.body;
    if (!candidateId) throw new HttpError(400, "invalid_payload", "candidateId required");
    const db = getDb();
    if (!db.get(req.params.id)) throw new HttpError(404, "not_found", `report ${req.params.id} not found`);
    if (!db.get(candidateId)) throw new HttpError(404, "not_found", `report ${candidateId} not found`);
    const result = db.resolve(req.params.id, candidateId);
    broadcast({ type: "report_resolved", a: req.params.id, b: candidateId });
    res.json(result);
});

app.post("/api/match-suggest", writeLimiter, asyncHandler(async (req, res) => {
    const db = getDb();
    const corpus = db.list({ status: "open" }).map(withReportId);
    const query = withReportId({ id: req.body.id || "QUERY_TMP", ...req.body });
    const matches = await findMatches(
        query,
        corpus,
        db.chokepoints(),
        { online: ONLINE_MATCHER, topN: req.body.limit ?? 5 },
    );
    res.json({ matches });
}));

// ---------------------------------------------------------------------------
// Error middleware — must be last
// ---------------------------------------------------------------------------
app.use((err, req, res, next) => {
    if (err instanceof HttpError) {
        req.log?.warn({ status: err.status, code: err.code, details: err.details }, err.message);
        return res.status(err.status).json({ error: err.code, message: err.message, details: err.details });
    }
    if (err?.type === "entity.too.large") {
        return res.status(413).json({ error: "payload_too_large", message: err.message });
    }
    req.log?.error({ err: err.message, stack: err.stack }, "unhandled error");
    res.status(500).json({ error: "internal_error", message: NODE_ENV === "production" ? "internal error" : err.message });
});

// ---------------------------------------------------------------------------
// Graceful shutdown
// ---------------------------------------------------------------------------
let shuttingDown = false;
function shutdown(signal) {
    if (shuttingDown) return;
    shuttingDown = true;
    logger.info({ signal }, "shutdown initiated");

    const force = setTimeout(() => {
        logger.warn("force-exit after 10s timeout");
        process.exit(1);
    }, 10_000).unref();

    // 1. Stop accepting new sockets, close existing ones cleanly
    for (const ws of sockets) {
        try { ws.close(1001, "server shutting down"); } catch (_) {}
    }
    wss.close(() => logger.debug("wss closed"));

    // 2. Close http server (waits for in-flight requests)
    server.close((err) => {
        if (err) logger.error({ err: err.message }, "http close error");
        else logger.debug("http server closed");
        // 3. Flush DB and exit
        try { getDb().close?.(); logger.info("db closed"); } catch (e) { logger.warn({ err: e.message }, "db close failed"); }
        clearTimeout(force);
        process.exit(0);
    });
}
process.on("SIGTERM", () => shutdown("SIGTERM"));
process.on("SIGINT", () => shutdown("SIGINT"));
process.on("uncaughtException", (err) => { logger.fatal({ err: err.message, stack: err.stack }, "uncaughtException"); shutdown("uncaughtException"); });
process.on("unhandledRejection", (reason) => { logger.error({ reason: String(reason) }, "unhandledRejection"); });

// ---------------------------------------------------------------------------
// Boot
// ---------------------------------------------------------------------------
(async () => {
    await initDb();
    server.listen(PORT, () => {
        logger.info({ port: PORT, env: NODE_ENV, online_matcher: ONLINE_MATCHER }, "server ready");
    });
})();
