"""CLI for collecting and reporting Roblox experience data.

Usage:
    python src/main.py collect     Fetch current stats and store a snapshot
    python src/main.py report      Show latest standings and momentum trends
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from analyze import build_trend, rank_by_momentum
from roblox_api import RobloxAPIError, fetch_experiences
from storage import SnapshotStore

CONFIG_PATH = Path(__file__).parent.parent / "config.json"
DB_PATH = Path(__file__).parent.parent / "data" / "snapshots.db"


def load_universe_ids() -> list[int]:
    with open(CONFIG_PATH, encoding="utf-8") as handle:
        return [int(item["universe_id"]) for item in json.load(handle)["experiences"]]


def collect() -> int:
    captured_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    universe_ids = load_universe_ids()

    try:
        snapshots = fetch_experiences(universe_ids, captured_at)
    except RobloxAPIError as error:
        print(f"Collection failed: {error}", file=sys.stderr)
        return 1

    if not snapshots:
        print("No experiences returned. Check the universe IDs in config.json.", file=sys.stderr)
        return 1

    store = SnapshotStore(DB_PATH)
    written = store.save_all(snapshots)
    total = store.total_snapshots()
    store.close()

    print(f"Captured {len(snapshots)} experiences at {captured_at}")
    print(f"  {written} new rows written ({len(snapshots) - written} duplicates ignored)")
    print(f"  {total} snapshots stored in total")
    return 0


def report() -> int:
    store = SnapshotStore(DB_PATH)
    latest = store.latest_per_experience()

    if not latest:
        print("No data yet. Run: python src/main.py collect")
        store.close()
        return 1

    print("\nCURRENT STANDINGS (by concurrent players)")
    print("-" * 62)
    for row in latest:
        print(f"{row['name'][:34]:<35}{row['playing']:>10,} playing{row['visits']:>14,} visits")

    trends = []
    for row in latest:
        trend = build_trend(store.history(row["universe_id"]))
        if trend:
            trends.append(trend)
    store.close()

    if not trends:
        print("\nRun collect at least twice to see momentum trends.")
        return 0

    print("\nMOMENTUM (change in concurrent players)")
    print("-" * 62)
    for trend in rank_by_momentum(trends):
        arrow = {"rising": "+", "falling": "-", "flat": "="}[trend.direction]
        print(
            f"{trend.name[:30]:<31}{arrow}{abs(trend.percent_change):>7.1f}%"
            f"{trend.change:>+10,} players  ({trend.readings} readings)"
        )
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Track Roblox experience popularity over time.")
    parser.add_argument("command", choices=["collect", "report"])
    args = parser.parse_args()
    return collect() if args.command == "collect" else report()


if __name__ == "__main__":
    raise SystemExit(main())
