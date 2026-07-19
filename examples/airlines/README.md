# Airlines

[![Powered by Kedro](https://img.shields.io/badge/powered_by-kedro-ffc900?logo=kedro)](https://kedro.org)

A minimal Kedro project showing [kedro-semantic-layer](../..) in action: dimensions, measures, and a join between datasets are defined entirely in `conf/base/catalog.yml`, on top of `ibis.FileDataset` entries for the [Malloy airlines sample data](https://github.com/malloydata/malloy-samples).

[Watch the demo](https://github.com/deepyaman/kedro-semantic-layer/raw/main/examples/airlines/query.webm).

## Try it

From the repository root (uses the [uv workspace](https://docs.astral.sh/uv/concepts/projects/workspaces/)):

```console
uv sync
cd examples/airlines
uv run kedro ipython
```

Loading `flights` returns a Boring Semantic Layer model instead of a raw Ibis table:

```python
flights = catalog.load("flights")

flights.group_by("carriers.name").aggregate("flight_count", "avg_distance").execute()
```

`carriers.name` comes from the `joins:` block on `flights`: loading `flights` builds the `carriers` semantic model on demand, no separate `catalog.load("carriers")` call needed.

## Where to look

- `conf/base/catalog.yml`: dimensions, measures, and the flights→carriers join, all declared as dataset `metadata`
- `query.tape`: the [VHS](https://github.com/charmbracelet/vhs) script used to record the demo above
