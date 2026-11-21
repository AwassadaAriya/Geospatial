import hashlib
import sys
import time
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
import rasterio
import requests
from rasterstats import zonal_stats
from shapely.geometry import box, mapping

sys.path.insert(0, str(Path(__file__).resolve().parent))
from load_data import (RAW, PROC, EXP, CRS, SCENARIOS, DEM, to_crs, load_aoi, load_neighborhoods, 
                       load_floods, load_svi)

EXP.mkdir(parents=True, exist_ok=True)
REFRESH = False                 # set by --refresh: ignore cached downloads and fetch them again
NODATA = -9999.0
# impervious: NLCD at 30 m for the whole study area, one request so every year shares one grid
NLCD_YEARS = (2021, 2001)       # current, and the earliest NLCD year, for change over time
NLCD_TIF = {y: RAW / f"nlcd_impervious_{y}.tif" for y in NLCD_YEARS}
NOTEBOOK_IMPERVIOUS = PROC / "impervious_frac_26986.tif"     # East Boston only, from the notebook; kept for comparison
PAVED_MIN_SHARE = 0.5           # "public paved land": public or tax-exempt owner and at least this impervious share
PARCEL_SERVICE = "https://gis.boston.gov/arcgis/rest/services/Assessing/Property_Assessment_FY25/MapServer/0"
PARCEL_FIELDS = "GIS_ID,OWNER,LU,LU_DESC,TOTAL_VALUE,BLDG_VALUE,YR_BUILT"
AIRFIELD_MIN_AREA_M2 = 100_000
S = requests.Session()
S.headers.update({"User-Agent": "Mozilla/5.0 (Macintosh) geo-research"})

PUBLIC_KEYWORDS = [
    "CITY OF BOSTON", "BOSTON CITY OF", "COMMONWEALTH OF MASS", "COMMONWEALTH MASS",
    "MASSACHUSETTS PORT", "MASS PORT", "MASSPORT", "BOSTON HOUSING AUTH",
    "BOSTON REDEVELOPMENT", "BOSTON PLANNING", "MASS BAY TRANS", "MBTA",
    "UNITED STATES", "U S A", "MASS DEPT", "DEPT OF CONSERVATION", "MASSDOT",
    "MASS HIGHWAY", "CONSERVATION COMM", "BOSTON PUBLIC",
]

def cached(p):
    return p.exists() and not REFRESH


def stage_dem(tile_m=1500, res=1):
    if cached(DEM["west"]):
        print("dem west exists"); return
    import py3dep, rioxarray
    from rioxarray.merge import merge_arrays
    tiles_dir = RAW / "dem_tiles_1m_west"; tiles_dir.mkdir(parents=True, exist_ok=True)
    study = load_aoi("west").buffer(300).geometry.iloc[0]
    minx, miny, maxx, maxy = study.bounds
    tiles = [box(x, y, min(x + tile_m, maxx), min(y + tile_m, maxy))
             for x in np.arange(minx, maxx, tile_m) for y in np.arange(miny, maxy, tile_m)]
    tiles = [t for t in tiles if t.intersects(study)]
    print(f"{len(tiles)} tiles of up to {tile_m} m", flush=True)
    parts = []
    for n, t in enumerate(tiles):
        f = tiles_dir / f"tile_{n:03d}.tif"
        if not cached(f):
            t4326 = gpd.GeoSeries([t], crs=CRS).to_crs(4326).iloc[0]
            for k in range(5):
                try:
                    da = py3dep.get_dem(t4326, resolution=res, crs=4326)
                    da = da.rio.reproject(CRS, resolution=float(res))
                    da.astype("float32").rio.to_raster(f)
                    break
                except Exception as e:
                    print(f"  tile {n + 1}/{len(tiles)} attempt {k + 1} failed ({type(e).__name__}: {str(e)[:80]})", flush=True)
                    time.sleep(10 * (k + 1))
            else:
                raise RuntimeError(f"tile {n + 1} failed 5 times; rerun to resume")
        parts.append(rioxarray.open_rasterio(f, masked=True).squeeze())
        print(f"  tile {n + 1}/{len(tiles)} ok", flush=True)
    da = merge_arrays(parts, nodata=np.nan)
    da = da.rio.clip([mapping(study)], CRS, drop=True)
    da = da.astype("float32").fillna(NODATA).rio.write_nodata(NODATA, encoded=False)
    da.rio.to_raster(DEM["west"], compress="lzw")
    print("wrote", DEM["west"], flush=True)


