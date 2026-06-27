import csv, collections

with open('Synthetic_Missing_Persons_2500.csv', encoding='utf-8') as f:
    rows = list(csv.DictReader(f))

pairs = collections.defaultdict(list)
for r in rows:
    if r['is_ground_truth_dup'] == 'True':
        pairs[r['duplicate_pair_id']].append(r)

pair_ids = list(pairs.keys())[:2]
for pid in pair_ids:
    print("=== " + pid + " ===")
    for r in pairs[pid]:
        print("  report_id=" + r["report_id"] + "  type=" + r["report_type"])
        print("  gender=" + r["gender"] + "  age_band=" + r["age_band"])
        print("  desc: " + r["physical_description"])
    print()
