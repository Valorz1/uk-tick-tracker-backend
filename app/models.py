"""Shapes of the JSON our API returns. FastAPI uses these to check responses
and to document them on the /docs page."""

from datetime import datetime

from pydantic import BaseModel


class Sighting(BaseModel):
    id: str
    date: datetime
    location: str
    species: str
    latin_name: str | None


class SearchResults(BaseModel):
    total: int  # how many sightings match, across all pages
    limit: int
    offset: int
    results: list[Sighting]