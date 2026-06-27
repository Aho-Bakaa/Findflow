"""
generate_datasets.py
Generates all 5 organizer-spec CSVs for the Found-First Missing Persons System.
All data is synthetic / consented demo data — disclosed clearly in the demo.

Output files (written to ./  relative to this script):
  Chokepoints_Parking.csv
  Zone_Boundaries.csv
  CCTV_Locations.csv
  Police_Stations.csv
  Synthetic_Missing_Persons_2500.csv   <- 2500 rows, 8% (200) ground-truth dup pairs
"""

import csv, random, uuid, os
from datetime import datetime, timedelta

random.seed(42)
OUT = os.path.dirname(os.path.abspath(__file__))

# ---------------------------------------------------------------------------
# Real-world anchors: Nashik–Trimbakeshwar Kumbh area
# ---------------------------------------------------------------------------
BASE_LAT, BASE_LNG = 19.9975, 73.5360   # Trimbakeshwar centre

def jitter(base, r=0.025):
    return round(base + random.uniform(-r, r), 6)

# ---------------------------------------------------------------------------
# 1. Zones
# ---------------------------------------------------------------------------
ZONES = [
    {"zone_id": "ZA", "zone_name": "Ramkund Ghat",         "adj": "ZB|ZC", "lat": 19.9992, "lng": 73.7783},
    {"zone_id": "ZB", "zone_name": "Trimbak Temple Area",   "adj": "ZA|ZD", "lat": 19.9430, "lng": 73.5284},
    {"zone_id": "ZC", "zone_name": "Godavari Ghat North",   "adj": "ZA|ZD|ZE", "lat": 20.0050, "lng": 73.7700},
    {"zone_id": "ZD", "zone_name": "Nashik Central Mela",   "adj": "ZB|ZC|ZE|ZF", "lat": 20.0050, "lng": 73.7900},
    {"zone_id": "ZE", "zone_name": "Panchavati Area",       "adj": "ZC|ZD|ZF", "lat": 20.0110, "lng": 73.7780},
    {"zone_id": "ZF", "zone_name": "Parking Hub South",     "adj": "ZD|ZE", "lat": 19.9900, "lng": 73.7820},
]

def write_zones():
    path = os.path.join(OUT, "Zone_Boundaries.csv")
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["zone_id","zone_name","adjacent_zones","lat_center","lng_center"])
        for z in ZONES:
            w.writerow([z["zone_id"], z["zone_name"], z["adj"], z["lat"], z["lng"]])
    print(f"  [OK] Zone_Boundaries.csv — {len(ZONES)} zones")

# ---------------------------------------------------------------------------
# 2. Booths / Chokepoints / Parking
# ---------------------------------------------------------------------------
BOOTH_NAMES = [
    ("Ramkund Gate East","ZA"), ("Ramkund Gate West","ZA"), ("Ramkund Main Ghat","ZA"),
    ("Trimbak Temple North","ZB"), ("Trimbak Temple South","ZB"),
    ("Godavari Ghat Booth 1","ZC"), ("Godavari Ghat Booth 2","ZC"),
    ("Central Command Post","ZD"), ("Nashik Road Chokepoint","ZD"),
    ("Panchavati Booth A","ZE"), ("Panchavati Booth B","ZE"),
    ("South Parking Booth","ZF"), ("Main Parking Entry","ZF"),
]
CHOKEPOINT_NAMES = [
    ("Ramkund Bridge","ZA"), ("Temple Road Narrows","ZB"), ("Ghat Steps East","ZC"),
    ("Market Lane Junction","ZD"), ("Panchavati Crossing","ZE"),
]
PARKING_NAMES = [
    ("P1 Trimbak Road","ZB"), ("P2 Nashik Highway","ZD"), ("P3 South Lot","ZF"),
]

