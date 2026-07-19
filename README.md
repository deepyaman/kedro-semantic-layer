# kedro-semantic-layer

[![PyPI version](https://img.shields.io/pypi/v/kedro-semantic-layer.svg)](https://pypi.org/project/kedro-semantic-layer/)
[![License](https://img.shields.io/badge/License-Apache_2.0-blue.svg)](https://github.com/deepyaman/kedro-semantic-layer/blob/main/LICENSE)

Define [Boring Semantic Layer](https://github.com/boringdata/boring-semantic-layer) models on your Kedro datasets, straight from the catalog.

`kedro-semantic-layer` is a Kedro plugin that turns dataset `metadata` into semantic models: any [Ibis](https://ibis-project.org)-backed dataset annotated with dimensions, measures, or joins loads as a queryable `SemanticModel` instead of a raw table—in nodes, in `kedro ipython`, everywhere the catalog is used.

## Installation

```console
pip install kedro-semantic-layer
```

Or install the development version from source:

```console
pip install "kedro-semantic-layer @ git+https://github.com/deepyaman/kedro-semantic-layer.git"
```

The plugin registers its hook automatically; no changes to `settings.py` are needed.

## Quickstart

Annotate an Ibis-backed dataset in `conf/base/catalog.yml`:

```yaml
flights:
  type: ibis.FileDataset
  filepath: data/01_raw/flights.parquet
  metadata:
    kedro-semantic-layer:
      dimensions:
        origin: _.origin
        destination:
          expr: _.destination
          description: "Destination airport code"
      measures:
        flight_count: _.count()
        avg_distance:
          expr: _.distance.mean()
          description: "Average distance of flights in miles"
```

Loading the dataset now returns a semantic model:

```python
flights = catalog.load("flights")

flights.group_by("origin").aggregate("flight_count", "avg_distance").execute()
```

## Joins

A `joins:` block references other catalog datasets by name (`model:`). The joined dataset's semantic model is built on demand when the joining dataset is loaded:

```yaml
flights:
  type: ibis.FileDataset
  filepath: data/01_raw/flights.parquet
  metadata:
    kedro-semantic-layer:
      dimensions:
        origin: _.origin
      measures:
        flight_count: _.count()
      joins:
        carriers:
          model: carriers    # another catalog dataset
          type: one          # one | many | cross
          left_on: carrier
          right_on: code

carriers:
  type: ibis.FileDataset
  filepath: data/01_raw/carriers.parquet
  metadata:
    kedro-semantic-layer:
      dimensions:
        name: _.name
```

Joined dimensions and measures are addressed with the join alias as prefix:

```python
flights = catalog.load("flights")

flights.group_by("carriers.name").aggregate("flight_count").execute()
```

Join targets without their own `kedro-semantic-layer` metadata are wrapped as plain semantic tables. Cyclic join definitions are rejected as soon as the catalog is created, with an error naming the cycle.

## Supported metadata keys

Everything under `metadata.kedro-semantic-layer` follows the [Boring Semantic Layer YAML format](https://github.com/boringdata/boring-semantic-layer/blob/main/docs/md/doc/yaml-config.md) and is parsed by its `from_config` API:

| Key | Description |
| --- | --- |
| `dimensions` | Name → Ibis deferred expression, or a dict with `expr`, `description`, `is_entity`, `is_time_dimension`, `smallest_time_grain`, `metadata`, … |
| `measures` | Name → aggregate expression, or a dict with `expr`, `description`, `metadata` |
| `calculated_measures` | Measures referencing other measures by name (e.g. ratios, percent of total) |
| `filter` | Row filter applied to the model (e.g. `_.distance > 1000`) |
| `joins` | Join alias → `{model, type, left_on, right_on, how}`, where `model` names another catalog dataset |

## How it works

On `after_catalog_created`, the plugin wraps the `load()` method of every dataset carrying `kedro-semantic-layer` metadata. The wrapper loads the underlying Ibis table as usual, then hands the metadata to Boring Semantic Layer's `from_config`, resolving any join references through the catalog. Datasets without the metadata key are untouched.

Because the wrapped `load()` closes over the catalog, and Ibis backend connections are not picklable, use the sequential or thread runner (not `ParallelRunner`) for pipelines that load semantic models—the same constraint that already applies to Ibis-backed datasets in general.

## Compatibility notes

The plugin only uses public Boring Semantic Layer APIs (`from_config`,
`to_semantic_table`, `SemanticModel`, `SemanticTable`). On the Kedro side, it
wraps `load()` through `AbstractDataset._load_wrapper` — the same mechanism
Kedro itself uses to wrap dataset loading (e.g. for versioning). CI runs
against the current Kedro release on Python 3.10–3.14; the test suite is what
catches a Kedro release changing that mechanism.

It also imports `kedro.utils._format_rich` and `_has_rich_handler`, private
helpers used only for optional rich-aware log formatting; the import is
guarded, falling back to plain logging if they're unavailable. This isn't
hypothetical—`_format_rich` existed in Kedro 0.19.8–0.19.11, was removed in
0.19.12–0.19.13, and returned in 0.19.14, all within the `kedro>=0.19.7`
range this plugin declares.

## Example

See [`examples/airlines`](https://github.com/deepyaman/kedro-semantic-layer/tree/main/examples/airlines) for a runnable project querying the Malloy airlines dataset, including the flights→carriers join above.
