"""Fetch tick sightings from the Elanco API, clean them and store them in SQLite.

Run from the project root with:  python -m app.ingest
"""

import logging
import time
from contextlib import closing

import httpx

from app.cleaning import InvalidRecordError, clean_record
from app.db import connect, count_sightings, upsert_sightings

API_URL = "https://dev-task.elancoapps.com/data/tick-sightings"
TIMEOUT_SECONDS = 10
MAX_ATTEMPTS = 3

logger = logging.getLogger(__name__)


class FetchError(Exception):
    """Raised when sightings cannot be fetched from the API."""


def fetch_sightings(
    client: httpx.Client, attempts: int = MAX_ATTEMPTS, wait_seconds: float = 1.0
) -> list:
    """Return the raw sightings list, retrying with a growing wait if a request fails."""
    for attempt in range(1, attempts + 1):
        try:
            response = client.get(API_URL, timeout=TIMEOUT_SECONDS)
            response.raise_for_status()  # turns 4xx and 5xx responses into errors
            data = response.json()  # raises ValueError if the body is not valid JSON
        except (httpx.HTTPError, ValueError) as error:
            logger.warning("Attempt %d of %d failed: %s", attempt, attempts, error)
            if attempt < attempts:
                time.sleep(wait_seconds * 2 ** (attempt - 1))  # 1s, then 2s, ...
            continue

        if not isinstance(data, list):
            raise FetchError("expected a JSON list of sightings")
        return data

    raise FetchError(f"could not fetch sightings after {attempts} attempts")


def clean_all(raw_records: list) -> tuple[list[dict], int]:
    """Clean every raw record. Return the valid ones and how many were rejected."""
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
    """Fetch, clean and store sightings. Return a summary of what happened."""
    raw_records = fetch_sightings(client)
    cleaned, rejected = clean_all(raw_records)
    upsert_sightings(conn, cleaned)

    unique_ids = {record["id"] for record in cleaned}
    return {
        "fetched": len(raw_records),
        "valid": len(cleaned),
        "rejected": rejected,
        "duplicate_ids": len(cleaned) - len(unique_ids),
        "total_in_database": count_sightings(conn),
    }


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    try:
        with httpx.Client() as client, closing(connect()) as conn:
            summary = run_ingestion(client, conn)
    except FetchError as error:
        logger.error("Ingestion failed: %s. Existing data was left unchanged.", error)
        raise SystemExit(1)
    logger.info("Ingestion complete: %s", summary)


if __name__ == "__main__":
    main()
