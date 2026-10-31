import sqlite3
from datetime import date, timedelta


def search_sightings(
    conn: sqlite3.Connection,
    start: date | None = None,
    end: date | None = None,
    location: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> tuple[int, list[dict]]:
    """Return (total matches, one page of matching sightings, newest first)."""
    conditions = []
    params = []

    if start:
        conditions.append("date >= ?")
        params.append(start.isoformat())

    if end:
        # Dates are stored with a time, so "up to and including end" means
        # "before the start of the next day".
        conditions.append("date < ?")
        params.append((end + timedelta(days=1)).isoformat())

    if location:
        # Tidy the input the same way stored cities were tidied.
        conditions.append("location = ?")
        params.append(location.strip().title())

    # Only our own fixed condition strings go into the SQL text.
    # Every value the user sends goes through a ? placeholder.
    where = " WHERE " + " AND ".join(conditions) if conditions else ""

    total = conn.execute(
        f"SELECT COUNT(*) FROM sightings{where}",
        params,
    ).fetchone()[0]

    rows = conn.execute(
        "SELECT id, date, location, species, latin_name FROM sightings"
        f"{where} ORDER BY date DESC, id LIMIT ? OFFSET ?",
        [*params, limit, offset],
    ).fetchall()

    return total, [dict(row) for row in rows]
