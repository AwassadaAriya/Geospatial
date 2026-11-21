# Boston sea level rise map
Research question: How is urbanization changing Boston's capacity to buffer heat and stormwater, and how does this change overlap with areas projected to experience sea-level-rise inundation?

## Rebuild the data

Needs Python 3.12 and [uv](https://docs.astral.sh/uv/).

```sh
uv venv --python 3.12 .venv && source .venv/bin/activate
uv pip install -r requirements.txt

python map/fetch_extra.py
python map/pipeline.py dem parcels assets nlcd features score
python map/export_web.py
python map/ink_grid.py
```

Downloads are saved in `data/raw`, and stages skip any file that already exists there. Add `--refresh` to download them again, e.g. `python map/pipeline.py --refresh nlcd features score`. This only refreshes what `pipeline.py` downloads (west parcels, west DEM, assets, NLCD). `fetch_extra.py` keeps its own cache. Refreshing `parcels` pulls the live assessing service, so the parcel count can change.

East Boston's parcels, the DEM and a few other inputs come from `east_boston_slr_baseline_(2).ipynb`. They are committed, so the steps above work without it, but rebuilding them from scratch needs the notebook. See [data/README.md](data/README.md) for which files, and for how impervious surface is measured and its caveats.

On macOS with python.org Python, downloads may fail with `CERTIFICATE_VERIFY_FAILED`. Fix it with `export SSL_CERT_FILE=$(python -c "import certifi; print(certifi.where())")`. 
