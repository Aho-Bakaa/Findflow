"""KML parsing — extracts <Placemark> points into a DataFrame.

Note: handles the Python 3.13 ElementTree change where `if element:` evaluates
an element with no children as False (which silently dropped text fields).
"""
import xml.etree.ElementTree as ET
import pandas as pd

_NS = {"kml": "http://www.opengis.net/kml/2.2"}


def parse_points(path) -> pd.DataFrame:
    """Return a DataFrame[name, description, lat, lon] of all Point placemarks."""
    rows = []
    for pm in ET.parse(path).getroot().findall(".//kml:Placemark", _NS):
        name = pm.find("kml:name", _NS)
        desc = pm.find("kml:description", _NS)
        coords = pm.find(".//kml:Point/kml:coordinates", _NS)
        if coords is None or not coords.text:
            continue
        parts = coords.text.strip().split(",")
        if len(parts) < 2:
            continue
        try:
            lon, lat = float(parts[0]), float(parts[1])
        except ValueError:
            continue
        rows.append({
            "name": name.text.strip() if (name is not None and name.text) else "",
            "description": desc.text.strip() if (desc is not None and desc.text) else "",
            "lat": lat, "lon": lon,
        })
    return pd.DataFrame(rows)
