# Data

| file | source |
|---|---|
| `raw/neighborhoods.parquet` | [Boston Neighborhood Boundaries](https://data.boston.gov/dataset/bpda-neighborhood-boundaries) |
| `raw/parcels_raw.parquet` | [Property Assessment FY26](https://gis.boston.gov/arcgis/rest/services/Assessing/Property_Assessment_FY26/MapServer), East Boston |
| `raw/parcels_raw_west.parquet` | [Property Assessment FY25](https://gis.boston.gov/arcgis/rest/services/Assessing/Property_Assessment_FY25/MapServer), other neighbourhoods |
| `raw/flood_21.parquet`, `raw/flood_36.parquet` | Climate Ready Boston [21 in](https://data.boston.gov/dataset/21inch-sea-level-rise-high-tide) and [36 in](https://data.boston.gov/dataset/36inch-sea-level-rise-high-tide) sea level rise at high tide |
| `raw/social_vuln.parquet` | [Climate Ready Boston Social Vulnerability](https://data.boston.gov/dataset/climate-ready-boston-social-vulnerability) |
| `raw/assets_study.parquet` | [Analyze Boston](https://data.boston.gov) schools, fire, police, hospitals, community centres |
| `raw/mbta_lines.parquet`, `raw/mbta_stops.parquet` | [MassGIS MBTA Rapid Transit](https://www.mass.gov/info-details/massgis-data-mbta-rapid-transit) |
| `raw/snap_stores.parquet` | [USDA SNAP Retailer Locator](https://www.fns.usda.gov/snap/retailer-locator) |
| `raw/commute_tracts.parquet`, `raw/vehicles_tracts.parquet` | US Census ACS tables B08301 and B08201, via Esri Living Atlas |
| `raw/land_tracts.parquet` | Esri Living Atlas ACS tract boundaries |
| `raw/boston_street_segments.parquet` | [Boston Street Segments](https://data.boston.gov/dataset/boston-street-segments-sam-system) |
| `raw/nlcd_impervious_2021.tif`, `raw/nlcd_impervious_2001.tif` | [NLCD 2021 release](https://www.mrlc.gov/data) percent impervious for 2021 and 2001, whole study area plus 200 m, one request so both years share one 30 m grid (`pipeline.py nlcd`) |
| `processed/impervious_frac_26986.tif` | East Boston impervious from the notebook (NLCD 2021 resampled onto the 1 m DEM grid). Only used for the `impervious_share_notebook` comparison column |
| `raw/nlcd_impervious_2021_west.tif` | Superseded by `raw/nlcd_impervious_2021.tif`; no script reads it any more, safe to delete |
| `processed/dem_1m_26986.tif`, `processed/expanded/dem_1m_west.tif` | [USGS 3DEP](https://www.usgs.gov/3d-elevation-program) 1 m elevation |
| `electrical-infrastructure/ElecSubstations.geojson` | Electrical substations |
| `processed/expanded/parcels.parquet`, `parcels.csv`, `parcel_features.parquet` | Built by `map/pipeline.py` |

## Where each file comes from

`map/pipeline.py` and `map/fetch_extra.py` download most of the raw files. These East Boston inputs come only from `east_boston_slr_baseline_(2).ipynb` and have no script in `map/` yet: `raw/neighborhoods.parquet`, `raw/parcels_raw.parquet`, `raw/flood_21.parquet`, `raw/flood_36.parquet`, `raw/social_vuln.parquet`, `processed/dem_1m_26986.tif` and `processed/impervious_frac_26986.tif`. They are committed, so a normal rebuild works without the notebook. Rebuilding them from scratch means running the notebook, which expects its Google Drive folder. Impervious surface no longer depends on the notebook; its raster only feeds the comparison column.

## Impervious surface

`impervious_frac` (2021) and `impervious_share_2001` use the same method for all ten neighbourhoods: the mean NLCD percent impervious over every 30 m cell a parcel touches, divided by 100. "Public paved land" (`unpave_candidate`) is a public or tax-exempt owner with `impervious_frac` of at least `PAVED_MIN_SHARE` (0.5, set at the top of `map/pipeline.py`).

`impervious_share_notebook` keeps East Boston's old values for comparison. When the method was switched (Nov 2026), East Boston's public paved count stayed at 355, with 4 parcels changing status (2 gained, 2 lost). Rerunning `pipeline.py score` prints this comparison.

Caveats:
- **30 m cells, small lots.** Most Boston parcels are smaller than one NLCD cell, so a parcel's value is mostly its neighbourhood's value. Read it as "paved surroundings", not a measurement of the lot.
- **Grid alignment.** pygeohydro fetches NLCD from the MRLC WMS, reprojected to a lat/lon grid at about 30 m. The grid depends on the extent requested, so a different extent shifts parcel values slightly: in the nine west neighbourhoods, where only the extent changed, the median parcel moved by 0.015 and 7 parcels flipped public paved status.
- **Comparing 2001 with 2021.** Both years come from the NLCD 2021 release, which reprocessed every year with one method, so they are meant to be compared. Even so, NLCD maps impervious change mostly where land cover also changed, misses impervious surface under tree canopy, and small differences are within the error of the method. Differences of a few percentage points on one parcel should not be read as real change. Do not compare with values from earlier NLCD releases. [Annual NLCD](https://www.usgs.gov/centers/eros/science/annual-national-land-cover-database) (1985 onwards, one method for every year) is a better source if the map's change-over-time view becomes central.
