"""Shared catalog-building helpers for the test modules."""

import ibis
from kedro.io import AbstractDataset, DataCatalog

from kedro_semantic_layer.plugin import hooks


class InMemoryTableDataset(AbstractDataset):
    def __init__(self, table: ibis.Table, metadata: dict | None = None):
        self._table = table
        self.metadata = metadata

    def load(self) -> ibis.Table:
        return self._table

    def save(self, data: ibis.Table) -> None:
        raise NotImplementedError

    def _describe(self) -> dict:
        return {}


def make_catalog(**datasets: AbstractDataset) -> DataCatalog:
    catalog = DataCatalog(datasets)
    hooks.after_catalog_created(catalog)
    return catalog