def arcgis_query(layer_url, bounds_4326, out_fields, chunk=400):
    minx, miny, maxx, maxy = bounds_4326
    base = dict(geometry=f"{minx},{miny},{maxx},{maxy}", geometryType="esriGeometryEnvelope",
                inSR=4326, spatialRel="esriSpatialRelIntersects", where="1=1")
    ids = S.get(f"{layer_url}/query", params={**base, "returnIdsOnly": "true", "f": "json"}, timeout=180).json().get("objectIds") or []
    print(f"{len(ids)} features to fetch", flush=True)
    parts = []
    for i in range(0, len(ids), chunk):
        batch = ",".join(map(str, ids[i:i + chunk]))
        for k in range(4):
            try:
                r = S.post(f"{layer_url}/query", data={"objectIds": batch, "outFields": out_fields, "outSR": 4326,
                                                       "returnGeometry": "true", "f": "geojson"}, timeout=300)
                r.raise_for_status(); feats = r.json().get("features", []); break
            except Exception as e:
                print(f"  batch {i} attempt {k + 1} failed ({type(e).__name__})", flush=True); time.sleep(5 * (k + 1))
        else:
            raise RuntimeError(f"batch {i} failed")
        if feats:
            parts.append(gpd.GeoDataFrame.from_features(feats, crs=4326))
        if (i // chunk) % 20 == 0:
            print(f"  {min(i + chunk, len(ids))}/{len(ids)}", flush=True)
    return pd.concat(parts, ignore_index=True)


def stage_parcels():
    p = RAW / "parcels_raw_west.parquet"
    if cached(p):
        print("parcels west exists"); return
    b = tuple(load_aoi("west").to_crs(4326).total_bounds)
    raw = arcgis_query(PARCEL_SERVICE, b, PARCEL_FIELDS)
    raw.to_parquet(p); print("wrote", p, len(raw), "rows", flush=True)


def classify_owner(owner, lu):
    o = str(owner).upper()
    if any(k in o for k in PUBLIC_KEYWORDS):
        return "public"
    if str(lu).upper().strip() == "E":
        return "exempt"
    return "private"


def clean_parcels(raw):
    df = to_crs(raw).copy()
    cid = "GIS_ID"
    df = df[df.geometry.notna() & ~df.geometry.is_empty]
    df[cid] = df[cid].where(df[cid].notna(), df.geometry.to_wkb().map(lambda b: hashlib.md5(b).hexdigest()))
    for c in ("TOTAL_VALUE", "BLDG_VALUE"):
        df[c] = pd.to_numeric(df[c].astype(str).str.replace(r"[$,]", "", regex=True), errors="coerce")
    df["YR_BUILT"] = pd.to_numeric(df["YR_BUILT"], errors="coerce")
    g = df.groupby(cid).agg({"geometry": "first", "OWNER": "first", "LU": "first", "LU_DESC": "first",
                             "TOTAL_VALUE": "sum", "BLDG_VALUE": "sum", "YR_BUILT": "min"})
    g["n_units"] = df.groupby(cid).size()                      # condo join repeats the polygon once per unit
    g = gpd.GeoDataFrame(g.reset_index(), geometry="geometry", crs=CRS)
    g = g.rename(columns={cid: "parcel_id", "OWNER": "owner", "LU": "lu", "LU_DESC": "lu_desc",
                          "TOTAL_VALUE": "total_value", "BLDG_VALUE": "bldg_value", "YR_BUILT": "yr_built"})
    g["parcel_id"] = g["parcel_id"].astype(str)
    g["owner_type"] = [classify_owner(o, l) for o, l in zip(g["owner"], g["lu"])]
    g["geometry"] = g.geometry.make_valid()
    g["area_m2"] = g.area
    return g


def load_parcels():
    raw = pd.concat([gpd.read_parquet(RAW / "parcels_raw.parquet").to_crs(4326),
                     gpd.read_parquet(RAW / "parcels_raw_west.parquet").to_crs(4326)], ignore_index=True)
    g = clean_parcels(raw).drop_duplicates("parcel_id")
    hoods = load_neighborhoods()
    pts = gpd.GeoDataFrame(g[["parcel_id"]], geometry=g.representative_point(), crs=CRS)
    j = gpd.sjoin(pts, hoods, how="inner", predicate="within").drop_duplicates("parcel_id")
    g = g.merge(j[["parcel_id", "name", "zone"]].rename(columns={"name": "neighborhood"}), on="parcel_id")
    airfield = ((g["neighborhood"] == "East Boston") & (g["area_m2"] > AIRFIELD_MIN_AREA_M2)
                & g["owner"].astype(str).str.upper().str.contains("MASSACHUSETTS PORT|MASSPORT|MASS PORT"))
    print(f"excluding {airfield.sum()} large Massport parcel(s) in East Boston (airfield)")
    return g[~airfield].reset_index(drop=True)


CKAN = "https://data.boston.gov/api/3/action"
ASSET_DATASETS = {
    "school": ["public-schools", "non-public-schools"],
    "fire_station": ["fire-departments"],
    "police": ["boston-police-stations-bpd-only"],
    "hospital": ["hospitals"],
    "community_centre": ["community-centers"],
}


def ckan_geojson(slug):
    pkg = S.get(f"{CKAN}/package_show", params={"id": slug}, timeout=60).json()["result"]
    res = sorted(pkg["resources"], key=lambda r: ("geojson" not in (r.get("format") or "").lower() and "geojson" not in (r.get("url") or "").lower()))
    url = res[0]["url"]
    r = S.get(url, timeout=180, allow_redirects=True); r.raise_for_status()
    import io
    g = gpd.read_file(io.BytesIO(r.content))
    return pkg["title"], url, g


def stage_assets():
    p = RAW / "assets_study.parquet"
    if cached(p):
        print("assets exist"); return
    study = load_aoi().buffer(200).geometry.iloc[0]
    parts = []
    for kind, slugs in ASSET_DATASETS.items():
        for slug in slugs:
            title, url, g = ckan_geojson(slug)
            g = to_crs(g)
            g["geometry"] = g.representative_point()
            namecol = next((c for c in g.columns if c.upper() in ("NAME", "SCH_NAME", "FACILITY", "BLDG_NAME", "STATION", "LOCATION", "SITE")), None)
            g = gpd.GeoDataFrame({"name": g[namecol].values if namecol else [None] * len(g), "asset_type": [kind] * len(g),
                                  "source": [title] * len(g)}, geometry=g.geometry.values, crs=CRS)
            g = g[g.within(study)]
            print(f"  {title}: {len(g)} in study area  ({url[:80]})", flush=True)
            parts.append(g)
    st = gpd.read_parquet(RAW / "mbta_stops.parquet").to_crs(CRS)
    st = st[st.within(study)]
    parts.append(gpd.GeoDataFrame({"name": st["STATION"], "asset_type": "station", "source": "MBTA Rapid Transit Stops (MassGIS)"}, geometry=st.geometry, crs=CRS))
    out = pd.concat(parts, ignore_index=True)
    out.to_parquet(p)
    print("wrote", p, len(out), out["asset_type"].value_counts().to_dict(), flush=True)


def flood_fraction(parcels, flood_geom, cell=300):
    """Share of each parcel inside the flood extent. The extent is one huge polygon, so cut it into grid cells first."""
    minx, miny, maxx, maxy = parcels.total_bounds
    grid = gpd.GeoDataFrame(geometry=[box(x, y, x + cell, y + cell) for x in np.arange(minx, maxx, cell)
                                      for y in np.arange(miny, maxy, cell)], crs=CRS)
    pieces = gpd.clip(grid, flood_geom)
    pieces = pieces[~pieces.geometry.is_empty]
    ov = gpd.overlay(parcels[["parcel_id", "geometry"]], pieces[["geometry"]], how="intersection", keep_geom_type=True)
    wet = ov.assign(a=ov.area).groupby("parcel_id")["a"].sum()
    return (parcels["parcel_id"].map(wet).fillna(0) / parcels.area).clip(0, 1).values


def zstats(parcels, raster, stats, all_touched=False):
    zs = zonal_stats(parcels.geometry, str(raster), stats=stats, all_touched=all_touched, nodata=NODATA)
    return pd.DataFrame(zs, index=parcels.index)


def stage_nlcd():
    """NLCD impervious percent at 30 m for the whole study area, all years in one request (same grid)."""
    if all(cached(p) for p in NLCD_TIF.values()):
        print("nlcd exists"); return
    import pygeohydro as gh
    # buffered: NLCD comes back masked to the shape, and parcels on the edge need the cells just outside it
    area = load_aoi().buffer(200).to_crs(4326)
    ds = gh.nlcd_bygeom(area, resolution=30, years={"impervious": list(NLCD_YEARS)})
    d = list(ds.values())[0]
    for y, p in NLCD_TIF.items():
        d[f"impervious_{y}"].rio.to_raster(p, compress="lzw")
        print("wrote", p, flush=True)


def nlcd_share(feat, year):
    """Share of each parcel that is impervious (0-1): mean NLCD percent over every 30 m cell the parcel touches."""
    tif = NLCD_TIF[year]
    with rasterio.open(tif) as src:
        w = feat.to_crs(src.crs)
        zs = zonal_stats(w.geometry, str(tif), stats=["mean"], all_touched=True, nodata=src.nodata)
    v = pd.Series([z["mean"] for z in zs], index=feat.index, dtype="float64")
    return v.where((v >= 0) & (v <= 100)) / 100.0


def notebook_share(feat):
    """The old East Boston method (notebook raster on the 1 m DEM grid), for comparison only. NaN outside East Boston."""
    out = pd.Series(np.nan, index=feat.index)
    if not NOTEBOOK_IMPERVIOUS.exists():
        print("notebook impervious raster not found; impervious_share_notebook left empty"); return out
    east = feat["zone"] == "east"
    out[east] = zstats(feat[east], NOTEBOOK_IMPERVIOUS, ["mean"])["mean"]
    small = east & out.isna()
    if small.any():
        out[small] = zstats(feat[small], NOTEBOOK_IMPERVIOUS, ["mean"], all_touched=True)["mean"]
    return out


def stage_features():
    """Everything per parcel except critical assets (slow: zonal statistics on 1 m rasters)."""
    feat = load_parcels()
    print(len(feat), "parcels |", feat["neighborhood"].value_counts().to_dict(), flush=True)
    floods = load_floods(load_aoi())
    for s in SCENARIOS:
        f = floods[s].geometry.iloc[0]
        feat[f"flood_frac_{s}"] = flood_fraction(feat, f)          # share of the parcel inside the city's flood extent
    for zone, path in DEM.items():
        m = feat["zone"] == zone
        z = zstats(feat[m], path, ["mean", "min"])
        feat.loc[m, "ground_mean_m"] = z["mean"].values; feat.loc[m, "ground_min_m"] = z["min"].values
    print("elevation done", flush=True)
    stage_nlcd()
    feat["impervious_frac"] = nlcd_share(feat, 2021)             # same method in all ten neighbourhoods
    feat["impervious_share_2001"] = nlcd_share(feat, 2001)
    feat["impervious_share_notebook"] = notebook_share(feat)

    pts = gpd.GeoDataFrame(feat[["parcel_id"]], geometry=feat.representative_point(), crs=CRS)
    j = gpd.sjoin_nearest(pts, load_svi(), how="left", max_distance=300)
    feat["vuln_pct"] = j.groupby(level=0)["vuln_pct"].first()
    feat.to_parquet(EXP / "parcel_features.parquet")
    print("wrote parcel_features:", len(feat), "| flooded at 36in:", int((feat.flood_frac_36 > 0).sum()), flush=True)


def stage_score():
    """Add critical assets and the public-paved-land flag. No risk score: the map shows the data only."""
    feat = gpd.read_parquet(EXP / "parcel_features.parquet")
    a = to_crs(gpd.read_parquet(RAW / "assets_study.parquet"))
    hit = gpd.sjoin(a, feat[["geometry"]], how="inner", predicate="within")
    types = hit.groupby("index_right")["asset_type"].agg(lambda x: ", ".join(sorted(set(map(str, x)))))
    feat["asset_types"] = types.reindex(feat.index).fillna("")
    feat["critical_asset"] = feat["asset_types"] != ""
    public = feat["owner_type"].isin(["public", "exempt"])
    feat["unpave_candidate"] = public & (feat["impervious_frac"] >= PAVED_MIN_SHARE)
    compare_methods(feat, public)
    feat = feat.drop(columns=[c for c in feat.columns if c.startswith(("depth_", "wse_"))])
    feat.to_parquet(EXP / "parcels.parquet")
    feat.drop(columns="geometry").to_csv(EXP / "parcels.csv", index=False)
    print(f"wrote parcels: {len(feat)} | flooded at 36in: {int((feat.flood_frac_36 > 0).sum())}", flush=True)


def compare_methods(feat, public):
    """East Boston: how the public-paved flag changes between the notebook raster and NLCD 2021."""
    e = feat[(feat["zone"] == "east") & feat["impervious_share_notebook"].notna()]
    if e.empty:
        print("no notebook values to compare"); return
    new = e["unpave_candidate"]
    old = public[e.index] & (e["impervious_share_notebook"] >= PAVED_MIN_SHARE)
    d = e["impervious_frac"] - e["impervious_share_notebook"]
    print(f"East Boston, {len(e)} parcels: impervious share NLCD 2021 minus notebook: "
          f"mean {d.mean():+.3f}, median abs {d.abs().median():.3f}, |diff| > 0.1 for {int((d.abs() > 0.1).sum())}")
    print(f"  public paved: notebook {int(old.sum())} -> NLCD 2021 {int(new.sum())} | "
          f"changed status {int((old != new).sum())} (gained {int((new & ~old).sum())}, lost {int((old & ~new).sum())})")


if __name__ == "__main__":
    args = sys.argv[1:]
    REFRESH = "--refresh" in args
    stages = {"dem": stage_dem, "parcels": stage_parcels, "assets": stage_assets, "nlcd": stage_nlcd,
              "features": stage_features, "score": stage_score}
    for stage in [a for a in args if a != "--refresh"]:
        stages[stage]()