BOOTHS = []
def write_chokepoints():
    path = os.path.join(OUT, "Chokepoints_Parking.csv")
    rows = []
    idx = 1
    for name, zone in BOOTH_NAMES:
        z = next(x for x in ZONES if x["zone_id"]==zone)
        bid = f"BOOTH_{idx:02d}"
        row = {"booth_id": bid, "name": name, "type": "booth",
               "lat": jitter(z["lat"]), "lng": jitter(z["lng"]),
               "zone": zone, "capacity": random.randint(500,2000), "is_active": True}
        rows.append(row); BOOTHS.append(row); idx+=1
    for name, zone in CHOKEPOINT_NAMES:
        z = next(x for x in ZONES if x["zone_id"]==zone)
        bid = f"CP_{idx:02d}"
        row = {"booth_id": bid, "name": name, "type": "chokepoint",
               "lat": jitter(z["lat"]), "lng": jitter(z["lng"]),
               "zone": zone, "capacity": random.randint(3000,10000), "is_active": True}
        rows.append(row); idx+=1
    for name, zone in PARKING_NAMES:
        z = next(x for x in ZONES if x["zone_id"]==zone)
        bid = f"PK_{idx:02d}"
        row = {"booth_id": bid, "name": name, "type": "parking",
               "lat": jitter(z["lat"]), "lng": jitter(z["lng"]),
               "zone": zone, "capacity": random.randint(2000,8000), "is_active": True}
        rows.append(row); idx+=1
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["booth_id","name","type","lat","lng","zone","capacity","is_active"])
        w.writeheader(); w.writerows(rows)
    print(f"  [OK] Chokepoints_Parking.csv — {len(rows)} entries ({len(BOOTHS)} booths)")

# ---------------------------------------------------------------------------
# 3. CCTV
# ---------------------------------------------------------------------------
def write_cctv():
    path = os.path.join(OUT, "CCTV_Locations.csv")
    rows = []
    for i in range(1, 41):
        zone = random.choice(ZONES)
        rows.append({
            "cctv_id": f"CCTV_{i:03d}",
            "location_name": f"Camera at {zone['zone_name']} Pt{i}",
            "lat": jitter(zone["lat"]),
            "lng": jitter(zone["lng"]),
            "zone": zone["zone_id"],
            "coverage_radius_m": random.choice([50,75,100,150]),
        })
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["cctv_id","location_name","lat","lng","zone","coverage_radius_m"])
        w.writeheader(); w.writerows(rows)
    print(f"  [OK] CCTV_Locations.csv — {len(rows)} cameras")

# ---------------------------------------------------------------------------
# 4. Police Stations
# ---------------------------------------------------------------------------
PS_NAMES = [
    ("Trimbak Police Post","ZB"), ("Ramkund Beat Post","ZA"),
    ("Nashik Central Station","ZD"), ("Panchavati Post","ZE"),
    ("South Sector Post","ZF"), ("Godavari Ghat Post","ZC"),
]
def write_police():
    path = os.path.join(OUT, "Police_Stations.csv")
    rows = []
    for i,(name,zone) in enumerate(PS_NAMES,1):
        z = next(x for x in ZONES if x["zone_id"]==zone)
        rows.append({
            "station_id": f"PS_{i:03d}",
            "name": name,
            "type": "station" if i==3 else "post",
            "lat": jitter(z["lat"]),
            "lng": jitter(z["lng"]),
            "zone": zone,
            "contact": f"+91 9{random.randint(100000000,999999999)}",
        })
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["station_id","name","type","lat","lng","zone","contact"])
        w.writeheader(); w.writerows(rows)
    print(f"  [OK] Police_Stations.csv — {len(rows)} stations")

# ---------------------------------------------------------------------------
# 5. Synthetic Missing Persons — 2500 rows, 8% ground-truth duplicate pairs
# ---------------------------------------------------------------------------
GENDERS  = ["male","female","unknown"]
AGE_BANDS= ["child_0_5","child_6_12","teen","adult","elderly"]
LANGS    = ["Hindi","Marathi","Gujarati","Bengali","Telugu","Tamil","Unknown"]
OPERATORS= [f"OP_{i:03d}" for i in range(1,21)]

