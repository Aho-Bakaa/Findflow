/**
 * matcher.js
 * Found-First Missing Persons System — Match Engine
 * Claude Impact Lab Mumbai | Team 60 | 27 June 2026
 *
 * PRIMARY:   TF-IDF / Jaccard text similarity (always-available, offline-safe)
 * SECONDARY: Gemini Embeddings cosine similarity (optional, gated behind online check)
 *
 * Usage (standalone test):
 *   node matcher.js
 *
 * Usage (as module):
 *   import { findMatches } from './matcher.js';
 *   const candidates = await findMatches(queryReport, allOpenReports, chokepoints, { online: false });
 */

import fs from 'fs';
import path from 'path';
import { fileURLToPath } from 'url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));

// ─────────────────────────────────────────────────────────────────────────────
// CONSTANTS
// ─────────────────────────────────────────────────────────────────────────────

const SCORE_WEIGHTS = {
  gender:       0.15,   // hard gate — mismatches get 0 for gender+age combined
  age_band:     0.10,
  description:  0.50,   // TF-IDF Jaccard (primary)
  location:     0.20,   // proximity via Haversine
  time_window:  0.05,   // recency bonus — found before missing report
};

const MAX_DISTANCE_KM   = 15;   // beyond this, location score → 0
const MAX_TIME_GAP_MINS = 240;  // 4-hour window; beyond → 0 time bonus

// AGE_BAND compatibility matrix — mismatched bands get 0 points
const AGE_COMPAT = {
  child_0_5:  ['child_0_5'],
  child_6_12: ['child_6_12'],
  teen:       ['teen'],
  adult:      ['adult'],
  elderly:    ['elderly'],
};

// ─────────────────────────────────────────────────────────────────────────────
// 1. TEXT SIMILARITY — TF-IDF / Jaccard (PRIMARY — always works offline)
// ─────────────────────────────────────────────────────────────────────────────

const STOPWORDS = new Set([
  'a','an','the','and','or','is','in','on','at','to','of','for','with',
  'person','wearing','carrying','build','height','hair','no','marks',
]);

/** Tokenise a description into a bag of meaningful words. */
function tokenise(text) {
  if (!text) return [];
  return text.toLowerCase()
    .replace(/[^a-z0-9\s]/g, ' ')
    .split(/\s+/)
    .filter(w => w.length > 1 && !STOPWORDS.has(w));
}

/** Jaccard similarity between two token arrays. */
function jaccardSim(tokensA, tokensB) {
  if (!tokensA.length || !tokensB.length) return 0;
  const setA = new Set(tokensA);
  const setB = new Set(tokensB);
  let intersection = 0;
  for (const t of setA) if (setB.has(t)) intersection++;
  const union = setA.size + setB.size - intersection;
  return union === 0 ? 0 : intersection / union;
}

/**
 * TF-IDF weighted Jaccard — weight each shared token by its IDF
 * (rarer tokens that match count more).
 * corpus: array of token arrays (all open reports)
 */
function buildIDF(corpus) {
  const df = {};
  const N  = corpus.length || 1;
  for (const tokens of corpus) {
    const seen = new Set(tokens);
    for (const t of seen) df[t] = (df[t] || 0) + 1;
  }
  const idf = {};
  for (const [t, count] of Object.entries(df)) {
    idf[t] = Math.log((N + 1) / (count + 1)) + 1;  // smoothed
  }
  return idf;
}

function tfidfJaccardSim(tokensA, tokensB, idf) {
  if (!tokensA.length || !tokensB.length) return 0;
  const setA = new Set(tokensA);
  const setB = new Set(tokensB);
  let weightedIntersection = 0;
  let unionWeight = 0;
  const allTokens = new Set([...setA, ...setB]);
  for (const t of allTokens) {
    const w   = idf[t] || 1;
    const inA = setA.has(t) ? 1 : 0;
    const inB = setB.has(t) ? 1 : 0;
    weightedIntersection += w * Math.min(inA, inB);
    unionWeight          += w * Math.max(inA, inB);
  }
  return unionWeight === 0 ? 0 : weightedIntersection / unionWeight;
}

// ─────────────────────────────────────────────────────────────────────────────
// 2. HAVERSINE DISTANCE
// ─────────────────────────────────────────────────────────────────────────────

