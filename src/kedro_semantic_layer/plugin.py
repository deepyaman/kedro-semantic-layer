import logging
from collections.abc import Callable
from functools import wraps
from graphlib import CycleError, TopologicalSorter
from types import MethodType

import ibis
from boring_semantic_layer import (
    SemanticModel,
    SemanticTable,
    from_config,
    to_semantic_table,
)
from kedro.framework.hooks import hook_impl
from kedro.io import AbstractDataset, DataCatalog

try:
    # Match Kedro core's rich-aware log formatting where available; fall back
    # to plain logging if these Kedro-internal helpers move or disappear.
    from kedro.utils import _format_rich, _has_rich_handler
except ImportError:  # pragma: no cover

    def _format_rich(value: str, markup: str) -> str:
        return value

    def _has_rich_handler(*args) -> bool:
        return False


_logger = logging.getLogger(__name__)


def _get_load_func(cls: AbstractDataset) -> Callable:
    return (
        # https://github.com/kedro-org/kedro/blob/52458c2/kedro/io/core.py#L278-L280
        cls.load
        if not getattr(cls.load, "__loadwrapped__", False)
        else cls.load.__wrapped__  # type: ignore[attr-defined]
    )


def _check_join_cycles(configs: dict[str, dict]) -> None:
    """Reject join definitions that reference each other in a cycle.

    Loading a dataset loads the datasets its joins reference, so a cycle
    would otherwise only surface as a ``RecursionError`` at load time.
    """
    graph = {
        dataset_name: {
            model_name
            for join_config in (config.get("joins") or {}).values()
            # Self-joins don't recurse; Boring Semantic Layer resolves them
            # from the model under construction.
            if (model_name := join_config.get("model")) and model_name != dataset_name
        }
        for dataset_name, config in configs.items()
    }
    try:
        TopologicalSorter(graph).prepare()
    except CycleError as exc:
        raise ValueError(
            f"Catalog joins form a cycle: {' -> '.join(exc.args[1])}"
        ) from exc


def _resolve_join_models(
    catalog: DataCatalog, dataset_name: str, config: dict
) -> dict[str, SemanticTable]:
    """Load semantic models for catalog datasets referenced by join definitions."""
    models: dict[str, SemanticTable] = {}
    for join_config in (config.get("joins") or {}).values():
        model_name = join_config.get("model")
        # Boring Semantic Layer resolves self-joins from the model under
        # construction and validates missing/unknown "model" references.
        if not model_name or model_name == dataset_name or model_name in models:
            continue
        loaded = catalog.load(model_name)
        if not isinstance(loaded, SemanticTable):
            loaded = to_semantic_table(loaded, name=model_name)
        models[model_name] = loaded
    return models


def _build_semantic_model(
    table: ibis.Table, dataset_name: str, config: dict, catalog: DataCatalog
) -> SemanticModel:
    tables = {
        dataset_name: table,
        **_resolve_join_models(catalog, dataset_name, config),
    }
    models = from_config(
        {dataset_name: {**config, "table": dataset_name}}, tables=tables
    )
    return models[dataset_name]


def _load_wrapper(
    load_func: Callable, dataset_name: str, config: dict, catalog: DataCatalog
) -> Callable:
    """Decorate `load_func` with code to parse semantic layer config."""

    @wraps(load_func)
    def load(self):
        data = load_func(self)
        _logger.info(
            "Building semantic model for %s (%s)...",
            _format_rich(dataset_name, "dark_orange")
            if _has_rich_handler()
            else dataset_name,
            type(self).__name__,
            extra={"markup": True},
        )
        return _build_semantic_model(data, dataset_name, config, catalog)

    load.__annotations__["return"] = SemanticModel
    return load


class DataCatalogHooks:
    @hook_impl
    def after_catalog_created(self, catalog: DataCatalog):
        semantic_datasets: dict[str, tuple[AbstractDataset, dict]] = {}
        for dataset_name, dataset in catalog.items():
            if metadata := getattr(dataset, "metadata", None):
                if "kedro-semantic-layer" in metadata:
                    semantic_datasets[dataset_name] = (
                        dataset,
                        metadata["kedro-semantic-layer"],
                    )

        _check_join_cycles(
            {name: config for name, (_, config) in semantic_datasets.items()}
        )

        for dataset_name, (dataset, config) in semantic_datasets.items():
            # `_load_wrapper` is the mechanism Kedro itself uses to wrap a
            # dataset's `load()` (e.g. for versioning); reuse it rather than
            # reimplementing dataset-wrapping.
            dataset.load = MethodType(
                dataset._load_wrapper(
                    _load_wrapper(
                        _get_load_func(dataset), dataset_name, config, catalog
                    )
                ),
                dataset,
            )


hooks = DataCatalogHooks()
