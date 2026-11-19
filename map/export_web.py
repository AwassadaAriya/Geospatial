import json
import sys
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
from shapely.geometry import box
from shapely.ops import linemerge, unary_union

sys.path.insert(0, str(Path(__file__).resolve().parent))
from load_data import ROOT, RAW, CRS, SCENARIOS, load_all, load_neighborhoods  # noqa: E402

OUT = ROOT / "docs" / "data"
OUT.mkdir(parents=True, exist_ok=True)
VIEW_BBOX = (-71.250, 42.220, -70.800, 42.500)
STATION_RADIUS_M = 40 
STATION_MIN_SHARE = 0.25
GROCER_TYPES = {"Supermarket", "Super Store", "Grocery Store", "Specialty Store"}


def _round(o, nd=6):
    if isinstance(o, float):
        return round(o, nd)
    if isinstance(o, list):
        return [_round(x, nd) for x in o]
    return o


def to_geojson(gdf, cols=(), tol=None):
    g = gdf[[c for c in cols if c in gdf.columns] + ["geometry"]].copy()
    if tol:
        g["geometry"] = g.geometry.simplify(tol, preserve_topology=True)
    g = g[~g.geometry.is_empty & g.geometry.notna()].to_crs(4326)
    for c in g.select_dtypes(include="float").columns:
        g[c] = g[c].round(3)
    for c in g.select_dtypes(include="bool").columns:
        g[c] = g[c].astype(int)
    fc = json.loads(g.to_json(drop_id=True))
    for f in fc["features"]:
        f["geometry"]["coordinates"] = _round(f["geometry"]["coordinates"])
    return fc


def write(name, obj):
    p = OUT / f"{name}.js"
    p.write_text(f"window.EB=window.EB||{{}};window.EB.{name}=" + json.dumps(obj, separators=(",", ":")) + ";")
    print(f"  {name:10s} {p.stat().st_size / 1e6:5.2f} MB")


LINE_COLOURS = {"red": "Red Line", "orange": "Orange Line", "blue": "Blue Line", "green": "Green Line", "silver": "Silver Line"}


def flood_share(geoms, floods):
    """Per tide: share of the area within STATION_RADIUS_M of each site that lies inside the flood extent."""
    around = geoms.buffer(STATION_RADIUS_M)
    return {sc: (around.intersection(floods[sc].geometry.iloc[0]).area / around.area).round(3).values for sc in SCENARIOS}


