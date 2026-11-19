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
| `raw/nlcd_impervious_2021_west.tif`, `processed/impervious_frac_26986.tif` | [NLCD 2021](https://www.mrlc.gov/data) impervious surface |
| `processed/dem_1m_26986.tif`, `processed/expanded/dem_1m_west.tif` | [USGS 3DEP](https://www.usgs.gov/3d-elevation-program) 1 m elevation |
| `electrical-infrastructure/ElecSubstations.geojson` | Electrical substations |
| `processed/expanded/parcels.parquet`, `parcels.csv`, `parcel_features.parquet` | Built by `map/pipeline.py` |
