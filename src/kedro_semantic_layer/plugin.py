import logging
from collections.abc import Callable
from functools import wraps
from types import MethodType
from typing import TYPE_CHECKING

import ibis
from boring_semantic_layer import SemanticModel, to_semantic_table
from boring_semantic_layer.yaml import _parse_dimensions, _parse_measures
from kedro.framework.hooks import hook_impl
from kedro.io import AbstractDataset, DataCatalog
from kedro.utils import _format_rich, _has_rich_handler

_logger = logging.getLogger(__name__)


def _get_load_func(cls: AbstractDataset) -> Callable:
    return (
        # https://github.com/kedro-org/kedro/blob/52458c2/kedro/io/core.py#L278-L280
        cls.load
        if not getattr(cls.load, "__loadwrapped__", False)
        else cls.load.__wrapped__  # type: ignore[attr-defined]
    )


def _build_semantic_model(
    table: ibis.Table, dataset_name: str, config: dict[str, str]
) -> SemanticModel:
    semantic_table = to_semantic_table(table, name=dataset_name)

    if dimensions := config.get("dimensions"):
        semantic_table = semantic_table.with_dimensions(**_parse_dimensions(dimensions))

    if measures := config.get("measures"):
        semantic_table = semantic_table.with_measures(**_parse_measures(measures))

    return semantic_table


def _load_wrapper(
    load_func: Callable, dataset_name: str, config: dict[str, str]
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
        return _build_semantic_model(data, dataset_name, config)

    load.__annotations__["return"] = SemanticModel
    return load


class DataCatalogHooks:
    @hook_impl
    def after_catalog_created(self, catalog: DataCatalog):
        for dataset_name, dataset in catalog.items():
            if metadata := getattr(dataset, "metadata", None):
                if "kedro-semantic-layer" in metadata:
                    config = metadata["kedro-semantic-layer"]
                    dataset.load = MethodType(
                        dataset._load_wrapper(
                            _load_wrapper(_get_load_func(dataset), dataset_name, config)
                        ),
                        dataset,
                    )


hooks = DataCatalogHooks()
