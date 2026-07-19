import ibis
import pytest
from boring_semantic_layer import SemanticTable
from kedro.io import CachedDataset

from helpers import InMemoryTableDataset, make_catalog


FLIGHTS = ibis.memtable(
    {
        "carrier": ["AA", "AA", "UA", "DL"],
        "origin": ["JFK", "LGA", "ORD", "ATL"],
        "destination": ["LAX", "ORD", "SFO", "JFK"],
        "distance": [2475.0, 733.0, 1846.0, 760.0],
    }
)
CARRIERS = ibis.memtable(
    {
        "code": ["AA", "UA", "DL"],
        "name": ["American Airlines", "United Airlines", "Delta Air Lines"],
    }
)

FLIGHTS_CONFIG = {
    "dimensions": {
        "origin": "_.origin",
        "destination": {
            "expr": "_.destination",
            "description": "Destination airport code",
        },
    },
    "measures": {
        "flight_count": "_.count()",
        "avg_distance": {
            "expr": "_.distance.mean()",
            "description": "Average flight distance in miles",
        },
    },
}


def test_load_builds_semantic_model():
    catalog = make_catalog(
        flights=InMemoryTableDataset(
            FLIGHTS, metadata={"kedro-semantic-layer": FLIGHTS_CONFIG}
        )
    )

    flights = catalog.load("flights")

    assert isinstance(flights, SemanticTable)
    result = (
        flights.group_by("origin")
        .aggregate("flight_count", "avg_distance")
        .order_by("origin")
        .execute()
    )
    assert result["flight_count"].sum() == 4
    assert set(result["origin"]) == {"ATL", "JFK", "LGA", "ORD"}


def test_dataset_without_metadata_is_untouched():
    catalog = make_catalog(flights=InMemoryTableDataset(FLIGHTS))

    assert catalog.load("flights") is FLIGHTS


def test_calculated_measures():
    config = {
        **FLIGHTS_CONFIG,
        "calculated_measures": {
            "avg_distance_km": {
                "expr": "_.avg_distance * 1.609",
                "description": "Average flight distance in kilometers",
            }
        },
    }
    catalog = make_catalog(
        flights=InMemoryTableDataset(FLIGHTS, metadata={"kedro-semantic-layer": config})
    )

    flights = catalog.load("flights")
    result = flights.aggregate("avg_distance", "avg_distance_km").execute()
    assert result["avg_distance_km"][0] == pytest.approx(
        result["avg_distance"][0] * 1.609
    )


def test_filter():
    config = {**FLIGHTS_CONFIG, "filter": "_.distance > 1000"}
    catalog = make_catalog(
        flights=InMemoryTableDataset(FLIGHTS, metadata={"kedro-semantic-layer": config})
    )

    result = catalog.load("flights").aggregate("flight_count").execute()
    assert result["flight_count"][0] == 2


def make_joined_catalog(join_config: dict, carriers_metadata: dict | None = None):
    config = {**FLIGHTS_CONFIG, "joins": join_config}
    return make_catalog(
        flights=InMemoryTableDataset(
            FLIGHTS, metadata={"kedro-semantic-layer": config}
        ),
        carriers=InMemoryTableDataset(CARRIERS, metadata=carriers_metadata),
    )


CARRIERS_METADATA = {
    "kedro-semantic-layer": {
        "dimensions": {"name": "_.name"},
        "measures": {"carrier_count": "_.count()"},
    }
}


@pytest.mark.parametrize("join_type", ["one", "many"])
def test_join_to_semantic_dataset(join_type):
    catalog = make_joined_catalog(
        {
            "carriers": {
                "model": "carriers",
                "type": join_type,
                "left_on": "carrier",
                "right_on": "code",
            }
        },
        carriers_metadata=CARRIERS_METADATA,
    )

    flights = catalog.load("flights")
    result = (
        flights.group_by("carriers.name")
        .aggregate("flight_count")
        .order_by("carriers.name")
        .execute()
    )
    assert list(result["carriers.name"]) == [
        "American Airlines",
        "Delta Air Lines",
        "United Airlines",
    ]
    assert list(result["flight_count"]) == [2, 1, 1]


def test_join_alias_differs_from_model_name():
    catalog = make_joined_catalog(
        {
            "operator": {
                "model": "carriers",
                "type": "one",
                "left_on": "carrier",
                "right_on": "code",
            }
        },
        carriers_metadata=CARRIERS_METADATA,
    )

    flights = catalog.load("flights")
    result = flights.group_by("operator.name").aggregate("flight_count").execute()
    assert set(result["operator.name"]) == {
        "American Airlines",
        "Delta Air Lines",
        "United Airlines",
    }


