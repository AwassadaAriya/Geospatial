# Boston sea level rise map

## Open the map

Open `docs/index.html` in a browser.

## Rebuild the data

Needs Python 3.12 and [uv](https://docs.astral.sh/uv/).

```sh
uv venv --python 3.12 .venv && source .venv/bin/activate
uv pip install -r requirements.txt

python map/fetch_extra.py
python map/pipeline.py dem parcels assets features score
python map/export_web.py
python map/ink_grid.py
```

Downloads are saved in `data/raw`. 
