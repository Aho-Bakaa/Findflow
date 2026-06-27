// db.js — shared report store for the Found-First Missing Persons System.
// Primary backend: better-sqlite3 (synchronous, zero-config on Windows once built).
// Fallback: single JSON file with a coarse-grained write lock — used only if the
// SQLite native module cannot load. Both backends expose the same surface.

import fs from "fs";
import path from "path";
import { fileURLToPath } from "url";
import { randomUUID } from "crypto";
import { parse as parseCsv } from "csv-parse/sync";

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const DATA_DIR = path.resolve(__dirname, "..", "data");
const SQLITE_PATH = path.join(__dirname, "reports.sqlite");
const JSON_PATH = path.join(__dirname, "reports.json");

const REPORT_FIELDS = [
    "id", "report_type", "timestamp", "reporting_center", "operator_id",
    "name", "gender", "age_band", "age_estimate", "language",
    "physical_description", "last_seen_location", "last_seen_lat", "last_seen_lng",
    "reporter_mobile", "photo_data", "status", "matched_report_id",
    "duplicate_pair_id", "is_ground_truth_dup", "synced",
    "created_at", "updated_at",
];

let backend = null;
let chokepoints = [];
let zones = [];

function loadCsv(file) {
    const p = path.join(DATA_DIR, file);
    if (!fs.existsSync(p)) return [];
    return parseCsv(fs.readFileSync(p, "utf-8"), { columns: true, skip_empty_lines: true });
}

function loadStaticTables() {
    chokepoints = loadCsv("Chokepoints_Parking.csv").map(r => ({
        ...r,
        lat: parseFloat(r.lat),
        lng: parseFloat(r.lng),
        capacity: parseInt(r.capacity, 10),
        is_active: String(r.is_active).toLowerCase() === "true",
    }));
    zones = loadCsv("Zone_Boundaries.csv").map(r => ({
        ...r,
        lat_center: parseFloat(r.lat_center),
        lng_center: parseFloat(r.lng_center),
        adjacent_zones: (r.adjacent_zones || "").split("|").filter(Boolean),
    }));
}

function nowIso() { return new Date().toISOString(); }

function normalizeIncoming(report) {
    const out = { ...report };
    out.id = out.id || `RPT_${randomUUID().slice(0, 8).toUpperCase()}`;
    out.timestamp = out.timestamp || nowIso();
    out.created_at = out.created_at || nowIso();
    out.updated_at = nowIso();
    out.status = out.status || "open";
    out.synced = out.synced === false ? 0 : 1;
    out.is_ground_truth_dup = out.is_ground_truth_dup ? 1 : 0;
    if (out.last_seen_lat !== undefined && out.last_seen_lat !== null && out.last_seen_lat !== "") {
        out.last_seen_lat = parseFloat(out.last_seen_lat);
    } else {
        out.last_seen_lat = null;
    }
    if (out.last_seen_lng !== undefined && out.last_seen_lng !== null && out.last_seen_lng !== "") {
        out.last_seen_lng = parseFloat(out.last_seen_lng);
    } else {
        out.last_seen_lng = null;
    }
    if (out.age_estimate !== undefined && out.age_estimate !== null && out.age_estimate !== "") {
        out.age_estimate = parseInt(out.age_estimate, 10);
    } else {
        out.age_estimate = null;
    }
    for (const f of REPORT_FIELDS) {
        if (!(f in out)) out[f] = null;
    }
    return out;
}

