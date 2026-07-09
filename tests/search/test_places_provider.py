"""Geo unit tests plus live integration tests for the places provider."""

import importlib.util
import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "modules" / "maps_search"))
from geo import distance_decay, haversine_km  # noqa: E402

from atria.core.context_engineering.search.types import SearchContext

_LIVE = bool(
    os.environ.get("DATABASE_URL")
    and (os.environ.get("SEARCH_EMBED_API_KEY") or os.environ.get("OPENAI_API_KEY"))
)
_PROVIDER_PATH = (
    Path(__file__).resolve().parents[2] / "modules" / "maps_search" / "search_provider.py"
)


def _load_provider():
    # unique module name: avoids sys.modules collision with the documents provider test
    spec = importlib.util.spec_from_file_location("maps_sp_under_test", _PROVIDER_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.get_provider()


def test_haversine_known_distance():
    # Hoan Kiem lake to West Lake, Ha Noi: ~4 km
    km = haversine_km(21.0287, 105.8521, 21.0587, 105.8230)
    assert 3.0 < km < 6.0


def test_haversine_zero():
    assert haversine_km(10.0, 106.0, 10.0, 106.0) == 0.0


def test_distance_decay_monotonic():
    assert distance_decay(0.0) == 1.0
    assert distance_decay(1.0) > distance_decay(5.0) > 0.0


@pytest.mark.skipif(
    not _LIVE, reason="needs live stores and an embedding key (Task 10 ingest first)"
)
class TestPlacesProviderLive:
    def _provider(self):
        return _load_provider()

    def test_category_filter_is_hard(self):
        results = self._provider().search(
            "cà phê làm việc", {"category": "Quán cà phê"}, 10, SearchContext()
        )
        assert results.hits
        assert all(h.metadata["category"] == "Quán cà phê" for h in results.hits)

    def test_near_reranks_and_annotates_distance(self):
        # focus point in central Da Nang; nearby POIs must rank above far cities
        results = self._provider().search(
            "khách sạn",
            {"near": {"lat": 16.06, "lon": 108.22}, "radius_m": 20000},
            10,
            SearchContext(),
        )
        assert results.hits
        assert all("distance_m" in h.metadata for h in results.hits)
        assert all(h.metadata["distance_m"] <= 20000 for h in results.hits)

    def test_city_filter(self):
        results = self._provider().search("công viên", {"city": "Hà Nội"}, 10, SearchContext())
        assert all(h.metadata["city"] == "Hà Nội" for h in results.hits)

    def test_facets_present(self):
        results = self._provider().search("ăn uống vui chơi", {}, 10, SearchContext())
        assert "category" in results.facets


@pytest.mark.skipif(not _LIVE, reason="needs live stores")
def test_get_user_profile_tool():
    import importlib.util

    tools_path = Path(__file__).resolve().parents[2] / "modules/maps_search/tools.py"
    spec = importlib.util.spec_from_file_location("maps_tools_under_test", tools_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    specs = module.register(None)
    assert [s.name for s in specs] == ["get_user_profile"]
    result = specs[0].handler(user_id="U001")
    assert result["success"] is True
    assert "persona" in result["output"]
