// test_matcher.js — `npm run bench` entry point.
//
// Mirrors the matcher's own standalone test but is exposed as a stable script
// so CI / the user can run `npm run bench` and get a single PASS/FAIL exit code.
// For per-pair output and richer diagnostics, run `node matcher.js` directly.

import fs from "fs";
import path from "path";
import { fileURLToPath } from "url";
import { parse as parseCsv } from "csv-parse/sync";
import { findMatches } from "./matcher.js";

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const DATA_DIR = path.resolve(__dirname, "..", "data");

function loadCsv(file) {
    return parseCsv(fs.readFileSync(path.join(DATA_DIR, file), "utf-8"),
        { columns: true, skip_empty_lines: true });
}

async function main() {
    const topK = parseInt(process.argv[2] || "3", 10);
    const reports = loadCsv("Synthetic_Missing_Persons_2500.csv");
    const chokepoints = loadCsv("Chokepoints_Parking.csv");
    console.log(`[bench] loaded ${reports.length} reports, ${chokepoints.length} chokepoints`);

    // Group ground-truth dups into pairs by duplicate_pair_id
    const pairs = new Map();
    for (const r of reports) {
        if (String(r.is_ground_truth_dup).toLowerCase() !== "true") continue;
        if (!r.duplicate_pair_id) continue;
        if (!pairs.has(r.duplicate_pair_id)) pairs.set(r.duplicate_pair_id, {});
        pairs.get(r.duplicate_pair_id)[r.report_type] = r;
    }

    let total = 0, hits1 = 0, hitsK = 0;
    const t0 = Date.now();

    for (const [pid, pair] of pairs) {
        if (!pair.missing || !pair.found_unaccompanied) continue;
        total++;
        // Use the found-unaccompanied report as query (Flow A → matches against missing pool)
        const query = pair.found_unaccompanied;
        const target = pair.missing;
        const matches = await findMatches(query, reports, chokepoints, { online: false, topN: topK });
        const rank = matches.findIndex(m => m.report.report_id === target.report_id) + 1;
        if (rank === 1) hits1++;
        if (rank >= 1 && rank <= topK) hitsK++;
    }

    const elapsed = ((Date.now() - t0) / 1000).toFixed(2);
    const rate1 = (100 * hits1 / total).toFixed(1);
    const rateK = (100 * hitsK / total).toFixed(1);

    console.log(`\n=== Found-First Matcher Benchmark (top-${topK}) ===`);
    console.log(`Pairs evaluated      : ${total}`);
    console.log(`Top-1 hit rate       : ${rate1}%  (${hits1}/${total})`);
    console.log(`Top-${topK} hit rate       : ${rateK}%  (${hitsK}/${total})`);
    console.log(`Missed (not in top-${topK}) : ${total - hitsK}`);
    console.log(`Time                 : ${elapsed}s`);
    console.log(`Target               : >= 80% top-${topK}`);
    console.log(`Result               : ${parseFloat(rateK) >= 80 ? "PASS" : "FAIL"}`);

    process.exit(parseFloat(rateK) >= 80 ? 0 : 1);
}

main().catch(err => { console.error(err); process.exit(2); });
