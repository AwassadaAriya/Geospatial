import json
import sys
from pathlib import Path

import geopandas as gpd
import numpy as np
import shapely
from pyproj import Transformer
from scipy.spatial import cKDTree
from shapely.ops import unary_union

sys.path.insert(0, str(Path(__file__).resolve().parent))
from load_data import ROOT, RAW, CRS, SCENARIOS, load_all 

GROCER_TYPES = {"Supermarket", "Super Store", "Grocery Store", "Specialty Store"}     
OUT = ROOT / "docs" / "data" / "ink.js"
SPACINGS = [200, 100, 50]  
TO_LL = Transformer.from_crs(CRS, 4326, always_xy=True)


def hex_centres(bounds, s):
    minx, miny, maxx, maxy = bounds
    dy = s * np.sqrt(3) / 2
    ys = np.arange(miny, maxy + dy, dy)
    pts = [(x, y) for j, y in enumerate(ys) for x in np.arange(minx + (s / 2 if j % 2 else 0), maxx + s, s)]
    return np.array(pts)


def q(v):
    """0..1 -> one digit 0..9."""
    return "".join(map(str, np.clip(np.rint(np.nan_to_num(v) * 9), 0, 9).astype(int)))


def in_cell(centres, xy, spacing, strength=None):
    """Snap points to their nearest cell; each cell keeps the strongest point in it (default 1)."""
    out = np.zeros(len(centres))
    if len(xy) == 0:
        return out
    d, idx = cKDTree(centres).query(xy)
    w = np.ones(len(xy)) if strength is None else np.asarray(strength, float)
    ok = d <= spacing
    np.maximum.at(out, idx[ok], w[ok])
    return out


RESIDENTIAL_LU = {"R1", "R2", "R3", "R4", "A", "RC", "CM"}