function seedFromCsv() {
    const rows = loadCsv("Synthetic_Missing_Persons_2500.csv");
    const booths = Object.fromEntries(chokepoints.map(c => [c.booth_id, c]));
    const seeded = rows.map(r => {
        const b = booths[r.reporting_center];
        const lat = r.last_seen_lat ? parseFloat(r.last_seen_lat) : (b ? b.lat : null);
        const lng = r.last_seen_lng ? parseFloat(r.last_seen_lng) : (b ? b.lng : null);
        return normalizeIncoming({
            id: r.report_id,
            report_type: r.report_type,
            timestamp: r.timestamp,
            reporting_center: r.reporting_center,
            operator_id: r.operator_id,
            name: r.name || null,
            gender: r.gender,
            age_band: r.age_band,
            age_estimate: r.age_estimate ? parseInt(r.age_estimate, 10) : null,
            language: r.language,
            physical_description: r.physical_description,
            last_seen_location: r.last_seen_location,
            last_seen_lat: lat,
            last_seen_lng: lng,
            reporter_mobile: r.reporter_mobile || null,
            photo_data: null,
            status: r.status || "open",
            matched_report_id: r.matched_report_id || null,
            duplicate_pair_id: r.duplicate_pair_id || null,
            is_ground_truth_dup: String(r.is_ground_truth_dup).toLowerCase() === "true",
            synced: 1,
            created_at: r.timestamp,
            updated_at: r.timestamp,
        });
    });
    return seeded;
}

// ---------------------------------------------------------------------------
// SQLite backend
// ---------------------------------------------------------------------------
async function trySqlite() {
    let Database;
    try {
        const mod = await import("better-sqlite3");
        Database = mod.default;
    } catch (e) {
        return null;
    }
    const db = new Database(SQLITE_PATH);
    db.pragma("journal_mode = WAL");
    db.exec(`
        CREATE TABLE IF NOT EXISTS reports (
            id TEXT PRIMARY KEY,
            report_type TEXT NOT NULL,
            timestamp TEXT,
            reporting_center TEXT,
            operator_id TEXT,
            name TEXT,
            gender TEXT,
            age_band TEXT,
            age_estimate INTEGER,
            language TEXT,
            physical_description TEXT,
            last_seen_location TEXT,
            last_seen_lat REAL,
            last_seen_lng REAL,
            reporter_mobile TEXT,
            photo_data TEXT,
            status TEXT NOT NULL DEFAULT 'open',
            matched_report_id TEXT,
            duplicate_pair_id TEXT,
            is_ground_truth_dup INTEGER DEFAULT 0,
            synced INTEGER DEFAULT 1,
            created_at TEXT,
            updated_at TEXT
        );
        CREATE INDEX IF NOT EXISTS idx_reports_type ON reports(report_type);
        CREATE INDEX IF NOT EXISTS idx_reports_status ON reports(status);
    `);

    const count = db.prepare("SELECT COUNT(*) AS n FROM reports").get().n;
    if (count === 0) {
        const insert = db.prepare(`
            INSERT INTO reports (${REPORT_FIELDS.join(",")})
            VALUES (${REPORT_FIELDS.map(f => "@" + f).join(",")})
        `);
        const txn = db.transaction((rows) => { for (const r of rows) insert.run(r); });
        const seed = seedFromCsv();
        txn(seed);
        console.log(`[db/sqlite] seeded ${seed.length} reports from CSV`);
    } else {
        console.log(`[db/sqlite] loaded ${count} existing reports`);
    }

    const insertStmt = db.prepare(`
        INSERT INTO reports (${REPORT_FIELDS.join(",")})
        VALUES (${REPORT_FIELDS.map(f => "@" + f).join(",")})
    `);
    const updateStmt = db.prepare(`
        UPDATE reports SET status=@status, matched_report_id=@matched_report_id, updated_at=@updated_at
        WHERE id=@id
    `);

    return {
        kind: "sqlite",
        save(report) {
            const norm = normalizeIncoming(report);
            insertStmt.run(norm);
            return norm;
        },
        list({ status, type } = {}) {
            let q = "SELECT * FROM reports";
            const where = [];
            const args = {};
            if (status) { where.push("status = @status"); args.status = status; }
            if (type)   { where.push("report_type = @type"); args.type = type; }
            if (where.length) q += " WHERE " + where.join(" AND ");
            q += " ORDER BY updated_at DESC LIMIT 5000";
            return db.prepare(q).all(args);
        },
        get(id) { return db.prepare("SELECT * FROM reports WHERE id = ?").get(id); },
        resolve(idA, idB) {
            const t = db.transaction(() => {
                updateStmt.run({ id: idA, status: "resolved", matched_report_id: idB, updated_at: nowIso() });
                updateStmt.run({ id: idB, status: "resolved", matched_report_id: idA, updated_at: nowIso() });
            });
            t();
            return { a: this.get(idA), b: this.get(idB) };
        },
        markMatched(idA, idB) {
            updateStmt.run({ id: idA, status: "matched", matched_report_id: idB, updated_at: nowIso() });
            return this.get(idA);
        },
        stats() {
            const rows = db.prepare(`
                SELECT report_type, status, COUNT(*) AS n FROM reports GROUP BY report_type, status
            `).all();
            return rows;
        },
        close: () => db.close(),
        chokepoints: () => chokepoints,
        zones: () => zones,
    };
}