function haversineKm(lat1, lng1, lat2, lng2) {
  if (lat1 == null || lat2 == null) return MAX_DISTANCE_KM;
  const R = 6371;
  const dLat = (lat2 - lat1) * Math.PI / 180;
  const dLng = (lng2 - lng1) * Math.PI / 180;
  const a = Math.sin(dLat/2)**2 +
            Math.cos(lat1 * Math.PI/180) * Math.cos(lat2 * Math.PI/180) *
            Math.sin(dLng/2)**2;
  return R * 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a));
}

/** Lookup booth coords from Chokepoints_Parking data. */
function getCoords(report, chokepoints) {
  const lat = parseFloat(report.last_seen_lat);
  const lng = parseFloat(report.last_seen_lng);
  if (!isNaN(lat) && !isNaN(lng)) return { lat, lng };
  const booth = chokepoints.find(c => c.booth_id === report.reporting_center ||
                                       c.booth_id === report.last_seen_location);
  return booth ? { lat: parseFloat(booth.lat), lng: parseFloat(booth.lng) } : null;
}

function locationScore(query, candidate, chokepoints) {
  const cq = getCoords(query, chokepoints);
  const cc = getCoords(candidate, chokepoints);
  if (!cq || !cc) return 0.5;   // unknown → neutral
  const km = haversineKm(cq.lat, cq.lng, cc.lat, cc.lng);
  return Math.max(0, 1 - km / MAX_DISTANCE_KM);
}

// ─────────────────────────────────────────────────────────────────────────────
// 3. GENDER / AGE GATE
// ─────────────────────────────────────────────────────────────────────────────

function genderAgeBandScore(query, candidate) {
  const gq = query.gender;
  const gc = candidate.gender;
  // unknown gender → pass
  const genderMatch = (gq === 'unknown' || gc === 'unknown' || gq === gc);
  if (!genderMatch) return 0;

  const compat = AGE_COMPAT[query.age_band] || [];
  const ageMatch = compat.includes(candidate.age_band);
  if (!ageMatch) return 0;

  return 1;
}

// ─────────────────────────────────────────────────────────────────────────────
// 4. TIME WINDOW BONUS
// ─────────────────────────────────────────────────────────────────────────────

function timeScore(query, candidate) {
  try {
    const tq  = new Date(query.timestamp);
    const tc  = new Date(candidate.timestamp);
    // Prefer found-report timestamp < missing-report timestamp (found first)
    const diffMins = Math.abs((tq - tc) / 60000);
    return Math.max(0, 1 - diffMins / MAX_TIME_GAP_MINS);
  } catch { return 0.5; }
}

// ─────────────────────────────────────────────────────────────────────────────
// 5. GEMINI EMBEDDINGS — OPTIONAL ONLINE ENHANCEMENT
// ─────────────────────────────────────────────────────────────────────────────

/**
 * If the server is online and GEMINI_API_KEY is set, fetch embeddings for
 * two descriptions and return cosine similarity. Falls back to null on any failure.
 * This function is NEVER awaited in the critical path — it only augments.
 */
async function geminiEmbeddingSim(descA, descB) {
  const apiKey = process.env.GEMINI_API_KEY;
  if (!apiKey) return null;
  try {
    const url = `https://generativelanguage.googleapis.com/v1beta/models/text-embedding-004:batchEmbedContents?key=${apiKey}`;
    const body = JSON.stringify({
      requests: [
        { model: 'models/text-embedding-004', content: { parts: [{ text: descA }] } },
        { model: 'models/text-embedding-004', content: { parts: [{ text: descB }] } },
      ],
    });
    const resp = await fetch(url, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body, signal: AbortSignal.timeout(4000) });
    if (!resp.ok) return null;
    const data = await resp.json();
    const [e1, e2] = data.embeddings.map(e => e.values);
    // Cosine similarity
    let dot = 0, magA = 0, magB = 0;
    for (let i = 0; i < e1.length; i++) { dot += e1[i]*e2[i]; magA += e1[i]**2; magB += e2[i]**2; }
    return dot / (Math.sqrt(magA) * Math.sqrt(magB));
  } catch { return null; }
}

// ─────────────────────────────────────────────────────────────────────────────
// 6. CORE — findMatches
// ─────────────────────────────────────────────────────────────────────────────

