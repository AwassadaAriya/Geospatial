# Boston sea level rise map
Research question: How is urbanization changing Boston's capacity to buffer heat and stormwater, and how does this change overlap with areas projected to experience sea-level-rise inundation?

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
