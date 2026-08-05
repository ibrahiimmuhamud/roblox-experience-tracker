# Roblox Experience Tracker

A command-line tool that tracks how Roblox experiences gain and lose players over time.

Roblox's public API tells you how many people are playing an experience *right now* — but not
whether that number is climbing or collapsing. This tool captures readings on a schedule,
stores them as a time series, and reports which experiences have real momentum.

```
CURRENT STANDINGS (by concurrent players)
--------------------------------------------------------------
Brookhaven RP                         289,431 playing   67,204,881,930 visits
Adopt Me!                             142,880 playing   36,918,447,201 visits
Blox Fruits                            98,215 playing   32,004,119,884 visits

MOMENTUM (change in concurrent players)
--------------------------------------------------------------
Blox Fruits                    +   12.4%    +10,847 players  (18 readings)
Brookhaven RP                  +    3.1%     +8,702 players  (18 readings)
Adopt Me!                      -    5.7%     -8,633 players  (18 readings)
```

## Why I built it

A single snapshot is a vanity metric. What actually matters is whether players keep coming
back — so the interesting question isn't "how many are playing," it's "is this rising or
falling, and how fast." That requires storing history and comparing readings over time,
which is what this tool does.

## How it works

```
config.json  ->  Roblox Games API  ->  parse & validate  ->  SQLite  ->  trend report
                  (retry/backoff)      (skip malformed)     (dedup)
```

1. **Collect** — reads the tracked experiences from `config.json`, batches them into
   requests (the API caps IDs per call), and fetches current stats.
2. **Store** — writes each reading to SQLite under a composite primary key of
   `(universe_id, captured_at)`.
3. **Report** — pulls the newest reading per experience for standings, then compares the
   first and last readings to compute momentum.

### Design decisions

**Idempotent writes.** The composite primary key means re-running the collector for the same
timestamp writes nothing. A retried or duplicated scheduled run cannot double-count a reading.

**Retry with backoff.** Roblox rate-limits aggressively. Requests retry on `429` and `5xx`
with exponential backoff, but fail fast on `4xx` errors that will never succeed on retry.

**Malformed records are skipped, not fatal.** One bad record in a batch shouldn't lose the
other 99, so records missing an ID or name are dropped and the rest are kept.

**Two readings minimum for a trend.** A single data point is not a trend, so `build_trend`
returns `None` rather than reporting fake momentum from one reading.

**Parsing is separate from fetching.** `parse_games_payload` takes a dict, not a URL, so all
parsing logic is unit tested offline with no network calls.

## Setup

```bash
git clone https://github.com/<your-username>/roblox-experience-tracker.git
cd roblox-experience-tracker
python -m venv .venv && source .venv/bin/activate    # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

## Usage

```bash
python src/main.py collect    # take a snapshot
python src/main.py report     # view standings and momentum
```

Run `collect` at least twice, a few hours apart, before momentum has anything to compare.

### Tracking different experiences

Edit `config.json`. Find a `universe_id` from any experience's URL on the Roblox site.

```json
{
  "experiences": [
    { "name": "Adopt Me!", "universe_id": 920587237 }
  ]
}
```

## Tests

```bash
pytest tests/ -v
```

Covers payload parsing, malformed-record handling, storage idempotency, trend math, and
division-by-zero guards. All tests run offline against fixtures.

## Automated collection

`.github/workflows/collect.yml` runs the collector every 6 hours via GitHub Actions and
commits the updated database, building the time series without a server.

## Tech

Python 3.11 · SQLite · Roblox Games API · pytest · GitHub Actions

Uses only public, unauthenticated read endpoints. No credentials required.
