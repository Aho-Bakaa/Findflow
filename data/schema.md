# Data Schemas — Found-First Missing Persons System
# Claude Impact Lab Mumbai | Team 60 | 27 June 2026

---

## 1. Chokepoints_Parking.csv
Booths, chokepoints, and parking areas around Nashik–Trimbakeshwar Ghats.
Used for: proximity sorting of Flow A alerts, hotspot overlay.

| Field          | Type    | Description                                  |
|----------------|---------|----------------------------------------------|
| booth_id       | string  | Unique identifier e.g. "BOOTH_01"            |
| name           | string  | Human-readable name ("Ramkund Ghat Booth 1") |
| type           | enum    | booth | chokepoint | parking | police_post        |
| lat            | float   | Latitude (WGS-84)                            |
| lng            | float   | Longitude (WGS-84)                           |
| zone           | string  | Zone name e.g. "Zone_A"                      |
| capacity       | int     | Approximate crowd capacity at this point      |
| is_active      | boolean | Whether booth is staffed today               |

---

## 2. Zone_Boundaries.csv
Zone adjacency map for proximity-based alert routing.

| Field          | Type    | Description                                  |
|----------------|---------|----------------------------------------------|
| zone_id        | string  | e.g. "Zone_A"                                |
| zone_name      | string  | e.g. "Ramkund Ghat Area"                    |
| adjacent_zones | string  | Pipe-separated list "Zone_B|Zone_C"          |
| lat_center     | float   | Zone centroid latitude                       |
| lng_center     | float   | Zone centroid longitude                      |

---

## 3. CCTV_Locations.csv
CCTV camera GPS coordinates only — no footage, no live feed.
Used for: hotspot overlay (stretch goal).

| Field          | Type    | Description                                  |
|----------------|---------|----------------------------------------------|
| cctv_id        | string  | e.g. "CCTV_001"                              |
| location_name  | string  | e.g. "Ramkund Gate North"                   |
| lat            | float   | Latitude                                     |
| lng            | float   | Longitude                                   |
| zone           | string  | Zone this camera covers                      |
| coverage_radius_m | int  | Estimated coverage radius in metres          |

---

## 4. Police_Stations.csv
Police posts and stations near the Kumbh perimeter.

| Field          | Type    | Description                                  |
|----------------|---------|----------------------------------------------|
| station_id     | string  | e.g. "PS_001"                                |
| name           | string  | e.g. "Trimbak Road Police Post"             |
| type           | enum    | post | station                                    |
| lat            | float   | Latitude                                     |
| lng            | float   | Longitude                                   |
| zone           | string  | Zone covered                                 |
| contact        | string  | Phone number (synthetic)                     |

---

## 5. Synthetic_Missing_Persons_2500.csv
Main dataset — 2500 records seeding the registry and matcher tests.
~1250 missing reports (Flow B) + ~1250 found reports (Flow A).
Exactly 8% (200 rows) are pre-flagged as ground-truth duplicate pairs.

| Field                | Type    | Description                                        |
|----------------------|---------|----------------------------------------------------|
| report_id            | string  | UUID e.g. "RPT_0001"                              |
| report_type          | enum    | missing \| found_unaccompanied                    |
| timestamp            | datetime| ISO-8601 e.g. "2027-02-10T08:34:00+05:30"        |
| reporting_center     | string  | booth_id of the booth filing this report           |
| operator_id          | string  | Operator who filed                                 |
| name                 | string  | Name (nullable — often blank for found reports)    |
| gender               | enum    | male \| female \| unknown                         |
| age_band             | enum    | child_0_5 \| child_6_12 \| teen \| adult \| elderly|
| age_estimate         | int     | Best guess age (nullable)                          |
| language             | string  | Primary language spoken e.g. "Hindi"              |
| physical_description | string  | Free-text: clothing, distinguishing features       |
| last_seen_location   | string  | booth_id or free-text location                     |
| last_seen_lat        | float   | Coordinates if known (nullable)                    |
| last_seen_lng        | float   | Coordinates if known (nullable)                    |
| reporter_mobile      | string  | Contact number (nullable)                          |
| photo_url            | string  | Path/URL to photo (nullable for demo)              |
| status               | enum    | open \| matched \| resolved                       |
| duplicate_pair_id    | string  | Links duplicate pairs for benchmark (nullable)     |
| is_ground_truth_dup  | boolean | True for the 8% benchmark rows                    |
| matched_report_id    | string  | Set when resolved (nullable)                       |
| resolution_time_mins | int     | Minutes to resolution (nullable, set on resolve)  |

---

## 6. reports (Server SQLite/JSON DB — Runtime Table)
Live shared database written by all booths. Superset of CSV schema.

| Field                | Type    | Description                                        |
|----------------------|---------|----------------------------------------------------|
| id                   | string  | UUID (auto-generated)                              |
| report_type          | enum    | missing \| found_unaccompanied                    |
| timestamp            | string  | ISO-8601                                           |
| reporting_center     | string  | booth_id                                           |
| operator_id          | string  |                                                    |
| name                 | string  | nullable                                           |
| gender               | enum    | male \| female \| unknown                         |
| age_band             | enum    | child_0_5 \| child_6_12 \| teen \| adult \| elderly|
| age_estimate         | int     | nullable                                           |
| language             | string  |                                                    |
| physical_description | string  |                                                    |
| last_seen_location   | string  |                                                    |
| last_seen_lat        | float   | nullable                                           |
| last_seen_lng        | float   | nullable                                           |
| reporter_mobile      | string  | nullable                                           |
| photo_data           | string  | base64 data URI (nullable)                         |
| status               | enum    | open \| matched \| resolved                       |
| matched_report_id    | string  | nullable                                           |
| synced               | boolean | False if created offline and not yet synced        |
| created_at           | string  | ISO-8601                                           |
| updated_at           | string  | ISO-8601                                           |
