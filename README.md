# UK Tick Tracker: Backend MVP

**Author:** Parmbir Singh Nandha
**Submitted for:** Elanco Placement Programme technical task (backend), 2026

**Video walkthrough:** _link to be added_

A backend that consumes raw tick-sighting data from the Elanco API, cleans and stores it,
and serves search, filtering and reporting endpoints. It is built with **FastAPI** and **SQLite**.

---

## Contents

1. [Quick start](#quick-start)
2. [Endpoints](#endpoints)
3. [Architecture](#architecture)
4. [How the data is consumed and processed](#how-the-data-is-consumed-and-processed)
5. [What I found in the data](#what-i-found-in-the-data)
6. [Design choices and assumptions](#design-choices-and-assumptions)
7. [Error handling](#error-handling)
8. [Testing](#testing)
9. [What I would do next](#what-i-would-do-next)

---

## Quick start

Requires **Python 3.10 or later** (developed and tested on Python 3.14).

```bash
git clone https://github.com/Valorz1/uk-tick-tracker-backend.git
cd uk-tick-tracker-backend

python -m venv .venv
.venv\Scripts\activate          # Windows
# source .venv/bin/activate     # macOS / Linux

pip install -r requirements.txt
```

**1. Load the data** (fetches from the Elanco API, cleans it and saves it to `ticks.db`):

```bash
python -m app.ingest
```

```
INFO: Ingestion complete: {'fetched': 1000, 'valid': 1000, 'rejected': 0, 'duplicate_ids': 0, 'total_in_database': 1000}
```

Running it again is safe: records are updated, never duplicated.

**2. Start the API:**

```bash
uvicorn app.main:app --reload
```

Then open **http://127.0.0.1:8000/docs** to try every endpoint in the browser.

**3. Run the tests:**

```bash
python -m pytest -v
```

---

## Endpoints

| Endpoint | Purpose |
|---|---|
| `GET /sightings` | Search and filter sightings by date range and location, with paging |
| `GET /reports/regions` | Number of sightings per region, highest first |
| `GET /reports/trends` | Number of sightings per week or month, oldest first |

### `GET /sightings`

| Parameter | Type | Default | Notes |
|---|---|---|---|
| `start` | date (`YYYY-MM-DD`) | none | Earliest date, inclusive |
| `end` | date (`YYYY-MM-DD`) | none | Latest date, inclusive (the whole day) |
| `location` | text | none | City; case and extra spaces are ignored (`" london "` finds London) |
| `limit` | 1 to 500 | 50 | Page size |
| `offset` | 0 or more | 0 | How many results to skip |

`GET /sightings?location=london&start=2024-01-01&end=2024-12-31&limit=2`

```json
{
  "total": 2,
  "limit": 2,
  "offset": 0,
  "results": [
    {
      "id": "JIpX177KvaSfIj0TY7iR",
      "date": "2024-09-28T07:08:08",
      "location": "London",
      "species": "Fox/badger tick",
      "latin_name": "Ixodes canisuga"
    },
    {
      "id": "dFaensEuXRAelfCSBxO2",
      "date": "2024-07-18T18:15:32",
      "location": "London",
      "species": "Tree-hole tick",
      "latin_name": "Ixodes arboricola"
    }
  ]
}
```

`total` counts every match across all pages, so a client knows how many pages there are.

### `GET /reports/regions`

```json
[
  {"region": "Nottingham", "count": 95},
  {"region": "Birmingham", "count": 82},
  {"region": "Glasgow", "count": 78},
  ...
]
```

### `GET /reports/trends?period=monthly` (the default) or `?period=weekly`

Monthly periods are labelled `YYYY-MM`. Weekly periods are labelled by the **Monday each week starts**,
so a week is never split at the end of a month or year.

```json
[
  {"period": "2024-10", "count": 8},
  {"period": "2024-11", "count": 1},
  {"period": "2024-12", "count": 5}
]
```

```json
[
  {"period": "2024-12-16", "count": 1},
  {"period": "2024-12-23", "count": 2},
  {"period": "2024-12-30", "count": 1}
]
```

### Errors

| Status | When |
|---|---|
| `422` | Invalid input, e.g. `start=not-a-date`, `limit=0`, `period=daily`, or `start` after `end` |
| `503` | No data loaded yet: `{"detail": "No data yet: run 'python -m app.ingest' first"}` |

An unknown location is not an error: it returns an empty list, because nothing matched.

---

## Architecture

```
                 python -m app.ingest                       uvicorn app.main:app
                 ────────────────────                       ────────────────────
Elanco API ──► fetch (timeout + retries) ──► clean ──► SQLite ◄── search & report endpoints ◄── client
                      ingest.py            cleaning.py  db.py        main.py + queries.py
```

**Ingestion and serving are separate.** A command fetches, cleans and stores the data once, and the API only
ever reads from SQLite. If the Elanco API is slow or down, every endpoint keeps working from the stored data.

| File | Job |
|---|---|
| `app/ingest.py` | Fetches from the Elanco API with a timeout and retries; runs cleaning; saves; prints a summary |
| `app/cleaning.py` | Checks and tidies one raw record, or rejects it with a reason |
| `app/db.py` | SQLite connection, table creation and saving (upsert) |
| `app/queries.py` | The SQL behind each endpoint |
| `app/models.py` | Pydantic models: the shape of each JSON response (also used by `/docs`) |
| `app/main.py` | FastAPI app and endpoints |

**Why these technologies**

- **FastAPI:** validates inputs from type hints (bad dates and out-of-range numbers are rejected automatically)
  and generates interactive documentation at `/docs`.
- **SQLite:** built into Python, needs no server, and handles this data size easily. `GROUP BY` and its date
  functions produce the reports in a few lines of SQL.
- **httpx:** clear timeouts and error types, plus a built-in `MockTransport` for faking the API in tests.
- **pytest:** fixtures and parametrised tests keep the test suite short.

---

## How the data is consumed and processed

1. **Fetch.** `GET https://dev-task.elancoapps.com/data/tick-sightings` returns one JSON list.
   Each request has a 10-second timeout and is retried if it fails (see [Error handling](#error-handling)).
2. **Clean.** Every record goes through `clean_record()`, which:
   - rejects it if `id`, `date`, `location` or `species` is missing, `None` or blank;
   - rejects dates that cannot be parsed, that include a timezone (the source never does) or that are in the future;
   - trims spaces and tidies city names (`" king's  lynn "` → `"King's Lynn"`);
   - stores dates in one format (`2022-08-01T06:40:31`).

   Rejected records are counted and logged with the reason. One bad record never stops the import.
3. **Store.** Valid records are saved with an **upsert**: insert the record, or replace it if that `id`
   already exists. The whole batch is one transaction, so either every record is saved or none are.
4. **Summarise.** The import reports how many records were fetched, valid, rejected and duplicated,
   plus the total in the database.

### Table

```sql
CREATE TABLE sightings (
    id         TEXT PRIMARY KEY,
    date       TEXT NOT NULL,
    location   TEXT NOT NULL,
    species    TEXT NOT NULL,
    latin_name TEXT
);
-- plus indexes on date and location, which the search filters use
```

SQLite has no date type, but ISO-format text sorts in date order and works with SQLite's date functions.

---

## What I found in the data

I explored the raw data with a script before designing anything:

- **1,000 records**, matching the API's own `/data/stats` endpoint.
- **No duplicate IDs, no missing or blank fields, no invalid dates.** The data was clean when I tested it.
  The pipeline still handles all of these cases, and the tests prove it with deliberately bad records.
- **14 UK cities**, from Nottingham (95 sightings) to Newcastle and Southampton (57 each).
- **5 species**, each always paired with the same Latin name.
- **Dates from 3 January 2012 to 30 December 2024**, all in one format, with no timezone.
- **The API was reliable:** 10 out of 10 test calls returned `200` in 0.37 to 0.64 seconds.
  Retry handling is therefore tested against a faked failing API rather than the real one.

---

## Design choices and assumptions

| Decision | Reason |
|---|---|
| **Each city is a region.** | `location` (a city) is the only location field. Mapping cities to wider regions would add assumptions of my own. |
| **A duplicate is the same `id`; the newest copy wins.** | The `id` is the source's unique key. Re-running ingestion never duplicates rows, and corrected records replace old ones. Records with the same date, city and species but different IDs are kept, because they could be genuine separate sightings. |
| **`id`, `date`, `location` and `species` are required; `latinName` is optional.** | Search and reports cannot use a record without these. |
| **Future dates are rejected.** | A sighting cannot happen in the future. |
| **Dates are treated as UK local time.** | The source dates have no timezone. |
| **Fetch everything in one request.** | The source has 1,000 records and no paging. The API's own search uses `limit` and `offset`, so responses stay small as the data grows. |
| **City names are tidied by one shared function**, used both when storing and when searching. | Stored data and search input always follow the same rule, so a search can never miss because of capitals or spaces. |

---

## Error handling

**When fetching from the Elanco API**

- **10-second timeout,** so a hung server cannot freeze the import.
- **Up to 3 attempts with exponential backoff** (waits of 1 second, then 2 seconds) for network errors,
  invalid JSON, server errors (5xx) and `429 Too Many Requests`.
- **No retry for other client errors** (e.g. `404 Not Found`), because waiting will not fix them.
- **A response that is not a list** stops the import straight away.
- **If every attempt fails,** the import logs a clear error, exits with code 1 and **leaves existing data untouched**.

**When cleaning**

- Each bad record is rejected with a reason and logged; the rest of the import continues.

**In the API**

- Invalid parameters → `422` with a message (FastAPI does most of this from the type hints).
- Empty database → `503` "run ingestion first", rather than empty results that look like "no ticks".
- All SQL uses `?` placeholders for user input, which prevents SQL injection.

---

## Testing

```bash
python -m pytest -v
```

**56 tests**, which run in about a second and never touch the real API or the real database:

| File | Covers |
|---|---|
| `tests/test_cleaning.py` | Valid records, every missing or blank required field, bad and future dates, timezones, city tidying |
| `tests/test_db.py` | Saving, no duplicates when saving twice, newest copy wins |
| `tests/test_ingest.py` | Retries after `500`, `429` and invalid JSON; giving up after 3 failures; no retry on `404`; the full pipeline summary; running twice |
| `tests/test_api.py` | Every filter alone and combined, the end date including the whole day, paging, invalid input, both reports, the `503` error |

- **The Elanco API is faked** with `httpx.MockTransport`, so failures can be tested on demand.
- **Each API test uses a small in-memory database** with sightings chosen so every expected answer is known.
  For example, 31 January at 23:59:59 is included in an `end=…-01-31` search, and 1 February at midnight is not.

---

## What I would do next

- **AI/ML insights (the brief's extension task):** for example, forecasting next month's sightings per region
  from the monthly trends, or flagging unusual spikes.
- **Map cities to wider regions or nations** (e.g. Glasgow → Scotland), with an `Unknown` group for new cities.
- **Handle deleted records:** ingestion adds and updates but never removes a sighting that disappears from the source.
- **Fill gaps in trends:** periods with no sightings are left out (every month has data, but only 522 of about
  680 weeks do). Returning zeros would make charting easier.
- **Add filters to the reports**, such as trends for one city or one species.
- **Fetch in pages and insert in batches** if the source grew large.
- **Run ingestion on a schedule** and record when the data was last refreshed.
- **Move the test client to `httpx2`.** The installed Starlette version shows a deprecation warning recommending it.
- **Give clearer rejection reasons,** e.g. "id is not text" rather than "missing id" for a numeric ID.