// ---------------------------------------------------------------------------
// JSON fallback backend
// ---------------------------------------------------------------------------
function jsonBackend() {
    let store = { reports: [] };
    if (fs.existsSync(JSON_PATH)) {
        try { store = JSON.parse(fs.readFileSync(JSON_PATH, "utf-8")); } catch (_) {}
    }
    if (!store.reports || store.reports.length === 0) {
        store.reports = seedFromCsv();
        fs.writeFileSync(JSON_PATH, JSON.stringify(store, null, 2));
        console.log(`[db/json] seeded ${store.reports.length} reports from CSV`);
    } else {
        console.log(`[db/json] loaded ${store.reports.length} existing reports`);
    }

    let writePending = false;
    const flush = () => {
        if (writePending) return;
        writePending = true;
        setImmediate(() => {
            fs.writeFileSync(JSON_PATH, JSON.stringify(store, null, 2));
            writePending = false;
        });
    };
    const flushSync = () => {
        // Used by graceful-shutdown to guarantee on-disk state.
        fs.writeFileSync(JSON_PATH, JSON.stringify(store, null, 2));
        writePending = false;
    };

    return {
        kind: "json",
        save(report) {
            const norm = normalizeIncoming(report);
            store.reports.push(norm);
            flush();
            return norm;
        },
        list({ status, type } = {}) {
            return store.reports
                .filter(r => (!status || r.status === status) && (!type || r.report_type === type))
                .sort((a, b) => (b.updated_at || "").localeCompare(a.updated_at || ""))
                .slice(0, 5000);
        },
        get(id) { return store.reports.find(r => r.id === id); },
        resolve(idA, idB) {
            const a = store.reports.find(r => r.id === idA);
            const b = store.reports.find(r => r.id === idB);
            if (a) { a.status = "resolved"; a.matched_report_id = idB; a.updated_at = nowIso(); }
            if (b) { b.status = "resolved"; b.matched_report_id = idA; b.updated_at = nowIso(); }
            flush();
            return { a, b };
        },
        markMatched(idA, idB) {
            const a = store.reports.find(r => r.id === idA);
            if (a) { a.status = "matched"; a.matched_report_id = idB; a.updated_at = nowIso(); flush(); }
            return a;
        },
        stats() {
            const buckets = {};
            for (const r of store.reports) {
                const k = `${r.report_type}|${r.status}`;
                buckets[k] = (buckets[k] || 0) + 1;
            }
            return Object.entries(buckets).map(([k, n]) => {
                const [report_type, status] = k.split("|");
                return { report_type, status, n };
            });
        },
        close: flushSync,
        chokepoints: () => chokepoints,
        zones: () => zones,
    };
}

// ---------------------------------------------------------------------------
// Public API
// ---------------------------------------------------------------------------
export async function initDb() {
    loadStaticTables();
    backend = await trySqlite();
    if (!backend) {
        console.log("[db] better-sqlite3 unavailable, falling back to JSON file backend");
        backend = jsonBackend();
    } else {
        console.log("[db] using better-sqlite3 backend");
    }
    return backend;
}

export function getDb() {
    if (!backend) throw new Error("db not initialized — call initDb() first");
    return backend;
}
