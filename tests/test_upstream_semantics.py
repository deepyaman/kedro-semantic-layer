"""Pin the upstream Boring Semantic Layer behaviors that the plugin's config
surface exposes, so a boring-semantic-layer version bump that changes one of
them fails here by name rather than surfacing as a confusing bug in a
downstream project.
"""

import datetime

import ibis
import pandas as pd
import pytest
from kedro.io import DataCatalog
from kedro_datasets.ibis import TableDataset

from helpers import InMemoryTableDataset, make_catalog
from kedro_semantic_layer.plugin import hooks


ORDERS = ibis.memtable(
    {
        "order_id": [1, 2, 3, 4, 5],
        "customer_id": [1, 1, 2, 3, 3],
    }
)
# Three distinct join-key values (customer_id) map to two distinct regions,
# so deferred vs. inline join semantics produce different row counts (3 vs 2).
CUSTOMERS = ibis.memtable(
    {
        "customer_id": [1, 2, 3],
        "region": ["A", "A", "B"],
    }
)
ORDERS_JOIN_CONFIG = {
    "dimensions": {"customer_id": "_.customer_id"},
    "measures": {"order_count": "_.count()"},
    "joins": {
        "customers": {
            "model": "customers",
            "type": "one",
            "left_on": "customer_id",
            "right_on": "customer_id",
        }
    },
}


def make_orders_catalog(customers_config: dict) -> DataCatalog:
    return make_catalog(
        orders=InMemoryTableDataset(
            ORDERS, metadata={"kedro-semantic-layer": ORDERS_JOIN_CONFIG}
        ),
        customers=InMemoryTableDataset(
            CUSTOMERS, metadata={"kedro-semantic-layer": customers_config}
        ),
    )


def test_is_entity_join_defers_until_after_aggregation():
    """With `is_entity: true` on the join target's key, the join is deferred
    until after aggregation (boringdata/boring-semantic-layer#219, #220):
    grouping by the joined dimension aggregates at the join-key grain, then
    decorates, so duplicate joined-dimension values survive as separate rows.
    """
    catalog = make_orders_catalog(
        {
            "dimensions": {
                "customer_id": {"expr": "_.customer_id", "is_entity": True},
                "region": "_.region",
            }
        }
    )

    result = (
        catalog.load("orders")
        .group_by("customers.region")
        .aggregate("order_count")
        .order_by("customers.region")
        .execute()
    )

    # One row per join-key value (customer_id); region "A" repeats.
    assert list(result["customers.region"]) == ["A", "A", "B"]
    assert result["order_count"].sum() == 5


def test_join_without_is_entity_collapses_to_dim_grain():
    """Without `is_entity`, the join is applied inline, so the same group_by
    collapses to the joined dimension's own grain.
    """
    catalog = make_orders_catalog(
        {
            "dimensions": {
                "customer_id": "_.customer_id",
                "region": "_.region",
            }
        }
    )

    result = (
        catalog.load("orders")
        .group_by("customers.region")
        .aggregate("order_count")
        .order_by("customers.region")
        .execute()
    )

    # One row per distinct joined-dimension value.
    assert list(result["customers.region"]) == ["A", "B"]
    assert list(result["order_count"]) == [3, 2]


EVENTS = ibis.memtable(
    {
        "event_id": [1, 2, 3],
        "event_date": [
            datetime.date(2024, 1, 1),
            datetime.date(2024, 1, 1),
            datetime.date(2024, 1, 2),
        ],
    }
)


def test_time_dimension_metadata_through_hook():
    """`is_time_dimension` and `smallest_time_grain` keys pass through the
    hook, and an aggregate grouped by the time dimension executes.
    """
    config = {
        "dimensions": {
            "event_date": {
                "expr": "_.event_date",
                "is_time_dimension": True,
                "smallest_time_grain": "TIME_GRAIN_DAY",
            }
        },
        "measures": {"event_count": "_.count()"},
    }
    catalog = make_catalog(
        events=InMemoryTableDataset(EVENTS, metadata={"kedro-semantic-layer": config})
    )

    events = catalog.load("events")

    assert events.get_dimensions()["event_date"].is_time_dimension is True
    result = (
        events.group_by("event_date")
        .aggregate("event_count")
        .order_by("event_date")
        .execute()
    )
    assert list(result["event_count"]) == [2, 1]


def test_dimension_only_query():
    """`group_by(*dims).aggregate()` with zero measures returns exactly the
    distinct dimension-tuple rows.
    """
    table = ibis.memtable({"a": [1, 1, 2, 2], "b": ["x", "x", "y", "z"]})
    config = {"dimensions": {"a": "_.a", "b": "_.b"}}
    catalog = make_catalog(
        t=InMemoryTableDataset(table, metadata={"kedro-semantic-layer": config})
    )

    result = catalog.load("t").group_by("a", "b").aggregate().execute()

    assert len(result) == 3
    got = {tuple(row) for row in result[["a", "b"]].itertuples(index=False)}
    assert got == {(1, "x"), (2, "y"), (2, "z")}


KEYSET = ibis.memtable({"k": [5, 4, 3, 2, 1], "v": ["a", "b", "c", "d", "e"]})