def main():
    d = load_all()
    aoi, scored, floods, assets = d["aoi"], d["scored"], d["floods"], d["assets"]
    aoi_geom = aoi.geometry.iloc[0]
    land = unary_union(gpd.read_parquet(RAW / "land_tracts.parquet").geometry.values)
    area = aoi_geom.intersection(land)
    shapely.prepare(area)
    fgeom = {s: floods[s].geometry.iloc[0] for s in SCENARIOS}
    for g in fgeom.values():
        shapely.prepare(g)


    p = scored.copy()
    rp = p.representative_point()
    pxy = np.column_stack([rp.x, rp.y])
    p["res"] = p["lu"].isin(RESIDENTIAL_LU)
    ct = gpd.read_parquet(RAW / "commute_tracts.parquet")
    vt = gpd.read_parquet(RAW / "vehicles_tracts.parquet")[["GEOID", "B08201_001E", "B08201_002E"]]
    t = ct.merge(vt, on="GEOID")
    t["noveh"] = t["B08201_002E"] / t["B08201_001E"]
    t["transit"] = t["B08301_010E"] / t["B08301_001E"]
    pts = gpd.GeoDataFrame(geometry=rp.values, crs=CRS)
    j = gpd.sjoin(pts, t[["noveh", "transit", "geometry"]], how="left", predicate="within")
    j = j[~j.index.duplicated()]
    p["noveh"] = j["noveh"].reindex(pts.index).values
    p["transit"] = j["transit"].reindex(pts.index).values
    top = {"noveh": np.nanmax(p.loc[p.res, "noveh"]), "transit": np.nanmax(p.loc[p.res, "transit"]),
           "vuln_pct": np.nanmax(p.loc[p.res, "vuln_pct"])}
    print("  full dot = highest tract value:", {k: round(float(v), 2) for k, v in top.items()})

    # places: the same features the other views draw (see map/export_web.py)
    stores = gpd.read_parquet(RAW / "snap_stores.parquet").to_crs(CRS)
    store_w = stores["Store_Type"].map({"Supermarket": 1.0, "Super Store": 1.0}).fillna(
        stores["Store_Type"].isin(GROCER_TYPES).map({True: 2 / 3, False: 1 / 3}))
    stops = gpd.read_parquet(RAW / "mbta_stops.parquet").to_crs(CRS).drop_duplicates("STATION")
    lines = unary_union(gpd.read_parquet(RAW / "mbta_lines.parquet").to_crs(CRS).geometry.values)
    sites = assets[assets["asset_type"] != "station"]
    subs = gpd.read_file(ROOT / "data" / "electrical-infrastructure" / "ElecSubstations.geojson").to_crs(CRS)
    subs = subs[subs["NAME"].notna()].drop_duplicates("NAME")
    xy_of = lambda g: np.column_stack([g.geometry.representative_point().x, g.geometry.representative_point().y])

    levels = []
    for s in SPACINGS:
        c = hex_centres(aoi_geom.bounds, s)
        c = c[shapely.contains_xy(area, c[:, 0], c[:, 1])]
        n = len(c)
        dist, idx = cKDTree(c).query(pxy)
        ok = dist <= s
        df = p[ok].assign(cell=idx[ok])
        r = df[df["res"]]
        has_home = np.zeros(n, bool); has_home[r["cell"].unique()] = True
        mean_res = lambda col: r.groupby("cell")[col].mean().reindex(range(n)).values
        v = {}
        # flood: share of 19 points spread over the cell that are on land inside the flood extent
        ang = np.linspace(0, 2 * np.pi, 7)[:-1]
        offs = [(0, 0)] + [(rr * np.cos(a), rr * np.sin(a)) for rr in (s * 0.25, s * 0.45) for a in ang] + [(s * 0.35 * np.cos(a + 0.5), s * 0.35 * np.sin(a + 0.5)) for a in ang]
        for sc in SCENARIOS:
            v[f"f{sc}"] = np.mean([shapely.contains_xy(fgeom[sc], c[:, 0] + dx, c[:, 1] + dy) & shapely.contains_xy(area, c[:, 0] + dx, c[:, 1] + dy) for dx, dy in offs], axis=0)
        v["noveh"] = np.nan_to_num(mean_res("noveh") / top["noveh"]) * has_home
        v["transit"] = np.nan_to_num(mean_res("transit") / top["transit"]) * has_home
        v["vuln"] = np.nan_to_num(mean_res("vuln_pct") / top["vuln_pct"]) * has_home
        # parcel layers: area-weighted over the parcels in each cell
        df = df.assign(_w=df["area_m2"].fillna(0))
        wsum = df.groupby("cell")["_w"].sum().reindex(range(n)).values
        share = lambda x: np.nan_to_num(df.assign(_x=np.asarray(x, float) * df["_w"]).groupby("cell")["_x"].sum().reindex(range(n)).values / wsum)
        for sc in SCENARIOS:
            v[f"expo{sc}"] = share(df[f"flood_frac_{sc}"].fillna(0))
        v["imperv"] = np.clip((share(df["impervious_frac"].fillna(0)) - 0.5) / 0.5, 0, 1)
        v["unpave"] = share(df["unpave_candidate"].astype(float))
        v["owner"] = share(df["owner_type"].eq("public"))
        v["owner_ex"] = share(df["owner_type"].eq("exempt"))
        # point layers: a dot where the feature is
        v["stores"] = in_cell(c, xy_of(stores), s, store_w.values)
        v["assets"] = in_cell(c, xy_of(sites), s)
        v["power"] = in_cell(c, xy_of(subs), s)
        on_line = shapely.distance(shapely.points(c), lines) <= s * 0.5
        v["blueline"] = np.maximum(in_cell(c, xy_of(stops), s), on_line * 0.45)
        lon, lat = TO_LL.transform(c[:, 0], c[:, 1])
        levels.append({"spacing": s, "lon": [round(x, 5) for x in lon], "lat": [round(y, 5) for y in lat],
                       "v": {k: q(a) for k, a in v.items()}})
        print(f"  {s:>3} m grid: {n:>6} cells | with homes {int(has_home.sum())} | mean " + " ".join(f"{k}={np.mean(a):.2f}" for k, a in v.items()))

    OUT.write_text("window.EB=window.EB||{};window.EB.ink=" + json.dumps({"levels": levels}, separators=(",", ":")) + ";")
    print(f"wrote {OUT} ({OUT.stat().st_size / 1e6:.2f} MB)")


if __name__ == "__main__":
    main()