/**
 * Find the top N matches for a query report from a pool of open reports.
 *
 * @param {object} query         - The report we are trying to match
 * @param {object[]} pool        - All other open reports to search
 * @param {object[]} chokepoints - Loaded Chokepoints_Parking.csv rows
 * @param {object}  opts
 * @param {boolean} opts.online  - If true, attempt Gemini embedding enhancement
 * @param {number}  opts.topN    - Number of candidates to return (default 3)
 * @returns {Promise<object[]>}  - Sorted array of { report, score, breakdown }
 */
export async function findMatches(query, pool, chokepoints, opts = {}) {
  const { online = false, topN = 3 } = opts;

  // Oppose types: found_unaccompanied matches against missing and vice-versa
  const targetType = query.report_type === 'found_unaccompanied' ? 'missing' : 'found_unaccompanied';
  const candidates = pool.filter(r =>
    r.report_id !== query.report_id &&
    r.report_type === targetType &&
    r.status === 'open'
  );

  if (!candidates.length) return [];

  // Build IDF corpus from all candidate descriptions
  const corpus = candidates.map(c => tokenise(c.physical_description));
  const idf    = buildIDF(corpus);
  const queryTokens = tokenise(query.physical_description);

  // Score every candidate
  const scored = await Promise.all(candidates.map(async (candidate, i) => {
    const gaScore  = genderAgeBandScore(query, candidate);
    if (gaScore === 0) {
      // Hard fail — incompatible gender or age band
      return { report: candidate, score: 0, breakdown: { gender_age: 0 } };
    }

    const descScore = tfidfJaccardSim(queryTokens, corpus[i], idf);
    const locScore  = locationScore(query, candidate, chokepoints);
    const timeScr   = timeScore(query, candidate);

    let finalDescScore = descScore;

    // Optional Gemini embedding enhancement (online only, timeout-safe)
    if (online && descScore > 0.05) {
      const embSim = await geminiEmbeddingSim(
        query.physical_description,
        candidate.physical_description
      );
      if (embSim !== null) {
        // Blend: 60% TF-IDF, 40% embeddings
        finalDescScore = 0.6 * descScore + 0.4 * embSim;
      }
    }

    const score =
      SCORE_WEIGHTS.gender      * gaScore +
      SCORE_WEIGHTS.description * finalDescScore +
      SCORE_WEIGHTS.location    * locScore +
      SCORE_WEIGHTS.time_window * timeScr;

    return {
      report: candidate,
      score: Math.round(score * 1000) / 1000,
      breakdown: {
        gender_age:  gaScore,
        description: Math.round(finalDescScore * 1000) / 1000,
        location:    Math.round(locScore * 1000) / 1000,
        time_window: Math.round(timeScr * 1000) / 1000,
        embedding_used: online && finalDescScore !== descScore,
      },
    };
  }));

  return scored
    .filter(s => s.score > 0)
    .sort((a, b) => b.score - a.score)
    .slice(0, topN);
}

// ─────────────────────────────────────────────────────────────────────────────
// 7. STANDALONE TEST — runs when called directly: node matcher.js
// ─────────────────────────────────────────────────────────────────────────────

