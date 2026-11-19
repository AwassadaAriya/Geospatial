from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
RAW, PROC = DATA / "raw", DATA / "processed"
EXP = PROC / "expanded"

CRS = "EPSG:26986"
SCENARIOS = ["21", "36"]
EAST = ["East Boston"]
WEST = ["Charlestown", "North End", "West End", "Downtown", "Chinatown", "Leather District", "South End",
        "South Boston", "South Boston Waterfront"]
STUDY = EAST + WEST
VULN_COUNT_COLS = ["OlderAdult", "TotChild", "Low_to_No", "LEP", "POC2", "TotDis", "MedIllnes"]

# elevation is kept as two 1 m rasters: the notebook's East Boston grid and a second one for the added area
DEM = {"east": PROC / "dem_1m_26986.tif", "west": EXP / "dem_1m_west.tif"}


def to_crs(gdf):
    if gdf.crs is None:
        gdf = gdf.set_crs(4326)
    return gdf.to_crs(CRS)


def load_neighborhoods():
    g = to_crs(gpd.read_parquet(RAW / "neighborhoods.parquet"))[["name", "geometry"]]
    g = g[g["name"].isin(STUDY)].reset_index(drop=True)
    missing = set(STUDY) - set(g["name"])
    if missing:
        raise LookupError(f"not in neighborhoods.parquet: {missing}")
    g["zone"] = np.where(g["name"].isin(EAST), "east", "west")
    return g


def load_aoi(zone=None):
    """Study area as a one-row GeoDataFrame. zone='east' or 'west' gives just that part."""
    n = load_neighborhoods()
    if zone:
        n = n[n["zone"] == zone]
    return gpd.GeoDataFrame({"name": [zone or "study area"]}, geometry=[n.union_all()], crs=CRS)


def load_scored():
    """Parcels for the whole study area (built by map/pipeline.py)."""
    return gpd.read_parquet(EXP / "parcels.parquet").to_crs(CRS)


def load_floods(aoi):
    out = {}
    for s in SCENARIOS:
        g = to_crs(gpd.read_parquet(RAW / f"flood_{s}.parquet"))
        g["geometry"] = g.geometry.make_valid()
        clipped = g.clip(aoi.buffer(200))
        out[s] = gpd.GeoDataFrame({"scenario": [s]}, geometry=[clipped.union_all()], crs=CRS)
    return out


def load_svi():
    g = to_crs(gpd.read_parquet(RAW / "social_vuln.parquet"))
    pop = pd.to_numeric(g["POP100_RE"], errors="coerce").replace(0, np.nan)
    cols = [c for c in VULN_COUNT_COLS if c in g.columns]
    ranks = pd.DataFrame({c: (pd.to_numeric(g[c], errors="coerce") / pop).rank(pct=True) for c in cols})
    g["vuln_pct"] = ranks.mean(axis=1)
    g["vuln_n_indicators"] = len(cols)
    return g[["vuln_pct", "vuln_n_indicators", "geometry"]]


def load_assets():
    return to_crs(gpd.read_parquet(RAW / "assets_study.parquet"))


def load_all():
    aoi = load_aoi()
    return dict(aoi=aoi, scored=load_scored(), floods=load_floods(aoi), svi=load_svi(), assets=load_assets())
