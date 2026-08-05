"""Tests for parsing, storage idempotency, and trend analysis.

These run fully offline: no network calls, no live API dependency.
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from analyze import Trend, build_trend, rank_by_momentum
from roblox_api import parse_games_payload
from storage import SnapshotStore

TIMESTAMP = "2026-01-01T00:00:00+00:00"


def sample_payload():
    return {
        "data": [
            {"id": 1, "name": "Alpha", "playing": 100, "visits": 5000, "favoritedCount": 50},
            {"id": 2, "name": "Beta", "playing": 200, "visits": 8000, "favoritedCount": 80},
        ]
    }


class TestParsing:
    def test_parses_valid_records(self):
        snapshots = parse_games_payload(sample_payload(), TIMESTAMP)
        assert len(snapshots) == 2
        assert snapshots[0].name == "Alpha"
        assert snapshots[0].playing == 100

    def test_skips_records_missing_id_or_name(self):
        payload = {"data": [
            {"name": "No ID", "playing": 5},
            {"id": 9, "playing": 5},
            {"id": 10, "name": "Valid", "playing": 5},
        ]}
        assert len(parse_games_payload(payload, TIMESTAMP)) == 1

    def test_missing_counts_default_to_zero(self):
        payload = {"data": [{"id": 1, "name": "Sparse"}]}
        snapshot = parse_games_payload(payload, TIMESTAMP)[0]
        assert (snapshot.playing, snapshot.visits, snapshot.favorites) == (0, 0, 0)

    def test_empty_payload_returns_no_snapshots(self):
        assert parse_games_payload({}, TIMESTAMP) == []

    def test_visits_per_favorite_handles_zero_favorites(self):
        payload = {"data": [{"id": 1, "name": "Zero", "visits": 100, "favoritedCount": 0}]}
        assert parse_games_payload(payload, TIMESTAMP)[0].visits_per_favorite == 0.0


class TestStorage:
    @pytest.fixture
    def store(self, tmp_path):
        store = SnapshotStore(tmp_path / "test.db")
        yield store
        store.close()

    def test_saves_snapshots(self, store):
        assert store.save_all(parse_games_payload(sample_payload(), TIMESTAMP)) == 2
        assert store.total_snapshots() == 2

    def test_rerunning_same_timestamp_is_idempotent(self, store):
        snapshots = parse_games_payload(sample_payload(), TIMESTAMP)
        store.save_all(snapshots)
        assert store.save_all(snapshots) == 0
        assert store.total_snapshots() == 2

    def test_new_timestamp_creates_new_rows(self, store):
        store.save_all(parse_games_payload(sample_payload(), TIMESTAMP))
        store.save_all(parse_games_payload(sample_payload(), "2026-01-01T01:00:00+00:00"))
        assert store.total_snapshots() == 4

    def test_latest_returns_one_row_per_experience(self, store):
        store.save_all(parse_games_payload(sample_payload(), TIMESTAMP))
        store.save_all(parse_games_payload(sample_payload(), "2026-01-01T02:00:00+00:00"))
        latest = store.latest_per_experience()
        assert len(latest) == 2
        assert all(row["captured_at"] == "2026-01-01T02:00:00+00:00" for row in latest)


class TestAnalysis:
    def test_single_reading_is_not_a_trend(self, tmp_path):
        store = SnapshotStore(tmp_path / "t.db")
        store.save_all(parse_games_payload(sample_payload(), TIMESTAMP))
        assert build_trend(store.history(1)) is None
        store.close()

    def test_growth_is_measured_across_readings(self, tmp_path):
        store = SnapshotStore(tmp_path / "t.db")
        store.save_all(parse_games_payload({"data": [
            {"id": 1, "name": "Alpha", "playing": 100}]}, TIMESTAMP))
        store.save_all(parse_games_payload({"data": [
            {"id": 1, "name": "Alpha", "playing": 150}]}, "2026-01-01T03:00:00+00:00"))

        trend = build_trend(store.history(1))
        assert trend.change == 50
        assert trend.percent_change == 50.0
        assert trend.direction == "rising"
        store.close()

    def test_zero_baseline_does_not_divide_by_zero(self):
        trend = Trend("Cold Start", 1, first_playing=0, last_playing=10, readings=2)
        assert trend.percent_change == 0.0

    def test_ranks_strongest_growth_first(self):
        trends = [
            Trend("Slow", 1, 100, 110, 2),
            Trend("Fast", 2, 100, 200, 2),
            Trend("Drop", 3, 100, 50, 2),
        ]
        assert [t.name for t in rank_by_momentum(trends)] == ["Fast", "Slow", "Drop"]