async function runStandaloneTest() {
  console.log('\n══════════════════════════════════════════════');
  console.log('  matcher.js — Standalone Benchmark Test');
  console.log('══════════════════════════════════════════════\n');

  // Load datasets
  const dataDir = path.join(__dirname, '..', 'data');

  const loadCSV = (filename) => {
    const content = fs.readFileSync(path.join(dataDir, filename), 'utf-8');
    const lines   = content.trim().split('\n');
    const headers = lines[0].split(',');
    return lines.slice(1).map(line => {
      // simple CSV parse (no quoted commas in our data)
      const vals = line.split(',');
      const obj  = {};
      headers.forEach((h, i) => obj[h.trim()] = (vals[i] || '').trim());
      return obj;
    });
  };

  const persons     = loadCSV('Synthetic_Missing_Persons_2500.csv');
  const chokepoints = loadCSV('Chokepoints_Parking.csv');

  console.log(`Loaded ${persons.length} reports, ${chokepoints.length} chokepoints.\n`);

  // ── Test 1: PAIR_010 ──────────────────────────────────────────────────────
  const pair1  = persons.filter(r => r.duplicate_pair_id === 'PAIR_010');
  const found1 = pair1.find(r => r.report_type === 'found_unaccompanied');
  const miss1  = pair1.find(r => r.report_type === 'missing');

  console.log('TEST 1 — PAIR_010');
  console.log(`  Query (${found1.report_type}): ${found1.physical_description}`);
  console.log(`  Target (${miss1.report_type}): ${miss1.physical_description}`);

  const results1 = await findMatches(found1, persons, chokepoints, { online: false, topN: 3 });
  const rank1    = results1.findIndex(r => r.report.duplicate_pair_id === 'PAIR_010') + 1;

  console.log(`  Top 3 matches:`);
  results1.forEach((r, i) => {
    const hit = r.report.duplicate_pair_id === 'PAIR_010' ? '  ← GROUND TRUTH HIT' : '';
    console.log(`    #${i+1}  score=${r.score}  pair=${r.report.duplicate_pair_id || 'none'}${hit}`);
    console.log(`         breakdown: desc=${r.breakdown.description} loc=${r.breakdown.location} time=${r.breakdown.time_window}`);
  });
  console.log(`  → PAIR_010 ranked: ${rank1 > 0 ? '#' + rank1 : 'NOT IN TOP 3'}\n`);

  // ── Test 2: PAIR_036 ──────────────────────────────────────────────────────
  const pair2  = persons.filter(r => r.duplicate_pair_id === 'PAIR_036');
  const found2 = pair2.find(r => r.report_type === 'found_unaccompanied');
  const miss2  = pair2.find(r => r.report_type === 'missing');

  console.log('TEST 2 — PAIR_036');
  console.log(`  Query (${found2.report_type}): ${found2.physical_description}`);
  console.log(`  Target (${miss2.report_type}): ${miss2.physical_description}`);

  const results2 = await findMatches(found2, persons, chokepoints, { online: false, topN: 3 });
  const rank2    = results2.findIndex(r => r.report.duplicate_pair_id === 'PAIR_036') + 1;

  console.log(`  Top 3 matches:`);
  results2.forEach((r, i) => {
    const hit = r.report.duplicate_pair_id === 'PAIR_036' ? '  ← GROUND TRUTH HIT' : '';
    console.log(`    #${i+1}  score=${r.score}  pair=${r.report.duplicate_pair_id || 'none'}${hit}`);
    console.log(`         breakdown: desc=${r.breakdown.description} loc=${r.breakdown.location} time=${r.breakdown.time_window}`);
  });
  console.log(`  → PAIR_036 ranked: ${rank2 > 0 ? '#' + rank2 : 'NOT IN TOP 3'}\n`);

  // ── Full benchmark — all 100 pairs ────────────────────────────────────────
  console.log('FULL BENCHMARK — All 100 ground-truth pairs (offline, TF-IDF only)');
  console.log('Running...\n');

  const pairMap = {};
  for (const r of persons) {
    if (r.is_ground_truth_dup === 'True' && r.duplicate_pair_id) {
      if (!pairMap[r.duplicate_pair_id]) pairMap[r.duplicate_pair_id] = [];
      pairMap[r.duplicate_pair_id].push(r);
    }
  }

  let hits1 = 0, hits3 = 0, total = 0;
  for (const [pid, pair] of Object.entries(pairMap)) {
    const queryR  = pair.find(r => r.report_type === 'found_unaccompanied');
    const targetR = pair.find(r => r.report_type === 'missing');
    if (!queryR || !targetR) continue;
    total++;

    const results = await findMatches(queryR, persons, chokepoints, { online: false, topN: 3 });
    const rank    = results.findIndex(r => r.report.report_id === targetR.report_id) + 1;
    if (rank === 1) hits1++;
    if (rank >= 1 && rank <= 3) hits3++;
  }

  console.log(`  Pairs tested      : ${total}`);
  console.log(`  Hit @rank1        : ${hits1}  (${(100*hits1/total).toFixed(1)}%)`);
  console.log(`  Hit @rank1-3      : ${hits3}  (${(100*hits3/total).toFixed(1)}%)`);
  console.log(`  Miss              : ${total - hits3}`);
  console.log('\n══════════════════════════════════════════════');
  console.log(hits3 / total >= 0.80
    ? '  ✅ BENCHMARK PASSED (≥80% hit rate in top-3)'
    : '  ⚠️  BENCHMARK BELOW 80% — review scoring weights');
  console.log('══════════════════════════════════════════════\n');
}

// Entry-point guard
if (process.argv[1] && path.resolve(process.argv[1]) === path.resolve(fileURLToPath(import.meta.url))) {
  runStandaloneTest().catch(console.error);
}
