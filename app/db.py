"""SQLite connection, table creation and saving for tick sightings."""

import sqlite3
from pathlib import Path

# The database file sits in the project root, whichever folder you run from.
DB_PATH = Path(__file__).resolve().parent.parent / "ticks.db"

# `IF NOT EXISTS` makes this safe to run on every connection.
# PRIMARY KEY on id is what prevents duplicate sightings, and NOT NULL is a
# second safety net behind the cleaning code. The indexes speed up the
# date and location filters used by search.
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
    """Open the database, creating the table and indexes if needed.

    Args:
        path: The database file. Tests pass ":memory:" for a temporary
            database that never touches the real `ticks.db`.

    Returns:
        An open connection whose rows can be read by column name.
        The caller is responsible for closing it.
    """
    # FastAPI may use a connection on a different thread from the one that
    # opened it. Each request gets its own connection, so this is safe.
    conn = sqlite3.connect(path, check_same_thread=False)
    conn.row_factory = sqlite3.Row  # lets us read columns by name: row["date"]
    conn.executescript(SCHEMA)
    return conn


def upsert_sightings(conn: sqlite3.Connection, records: list[dict]) -> None:
    """Save cleaned records, replacing any existing record with the same id.

    Running ingestion twice therefore never duplicates rows, and a
    corrected record from the source replaces the old version.

    Args:
        conn: An open database connection.
        records: Cleaned records, as returned by `clean_record`.
    """
    with conn:  # commits on success, rolls back on any error
        conn.executemany(
            # `:id`, `:date` etc. are placeholders filled safely from each
            # dict, so values are never pasted into the SQL text.
            # `excluded` means "the values we just tried to insert".
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
