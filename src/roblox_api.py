"""Client for Roblox's public Games API.

Only public, unauthenticated read endpoints are used. No credentials required.
Docs: https://create.roblox.com/docs/cloud/reference/domains/games
"""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from dataclasses import dataclass

GAMES_ENDPOINT = "https://games.roblox.com/v1/games"
USER_AGENT = "roblox-experience-tracker/1.0"
MAX_IDS_PER_REQUEST = 100


class RobloxAPIError(Exception):
    """Raised when the Roblox API cannot be reached or returns bad data."""


@dataclass(frozen=True)
class ExperienceSnapshot:
    """A single point-in-time reading for one Roblox experience."""

    universe_id: int
    name: str
    playing: int
    visits: int
    favorites: int
    captured_at: str

    @property
    def visits_per_favorite(self) -> float:
        """Rough engagement signal: how many visits each favorite represents."""
        if self.favorites == 0:
            return 0.0
        return round(self.visits / self.favorites, 2)


def _request(url: str, retries: int = 3, backoff: float = 1.5) -> dict:
    """GET a URL with retries and exponential backoff.

    Roblox rate-limits aggressively, so transient 429/5xx responses are retried
    rather than treated as fatal.
    """
    last_error: Exception | None = None

    for attempt in range(retries):
        request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
        try:
            with urllib.request.urlopen(request, timeout=20) as response:
                return json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as error:
            last_error = error
            # Client errors other than rate limiting will not succeed on retry.
            if error.code not in (429, 500, 502, 503, 504):
                raise RobloxAPIError(f"HTTP {error.code} from {url}") from error
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as error:
            last_error = error

        if attempt < retries - 1:
            time.sleep(backoff ** attempt)

    raise RobloxAPIError(f"Failed after {retries} attempts: {last_error}")


def _chunk(items: list[int], size: int) -> list[list[int]]:
    return [items[i : i + size] for i in range(0, len(items), size)]


def parse_games_payload(payload: dict, captured_at: str) -> list[ExperienceSnapshot]:
    """Convert a raw API payload into snapshots, skipping malformed records.

    Kept separate from the network call so it can be unit tested offline.
    """
    snapshots: list[ExperienceSnapshot] = []

    for record in payload.get("data", []):
        universe_id = record.get("id")
        name = record.get("name")
        if universe_id is None or not name:
            continue

        snapshots.append(
            ExperienceSnapshot(
                universe_id=int(universe_id),
                name=str(name),
                playing=int(record.get("playing") or 0),
                visits=int(record.get("visits") or 0),
                favorites=int(record.get("favoritedCount") or 0),
                captured_at=captured_at,
            )
        )

    return snapshots


def fetch_experiences(universe_ids: list[int], captured_at: str) -> list[ExperienceSnapshot]:
    """Fetch current stats for the given universe IDs.

    The API caps how many IDs one request accepts, so IDs are batched.
    """
    if not universe_ids:
        return []

    snapshots: list[ExperienceSnapshot] = []
    for batch in _chunk(universe_ids, MAX_IDS_PER_REQUEST):
        url = f"{GAMES_ENDPOINT}?universeIds={','.join(str(i) for i in batch)}"
        snapshots.extend(parse_games_payload(_request(url), captured_at))

    return snapshots