CLOTHING_TOPS    = ["red shirt","blue kurta","green t-shirt","white saree","yellow dupatta",
                    "orange jacket","grey hoodie","black t-shirt","pink blouse","striped kurta"]
CLOTHING_BOTTOMS = ["jeans","dhoti","pyjama","lehenga","salwar","shorts","lunghi","trousers"]
MARKS            = ["mole on left cheek","wearing glasses","scar on chin","bindi on forehead",
                    "short hair","long hair","no distinguishing marks","birthmark on neck",
                    "limping slightly","wearing silver anklet"]
CARRYING         = ["orange bag","plastic bag","no bag","black backpack","jhola bag","umbrella",
                    "small steel vessel","flower garland"]

def make_description(gender, age_band):
    top     = random.choice(CLOTHING_TOPS)
    bottom  = random.choice(CLOTHING_BOTTOMS)
    mark    = random.choice(MARKS)
    carry   = random.choice(CARRYING)
    height  = random.choice(["short","medium height","tall"])
    build   = random.choice(["thin","average build","stout"])
    return f"{height} {build} person wearing {top} and {bottom}, {mark}, carrying {carry}"

def make_description_variant(original_desc):
    """Slightly paraphrase a description to simulate a parent's report after a booth found-report."""
    words = original_desc.split()
    # randomly drop 1-2 words, change one synonym
    synonyms = {
        "shirt": "top", "kurta": "shirt", "t-shirt": "shirt",
        "jeans": "pants", "trousers": "pants",
        "short": "small", "tall": "large",
        "thin": "slim", "stout": "heavy",
        "carrying": "holding", "wearing": "in",
    }
    out = []
    for w in words:
        w_lower = w.lower().rstrip(",.;")
        if w_lower in synonyms and random.random() < 0.4:
            out.append(synonyms[w_lower])
        elif random.random() < 0.05:   # drop word
            pass
        else:
            out.append(w)
    return " ".join(out)

def rand_dt():
    base = datetime(2027, 2, 10, 6, 0, 0)
    return base + timedelta(minutes=random.randint(0, 60*16))

