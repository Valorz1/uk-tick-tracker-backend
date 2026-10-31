"""Fetch tick sightings from the Elanco API, clean them and store them in SQLite.

Run from the project root with:  python -m app.ingest

Ingestion is kept separate from the web API on purpose: the API only reads
from the local database, so it keeps working if the Elanco API is down.
"""

import logging
import time
from contextlib import closing

import httpx

from app.cleaning import InvalidRecordError, clean_record
from app.db import connect, count_sightings, upsert_sightings

API_URL = "https://dev-task.elancoapps.com/data/tick-sightings"
TIMEOUT_SECONDS = 10  # stops a hung server from freezing the import
MAX_ATTEMPTS = 3

logger = logging.getLogger(__name__)


class FetchError(Exception):
    """Raised when sightings cannot be fetched from the API.

    It deliberately does not inherit from httpx.HTTPError or ValueError,
    so the retry loop below never catches it: raising it stops at once.
    """


def fetch_sightings(
    client: httpx.Client, attempts: int = MAX_ATTEMPTS, wait_seconds: float = 1.0
) -> list:
    """Download the raw sightings list, retrying temporary failures.

    Retries network errors, timeouts, invalid JSON, 429 and 5xx responses,
    waiting twice as long after each failure (exponential backoff), which
    gives a struggling server time to recover instead of overloading it.

    Args:
        client: The HTTP client to use. Passed in (dependency injection)
            so tests can supply a fake client instead of the real API.
        attempts: The maximum number of requests to make.
        wait_seconds: The first wait between attempts. Tests pass 0.

    Returns:
        The decoded JSON list of raw sighting records.

    Raises:
        FetchError: If the response is a client error other than 429, is not
            a JSON list, or every attempt fails.
    """
    for attempt in range(1, attempts + 1):
        try:
            response = client.get(API_URL, timeout=TIMEOUT_SECONDS)
            # A 4xx error (e.g. 404 Not Found) means our request is wrong, so
            # retrying will not help: stop now. 429 (Too Many Requests) is the
            # exception, because waiting and trying again is the right response.
            if 400 <= response.status_code < 500 and response.status_code != 429:
                raise FetchError(f"API returned {response.status_code}; retrying will not help")
            response.raise_for_status()  # turns 429 and 5xx responses into errors
            data = response.json()  # raises ValueError if the body is not valid JSON
        except (httpx.HTTPError, ValueError) as error:
            logger.warning("Attempt %d of %d failed: %s", attempt, attempts, error)
            if attempt < attempts:  # no point waiting after the final attempt
                time.sleep(wait_seconds * 2 ** (attempt - 1))  # 1s, then 2s, ...
            continue

        # A reply in the wrong shape will not change on retry, so stop at once.
        if not isinstance(data, list):
            raise FetchError("expected a JSON list of sightings")
        return data

    raise FetchError(f"could not fetch sightings after {attempts} attempts")


def clean_all(raw_records: list) -> tuple[list[dict], int]:
    """Clean every raw record, skipping (not stopping on) invalid ones.

    Args:
        raw_records: Records exactly as received from the API.

    Returns:
        A tuple of (the cleaned valid records, the number rejected).
        Each rejection is logged with its reason.
    """
    cleaned = []
    rejected = 0
    for raw in raw_records:
        try:
            cleaned.append(clean_record(raw))
        except InvalidRecordError as error:
            rejected += 1
            logger.warning("Rejected record: %s", error)
    return cleaned, rejected


def run_ingestion(client: httpx.Client, conn) -> dict:
    """Run the full pipeline: fetch, clean, then store.

    Args:
        client: The HTTP client used to fetch from the API.
        conn: An open SQLite connection to store the records in.

    Returns:
        A summary dict: records fetched, valid, rejected, duplicate IDs
        within this batch, and the total now in the database.

    Raises:
        FetchError: If the data cannot be fetched. Nothing is saved in that
            case, so existing data is left unchanged.
    """
    raw_records = fetch_sightings(client)
    cleaned, rejected = clean_all(raw_records)
    upsert_sightings(conn, cleaned)

    # A set keeps only unique values, so the size difference is the number
    # of repeated IDs. The upsert already stored just one copy of each.
    unique_ids = {record["id"] for record in cleaned}
    return {
        "fetched": len(raw_records),
        "valid": len(cleaned),
        "rejected": rejected,
        "duplicate_ids": len(cleaned) - len(unique_ids),
        "total_in_database": count_sightings(conn),
    }


def main() -> None:
    """Command-line entry point: run ingestion and log the outcome.

    Exits with code 1 if fetching fails, so a script or scheduler running
    this command can tell that it did not succeed.
    """
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    try:
        # `with` closes both the HTTP client and the database connection,
        # even if an error happens part-way through.
        with httpx.Client() as client, closing(connect()) as conn:
            summary = run_ingestion(client, conn)
    except FetchError as error:
        logger.error("Ingestion failed: %s. Existing data was left unchanged.", error)
        raise SystemExit(1)
    logger.info("Ingestion complete: %s", summary)


# Only runs when executed as a command, not when imported (e.g. by tests).
if __name__ == "__main__":
    main()