def main():
    d = load_all()
    aoi, parcels, floods, svi, assets = d["aoi"], d["scored"], d["floods"], d["svi"], d["assets"]
    aoi_geom = aoi.geometry.iloc[0]
    view = gpd.GeoSeries([box(*VIEW_BBOX)], crs=4326).to_crs(CRS).iloc[0]
    print("writing", OUT)

    # ---------------- parcels: owner type (assessing), impervious share (NLCD), share inside the flood extent
    p = parcels.copy()
    p["unpave_candidate"] = p["unpave_candidate"].astype(int)
    for sc in SCENARIOS:
        p[f"ff{sc}"] = p[f"flood_frac_{sc}"].round(2)
    write("parcels", to_geojson(p, ["owner_type", "impervious_frac", "unpave_candidate", "ff21", "ff36"], tol=0.7))
    write("aoi", to_geojson(load_neighborhoods(), ["name"], tol=1.5))

    # ---------------- food stores (USDA SNAP); under water = the store point is inside the flood extent
    stores = gpd.read_parquet(RAW / "snap_stores.parquet").to_crs(CRS)
    stores = stores[stores.within(aoi_geom.buffer(1400))].rename(columns={"Store_Name": "name", "Store_Type": "type"}).copy()
    stores["grocer"] = stores["type"].isin(GROCER_TYPES)
    for sc in SCENARIOS:
        stores[f"c{sc}"] = stores.within(floods[sc].geometry.iloc[0])
    stores["size"] = stores["type"].map({"Supermarket": 3, "Super Store": 3}).fillna(stores["grocer"].map({True: 2, False: 1})).astype(int)
    write("stores", to_geojson(stores, ["name", "type", "grocer", "size", "c21", "c36"]))

    # ---------------- streets (city centrelines), faint lines for the Etching and Overprint views
    seg = gpd.read_parquet(RAW / "boston_street_segments.parquet").to_crs(CRS)
    seg = seg[seg.intersects(aoi_geom.buffer(1500))].copy()
    seg["eb"] = seg.intersects(aoi_geom.buffer(60)).astype(int)
    write("streets", to_geojson(seg, ["eb"], tol=2.0))

    # ---------------- census tracts (ACS percentages) and social vulnerability (Climate Ready Boston)
    ct = gpd.read_parquet(RAW / "commute_tracts.parquet")
    vt = gpd.read_parquet(RAW / "vehicles_tracts.parquet")[["GEOID", "B08201_001E", "B08201_002E"]]
    t = ct.merge(vt, on="GEOID")
    t = t[t.representative_point().within(aoi_geom)].copy()
    t["transit_pct"] = t["B08301_010E"] / t["B08301_001E"] * 100
    t["noveh_pct"] = t["B08201_002E"] / t["B08201_001E"] * 100
    write("tracts", to_geojson(t, ["transit_pct", "noveh_pct"], tol=2.0))
    write("svi", to_geojson(svi.clip(aoi), ["vuln_pct"], tol=2.0))

    # ---------------- MBTA rapid transit lines and stops (MassGIS)
    sub = gpd.read_parquet(RAW / "mbta_lines.parquet")
    sub["line"] = sub["LINE"].str.lower().where(sub["LINE"].str.lower().isin(LINE_COLOURS), "other")
    lines = sub.dissolve("line").reset_index()[["line", "geometry"]]
    lines["geometry"] = lines.geometry.map(lambda g: linemerge(g) if g.geom_type == "MultiLineString" else g)
    write("blueline", to_geojson(lines, ["line"], tol=2.0))
    st = gpd.read_parquet(RAW / "mbta_stops.parquet").rename(columns={"STATION": "name", "LINE": "lines"})
    st = st[st.within(aoi_geom.buffer(150))].drop_duplicates("name").copy()
    st["lines"] = st["lines"].str.title()
    for sc, v in flood_share(st.geometry, floods).items():
        st[f"share_{sc}"] = v
        st[f"s{sc}"] = v >= STATION_MIN_SHARE
    write("stations", to_geojson(st, ["name", "lines", "s21", "s36", "share_21", "share_36"]))
    print(f"  stations: {len(st)} | under water at 36in: {sorted(st.loc[st.s36, 'name'])}")

    # ---------------- electrical substations (team file: only the named rows are substations)
    subs = gpd.read_file(ROOT / "data" / "electrical-infrastructure" / "ElecSubstations.geojson").to_crs(CRS)
    subs = subs[subs["NAME"].notna()].drop_duplicates("NAME")
    subs = subs[subs.within(view)].rename(columns={"NAME": "name", "ADDRESS": "addr", "SITE_TYPE": "site", "VOLTAGE_CONTEXT": "kv"}).copy()
    for sc, v in flood_share(subs.geometry, floods).items():
        subs[f"share_{sc}"] = v
    write("power_subs", to_geojson(subs, ["name", "addr", "site", "kv", "share_21", "share_36"]))
    print("  substations under water at 36in:", sorted(subs.loc[subs.share_36 >= STATION_MIN_SHARE, "name"]))

    # ---------------- critical assets (city facility layers)
    a = assets[assets["asset_type"] != "station"].copy()      # stations are drawn by the transit layer
    a["geometry"] = a.representative_point()
    a = a[a.within(aoi_geom)]
    write("assets", to_geojson(a, ["name", "asset_type"]))

    # ---------------- ground: land outline, open water, flood extents trimmed to land, engraved shore lines
    land = gpd.read_parquet(RAW / "land_tracts.parquet")
    land_u = unary_union(land.geometry.values).intersection(view).simplify(5)
    write("land", to_geojson(gpd.GeoDataFrame(geometry=[land_u], crs=CRS)))
    write("water", to_geojson(gpd.GeoDataFrame(geometry=[view.difference(land_u)], crs=CRS), tol=3.0))
    for sc in SCENARIOS:
        wet = floods[sc].geometry.iloc[0].intersection(land_u.buffer(3))
        write(f"flood{sc}", to_geojson(gpd.GeoDataFrame(geometry=[wet], crs=CRS), [], tol=1.0))
    rings = [{"i": i, "geometry": land_u.buffer(dist).boundary.intersection(view).simplify(5)}
             for i, dist in enumerate([30, 75, 135, 215, 320])]
    write("shore", to_geojson(gpd.GeoDataFrame(rings, crs=CRS), ["i"]))

    write("stats", {"meta": {"parcels": int(len(p)), "bounds": [round(v, 4) for v in aoi.to_crs(4326).total_bounds]}})


if __name__ == "__main__":
    main()
