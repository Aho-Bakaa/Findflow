"""Is there learnable spatiotemporal signal in the case data, or is it uniform?"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import chisquare, chi2_contingency

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from findflow import config as C

df = pd.read_csv(C.CASES_CSV)
df["reported_at"] = pd.to_datetime(df["reported_at"])
df["hour"] = df["reported_at"].dt.hour


def cv(x):
    return np.std(x) / np.mean(x)


print("=" * 60)
print("UNIFORMITY TESTS  (p>0.05 => indistinguishable from random)")
print("=" * 60)
h = df.groupby("hour").size()
h = h[h.index.isin(range(5, 22))]
print(f"HOUR     CV={cv(h.values):.2f}  p={chisquare(h.values)[1]:.3f}")
loc = df["last_seen_location"].value_counts()
print(f"LOCATION CV={cv(loc.values):.2f}  p={chisquare(loc.values)[1]:.3f}")
day = df.groupby(df["reported_at"].dt.date).size()
print(f"DAY      CV={cv(day.values):.2f}  p={chisquare(day.values)[1]:.3f}")
age = df["age_band"].value_counts()
print(f"AGE      CV={cv(age.values):.2f}  (intentionally skewed -> elders)")

print("\nKIDS-vs-ELDERS cluster differently?")
sub = df[df["age_band"].isin(["0-12", "80+"])]
top = df["last_seen_location"].value_counts().head(12).index
ct = pd.crosstab(sub["last_seen_location"], sub["age_band"]).reindex(top).dropna()
print(f"  chi2 p={chi2_contingency(ct)[1]:.3f} "
      f"({'real difference' if chi2_contingency(ct)[1] < 0.05 else 'NO real difference — noise'})")
