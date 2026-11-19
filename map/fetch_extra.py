import sys
from pathlib import Path

import geopandas as gpd
import pandas as pd
import requests

sys.path.insert(0, str(Path(__file__).resolve().parent))
from load_data import RAW, CRS  # noqa: E402

S = requests.Session()
S.headers.update({"User-Agent": "Mozilla/5.0 (Macintosh) geo-research"})

BBOX = (-71.110, 42.300, -70.970, 42.412)

SNAP_URL = "https://services1.arcgis.com/RLQu0rK7h4kbsBq5/arcgis/rest/services/snap_retailer_location_data/FeatureServer/0"
LIVING_ATLAS = "https://services.arcgis.com/P3ePLMYs2RVChkJx/arcgis/rest/services"
COMMUTE_URL = f"{LIVING_ATLAS}/ACS_Means_of_Transportation_to_Work_Boundaries/FeatureServer/2"
VEHICLES_URL = f"{LIVING_ATLAS}/ACS_Vehicle_Availability_Boundaries/FeatureServer/2"


def arcgis_all(layer_url, where="1=1", bbox=None, out_fields="*", geometry=True, page=50):
    """Page through an ArcGIS feature layer with resultOffset; return a GeoDataFrame in EPSG:4326."""
    parts, offset = [], 0
    while True:
        params = dict(where=where, outFields=out_fields, returnGeometry=str(geometry).lower(),
                      outSR=4326, resultOffset=offset, resultRecordCount=page, f="geojson")
        if bbox:
            params.update(geometry=",".join(map(str, bbox)), geometryType="esriGeometryEnvelope",
                          inSR=4326, spatialRel="esriSpatialRelIntersects")
        r = S.get(f"{layer_url}/query", params=params, timeout=120)
        r.raise_for_status()
        js = r.json()
        if "error" in js:
            raise RuntimeError(js["error"])
        feats = js.get("features", [])
        if feats:
            parts.append(gpd.GeoDataFrame.from_features(feats, crs=4326))
        if len(feats) < page:
            break
        offset += page
    if not parts:
        raise RuntimeError(f"no features from {layer_url}")
    return pd.concat(parts, ignore_index=True)


def fetch_snap():
    p = RAW / "snap_stores.parquet"
    if p.exists():
        return p
    g = arcgis_all(SNAP_URL, bbox=BBOX,
                   out_fields="Record_ID,Store_Name,Store_Street_Address,City,State,Zip_Code,Store_Type,Latitude,Longitude,Incentive_Program")
    g.to_crs(CRS).to_parquet(p)
    print(f"snap_stores: {len(g)} stores | {g['Store_Type'].value_counts().to_dict()}")
    return p



def fetch_tracts(url, name, keep_prefix):
    p = RAW / f"{name}.parquet"
    if p.exists():
        return p
    g = arcgis_all(url, where="State='Massachusetts' AND County='Suffolk County'")
    cols = ["GEOID", "NAME", "geometry"] + [c for c in g.columns if c.startswith(keep_prefix)]
    g = g[cols]
    g.to_crs(CRS).to_parquet(p)
    print(f"{name}: {len(g)} Suffolk County tracts, {len(cols) - 3} ACS columns")
    return p



VIEW_BBOX = (-71.250, 42.220, -70.800, 42.500)
LAND_URL = f"{LIVING_ATLAS}/ACS_Vehicle_Availability_Boundaries/FeatureServer/2"


def fetch_land():
    p = RAW / "land_tracts.parquet"
    if p.exists():
        return p
    # this service rejects envelope queries, so pull two counties and clip locally
    from shapely.geometry import box
    g = arcgis_all(LAND_URL, where="State='Massachusetts' AND County IN ('Suffolk County','Middlesex County','Norfolk County','Essex County','Plymouth County')",
                   out_fields="GEOID,ALAND,AWATER")
    g = g[g.intersects(box(*VIEW_BBOX))]
    g.to_crs(CRS).to_parquet(p)
    print(f"land_tracts: {len(g)} tracts")
    return p


MBTA_URL = "https://arcgisserver.digital.mass.gov/arcgisserver/rest/services/AGOL/MBTA_Rapid_Transit/FeatureServer"


def fetch_mbta():
    """Official MBTA rapid transit lines and stops (MassGIS), clipped to the map view."""
    from shapely.geometry import box
    out = {}
    for name, layers in (("mbta_lines", (4, 5, 6)), ("mbta_stops", (0, 1, 2, 3))):
        p = RAW / f"{name}.parquet"
        if not p.exists():
            best = None
            for lyr in layers:                       # the service repeats each dataset at several scales; keep the fullest
                try:
                    g = arcgis_all(f"{MBTA_URL}/{lyr}", page=200)
                except Exception:
                    continue
                if best is None or len(g) > len(best):
                    best = g
            best = best[best.intersects(box(*VIEW_BBOX))]
            best.to_crs(CRS).to_parquet(p)
            print(f"{name}: {len(best)} features | cols {[c for c in best.columns if c != 'geometry'][:8]}")
        out[name] = p
    return out


STREETS_SLUG = "boston-street-segments-sam-system"


def fetch_streets():
    """City of Boston street centrelines (Analyze Boston), drawn as faint lines in the Etching and Overprint views."""
    import io
    p = RAW / "boston_street_segments.parquet"
    if p.exists():
        return p
    pkg = S.get("https://data.boston.gov/api/3/action/package_show", params={"id": STREETS_SLUG}, timeout=60).json()["result"]
    url = [r["url"] for r in pkg["resources"] if (r.get("format") or "").lower() == "geojson"][0]
    r = S.get(url, timeout=300); r.raise_for_status()
    gpd.read_file(io.BytesIO(r.content)).to_parquet(p)
    return p


if __name__ == "__main__":
    RAW.mkdir(parents=True, exist_ok=True)
    fetch_snap()
    fetch_tracts(COMMUTE_URL, "commute_tracts", "B08301")
    fetch_tracts(VEHICLES_URL, "vehicles_tracts", "B08201")
    fetch_land()
    fetch_mbta()
    fetch_streets()
    print("done ->", RAW)