def test_keyset_pagination_chain_is_lazy():
    """A `filter -> group_by(*dims).aggregate() -> order_by -> limit` chain
    stays unexecuted until `.execute()`, and paging with a cursor from the
    previous page's last row yields the expected non-overlapping rows.
    """
    config = {"dimensions": {"k": "_.k", "v": "_.v"}}
    catalog = make_catalog(
        t=InMemoryTableDataset(KEYSET, metadata={"kedro-semantic-layer": config})
    )
    model = catalog.load("t")

    page_size = 2
    chain = (
        model.filter(lambda t: t.k < 6)
        .group_by("k", "v")
        .aggregate()
        .order_by(ibis.desc("k"))
        .limit(page_size)
    )
    assert not isinstance(chain, pd.DataFrame)
    assert hasattr(chain, "execute")

    page1 = chain.execute()
    cursor = int(page1["k"].iloc[-1])

    page2 = (
        model.filter(lambda t: (t.k < 6) & (t.k < cursor))
        .group_by("k", "v")
        .aggregate()
        .order_by(ibis.desc("k"))
        .limit(page_size)
        .execute()
    )

    assert list(page1["k"]) == [5, 4]
    assert list(page2["k"]) == [3, 2]


def test_string_form_calculated_measure():
    """`calculated_measures` accepts the plain-string form, not only the dict
    form that `test_calculated_measures` covers.
    """
    table = ibis.memtable({"hits": [3], "visits": [10]})
    config = {
        "measures": {"hits": "_.hits.sum()", "visits": "_.visits.sum()"},
        "calculated_measures": {"hit_rate": "_.hits / _.visits"},
    }
    catalog = make_catalog(
        stats=InMemoryTableDataset(table, metadata={"kedro-semantic-layer": config})
    )

    result = catalog.load("stats").aggregate("hits", "visits", "hit_rate").execute()

    assert result["hit_rate"][0] == pytest.approx(0.3)


def test_shared_connection_table_dataset(tmp_path):
    """Two `kedro_datasets.ibis.TableDataset` entries sharing an identical
    `connection` config (and therefore a cached backend connection): the
    metadata-carrying entry loads as a semantic model while the plain entry
    stays an Ibis table.
    """
    db_path = tmp_path / "shared.duckdb"
    con = ibis.duckdb.connect(str(db_path))
    con.create_table(
        "orders", ibis.memtable({"order_id": [1, 2, 3], "amount": [10.0, 20.0, 30.0]})
    )
    con.disconnect()

    connection = {"backend": "duckdb", "database": str(db_path)}
    catalog = DataCatalog(
        {
            "orders": TableDataset(
                table_name="orders",
                connection=connection,
                metadata={
                    "kedro-semantic-layer": {
                        "dimensions": {"order_id": "_.order_id"},
                        "measures": {"total": "_.amount.sum()"},
                    }
                },
            ),
            # Second entry sharing the identical connection dict, without
            # semantic-layer metadata -- must stay untouched by the hook.
            "orders_plain": TableDataset(table_name="orders", connection=connection),
        }
    )
    hooks.after_catalog_created(catalog)

    result = catalog.load("orders").aggregate("total").execute()

    assert result["total"][0] == pytest.approx(60.0)
    assert isinstance(catalog.load("orders_plain"), ibis.Table)


def test_materialized_view_dataset(tmp_path):
    """A `kedro_datasets.ibis.TableDataset` backed by a database VIEW (rather
    than a table) carrying metadata loads as a semantic model and aggregates
    correctly.
    """
    db_path = tmp_path / "view.duckdb"
    con = ibis.duckdb.connect(str(db_path))
    con.create_table(
        "orders", ibis.memtable({"order_id": [1, 2, 3], "amount": [10.0, 20.0, 30.0]})
    )
    con.create_view("big_orders", con.table("orders").filter(ibis._.amount > 15))
    con.disconnect()

    connection = {"backend": "duckdb", "database": str(db_path)}
    catalog = DataCatalog(
        {
            "big_orders": TableDataset(
                table_name="big_orders",
                connection=connection,
                metadata={
                    "kedro-semantic-layer": {
                        "dimensions": {"order_id": "_.order_id"},
                        "measures": {"total": "_.amount.sum()"},
                    }
                },
            )
        }
    )
    hooks.after_catalog_created(catalog)

    result = catalog.load("big_orders").aggregate("total").execute()

    assert result["total"][0] == pytest.approx(50.0)


def test_join_to_metadata_carrying_view_entry(tmp_path):
    """A join whose target is itself a metadata-carrying view entry in the
    same catalog resolves and decorates correctly.
    """
    db_path = tmp_path / "join_view.duckdb"
    con = ibis.duckdb.connect(str(db_path))
    con.create_table(
        "sales",
        ibis.memtable(
            {"sale_id": [1, 2, 3], "product": ["widget", "gadget", "widget"]}
        ),
    )
    con.create_view(
        "products",
        con.table("sales").select("product").distinct().mutate(category=ibis._.product),
    )
    con.disconnect()

    connection = {"backend": "duckdb", "database": str(db_path)}
    catalog = DataCatalog(
        {
            "sales": TableDataset(
                table_name="sales",
                connection=connection,
                metadata={
                    "kedro-semantic-layer": {
                        "dimensions": {
                            "sale_id": "_.sale_id",
                            "product": "_.product",
                        },
                        "measures": {"sale_count": "_.count()"},
                        "joins": {
                            "products": {
                                "model": "products",
                                "type": "one",
                                "left_on": "product",
                                "right_on": "product",
                            }
                        },
                    }
                },
            ),
            "products": TableDataset(
                table_name="products",
                connection=connection,
                metadata={
                    "kedro-semantic-layer": {
                        "dimensions": {
                            "product": "_.product",
                            "category": "_.category",
                        }
                    }
                },
            ),
        }
    )
    hooks.after_catalog_created(catalog)

    sales = catalog.load("sales")
    result = (
        sales.group_by("products.category")
        .aggregate("sale_count")
        .order_by("products.category")
        .execute()
    )

    assert list(result["products.category"]) == ["gadget", "widget"]
    assert list(result["sale_count"]) == [1, 2]