def write_persons():
    TOTAL  = 2500
    N_DUPS = 200     # 8%  => 100 pairs
    path   = os.path.join(OUT, "Synthetic_Missing_Persons_2500.csv")

    fields = [
        "report_id","report_type","timestamp","reporting_center","operator_id",
        "name","gender","age_band","age_estimate","language",
        "physical_description","last_seen_location","last_seen_lat","last_seen_lng",
        "reporter_mobile","photo_url","status","duplicate_pair_id",
        "is_ground_truth_dup","matched_report_id","resolution_time_mins"
    ]

    rows = []

    # --- 100 ground-truth duplicate pairs (200 rows) ---
    for p in range(100):
        pair_id = f"PAIR_{p+1:03d}"
        booth_found  = random.choice(BOOTHS)
        booth_parent = random.choice([b for b in BOOTHS if b["booth_id"] != booth_found["booth_id"]])
        gender   = random.choice(["male","female"])
        age_band = random.choice(AGE_BANDS)
        age_est  = {"child_0_5":3,"child_6_12":9,"teen":15,"adult":35,"elderly":68}[age_band]
        lang     = random.choice(LANGS)
        desc_found = make_description(gender, age_band)
        desc_parent = make_description_variant(desc_found)
        dt_found   = rand_dt()
        dt_parent  = dt_found + timedelta(minutes=random.randint(5,30))
        rid_found  = f"RPT_{len(rows)+1:04d}"
        rid_parent = f"RPT_{len(rows)+2:04d}"

        rows.append({
            "report_id": rid_found,
            "report_type": "found_unaccompanied",
            "timestamp": dt_found.isoformat(),
            "reporting_center": booth_found["booth_id"],
            "operator_id": random.choice(OPERATORS),
            "name": "",
            "gender": gender, "age_band": age_band, "age_estimate": age_est, "language": lang,
            "physical_description": desc_found,
            "last_seen_location": booth_found["booth_id"],
            "last_seen_lat": booth_found["lat"], "last_seen_lng": booth_found["lng"],
            "reporter_mobile": "",
            "photo_url": f"photos/synth_{rid_found}.jpg",
            "status": "open",
            "duplicate_pair_id": pair_id, "is_ground_truth_dup": True,
            "matched_report_id": "", "resolution_time_mins": "",
        })
        rows.append({
            "report_id": rid_parent,
            "report_type": "missing",
            "timestamp": dt_parent.isoformat(),
            "reporting_center": booth_parent["booth_id"],
            "operator_id": random.choice(OPERATORS),
            "name": random.choice(["","Ramesh","Sunita","Priya","Arjun","Kavita","","Lakshmi",""]),
            "gender": gender, "age_band": age_band, "age_estimate": age_est, "language": lang,
            "physical_description": desc_parent,
            "last_seen_location": booth_found["booth_id"],
            "last_seen_lat": booth_found["lat"], "last_seen_lng": booth_found["lng"],
            "reporter_mobile": f"+91 9{random.randint(100000000,999999999)}",
            "photo_url": "",
            "status": "open",
            "duplicate_pair_id": pair_id, "is_ground_truth_dup": True,
            "matched_report_id": "", "resolution_time_mins": "",
        })

    # --- Remaining 2300 non-duplicate rows ---
    types = ["missing","found_unaccompanied"]
    while len(rows) < TOTAL:
        booth  = random.choice(BOOTHS)
        rtype  = random.choice(types)
        gender = random.choice(GENDERS)
        ab     = random.choice(AGE_BANDS)
        ae     = {"child_0_5":random.randint(1,5),"child_6_12":random.randint(6,12),
                  "teen":random.randint(13,19),"adult":random.randint(20,60),
                  "elderly":random.randint(61,90)}[ab]
        rid    = f"RPT_{len(rows)+1:04d}"
        rows.append({
            "report_id": rid,
            "report_type": rtype,
            "timestamp": rand_dt().isoformat(),
            "reporting_center": booth["booth_id"],
            "operator_id": random.choice(OPERATORS),
            "name": random.choice(["","","",
                "Ramesh","Sunita","Priya","Arjun","Kavita","Lakshmi","Vikram","Geeta"]),
            "gender": gender, "age_band": ab, "age_estimate": ae,
            "language": random.choice(LANGS),
            "physical_description": make_description(gender, ab),
            "last_seen_location": booth["booth_id"],
            "last_seen_lat": booth["lat"], "last_seen_lng": booth["lng"],
            "reporter_mobile": "" if rtype=="found_unaccompanied" else f"+91 9{random.randint(100000000,999999999)}",
            "photo_url": f"photos/synth_{rid}.jpg" if random.random()<0.6 else "",
            "status": "open",
            "duplicate_pair_id": "", "is_ground_truth_dup": False,
            "matched_report_id": "", "resolution_time_mins": "",
        })

    random.shuffle(rows)
    # Re-assign sequential IDs after shuffle
    for i, r in enumerate(rows):
        r["report_id"] = f"RPT_{i+1:04d}"

    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader(); w.writerows(rows)

    dup_count = sum(1 for r in rows if r["is_ground_truth_dup"])
    print(f"  [OK] Synthetic_Missing_Persons_2500.csv — {len(rows)} rows, "
          f"{dup_count} ground-truth dup rows ({100*dup_count/len(rows):.1f}%), "
          f"100 matched pairs")

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    print("Generating Kumbh Mela synthetic datasets...")
    write_zones()
    write_chokepoints()
    write_cctv()
    write_police()
    write_persons()
    print("Done. All CSVs written to:", OUT)
