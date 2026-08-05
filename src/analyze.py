"""Trend analysis over stored snapshots."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Trend:
    """Change in concurrent players between the first and last reading."""

    name: str
    universe_id: int
    first_playing: int
    last_playing: int
    readings: int

    @property
    def change(self) -> int:
        return self.last_playing - self.first_playing

    @property
    def percent_change(self) -> float:
        if self.first_playing == 0:
            return 0.0
        return round((self.change / self.first_playing) * 100, 1)

    @property
    def direction(self) -> str:
        if self.change > 0:
            return "rising"
        if self.change < 0:
            return "falling"
        return "flat"


def build_trend(rows: list) -> Trend | None:
    """Build a Trend from ordered history rows, or None if there is too little data.

    At least two readings are required; a single point is not a trend.
    """
    if len(rows) < 2:
        return None

    return Trend(
        name=rows[-1]["name"],
        universe_id=rows[-1]["universe_id"],
        first_playing=rows[0]["playing"],
        last_playing=rows[-1]["playing"],
        readings=len(rows),
    )


def rank_by_momentum(trends: list[Trend]) -> list[Trend]:
    """Sort trends by percentage growth, strongest first."""
    return sorted(trends, key=lambda t: t.percent_change, reverse=True)