def test_join_to_plain_dataset_is_auto_wrapped():
    catalog = make_joined_catalog(
        {
            "carriers": {
                "model": "carriers",
                "type": "one",
                "left_on": "carrier",
                "right_on": "code",
            }
        },
        carriers_metadata=None,
    )

    flights = catalog.load("flights")
    result = flights.group_by("origin").aggregate("flight_count").execute()
    assert result["flight_count"].sum() == 4


def test_cross_join():
    catalog = make_joined_catalog(
        {"carriers": {"model": "carriers", "type": "cross"}},
        carriers_metadata=CARRIERS_METADATA,
    )

    result = catalog.load("flights").aggregate("flight_count").execute()
    assert result["flight_count"][0] == 12  # 4 flights x 3 carriers


def test_transitive_join_chain():
    bookings = ibis.memtable({"origin": ["JFK", "ORD", "JFK"], "seats": [2, 3, 1]})
    bookings_config = {
        "dimensions": {"origin": "_.origin"},
        "measures": {"booking_count": "_.count()"},
        "joins": {
            "flights": {
                "model": "flights",
                "type": "many",
                "left_on": "origin",
                "right_on": "origin",
            }
        },
    }
    flights_config = {
        **FLIGHTS_CONFIG,
        "joins": {
            "carriers": {
                "model": "carriers",
                "type": "one",
                "left_on": "carrier",
                "right_on": "code",
            }
        },
    }
    catalog = make_catalog(
        bookings=InMemoryTableDataset(
            bookings, metadata={"kedro-semantic-layer": bookings_config}
        ),
        flights=InMemoryTableDataset(
            FLIGHTS, metadata={"kedro-semantic-layer": flights_config}
        ),
        carriers=InMemoryTableDataset(CARRIERS, metadata=CARRIERS_METADATA),
    )

    result = (
        catalog.load("bookings")
        .group_by("flights.origin")
        .aggregate("booking_count")
        .order_by("flights.origin")
        .execute()
    )
    assert list(result["flights.origin"]) == ["JFK", "ORD"]
    assert list(result["booking_count"]) == [2, 1]


def test_cached_dataset_avoids_redundant_join_loads():
    """Wrapping a frequently-joined dataset in `kedro.io.CachedDataset` loads
    it once per session, even when multiple other datasets join to it.
    `metadata` must live on the `CachedDataset` entry itself -- the hook
    checks the top-level catalog entry, not the `dataset:` it wraps.
    """
    load_count = {"carriers": 0}

    class CountingCarriers(InMemoryTableDataset):
        def load(self) -> ibis.Table:
            load_count["carriers"] += 1
            return super().load()

    join_config = {
        "carriers": {
            "model": "carriers",
            "type": "one",
            "left_on": "carrier",
            "right_on": "code",
        }
    }
    flights_config = {**FLIGHTS_CONFIG, "joins": join_config}
    catalog = make_catalog(
        flights=InMemoryTableDataset(
            FLIGHTS, metadata={"kedro-semantic-layer": flights_config}
        ),
        bookings=InMemoryTableDataset(
            FLIGHTS, metadata={"kedro-semantic-layer": flights_config}
        ),
        carriers=CachedDataset(
            dataset=CountingCarriers(CARRIERS), metadata=CARRIERS_METADATA
        ),
    )

    catalog.load("flights")
    catalog.load("bookings")
    catalog.load("flights")

    assert load_count["carriers"] == 1


def test_join_cycle_raises_at_catalog_creation():
    flights_config = {
        **FLIGHTS_CONFIG,
        "joins": {
            "carriers": {
                "model": "carriers",
                "type": "one",
                "left_on": "carrier",
                "right_on": "code",
            }
        },
    }
    carriers_config = {
        "dimensions": {"name": "_.name"},
        "joins": {
            "flights": {
                "model": "flights",
                "type": "one",
                "left_on": "code",
                "right_on": "carrier",
            }
        },
    }

    with pytest.raises(
        ValueError,
        match=r"cycle: (flights -> carriers -> flights|carriers -> flights -> carriers)",
    ):
        make_catalog(
            flights=InMemoryTableDataset(
                FLIGHTS, metadata={"kedro-semantic-layer": flights_config}
            ),
            carriers=InMemoryTableDataset(
                CARRIERS, metadata={"kedro-semantic-layer": carriers_config}
            ),
        )
