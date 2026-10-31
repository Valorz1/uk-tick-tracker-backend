"""SQLite connection, table creation and saving for tick sightings."""

import sqlite3
from pathlib import Path

# The database file sits in the project root, whichever folder you run from.
DB_PATH = Path(__file__).resolve().parent.parent / "ticks.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS sightings (
    id         TEXT PRIMARY KEY,
    date       TEXT NOT NULL,
    location   TEXT NOT NULL,
    species    TEXT NOT NULL,
    latin_name TEXT
);
CREATE INDEX IF NOT EXISTS idx_sightings_date ON sightings (date);
CREATE INDEX IF NOT EXISTS idx_sightings_location ON sightings (location);
"""


def connect(path: str | Path = DB_PATH) -> sqlite3.Connection:
    """Open the database, creating the table if it does not exist yet."""
    # FastAPI may use a connection on a different thread from the one that.
    
    # opened it. Each request gets its own connection, so this is safe.
    conn = sqlite3.connect(path, check_same_thread=False)
    conn.row_factory = sqlite3.Row  # lets us read columns by name: row["date"]
    conn.executescript(SCHEMA)
    return conn


def upsert_sightings(conn: sqlite3.Connection, records: list[dict]) -> None:
    """Insert cleaned records; if an id already exists, replace it with the new copy."""
    # `with conn` makes this one transaction: every record is saved, or none are.
    with conn:
        conn.executemany(
            """
            INSERT INTO sightings (id, date, location, species, latin_name)
            VALUES (:id, :date, :location, :species, :latin_name)
            ON CONFLICT (id) DO UPDATE SET
                date = excluded.date,
                location = excluded.location,
                species = excluded.species,
                latin_name = excluded.latin_name
            """,
            records,
        )


def count_sightings(conn: sqlite3.Connection) -> int:
    """Return how many sightings are stored."""
    return conn.execute("SELECT COUNT(*) FROM sightings").fetchone()[0]
