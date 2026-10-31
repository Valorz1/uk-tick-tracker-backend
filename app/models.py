"""Shapes of the JSON our API returns. FastAPI uses these to check responses
and to document them on the /docs page."""

from datetime import datetime

from pydantic import BaseModel


class Sighting(BaseModel):
    """One tick sighting."""

    id: str
    date: datetime  # validated as a real date and time, not just any text
    location: str
    species: str
    latin_name: str | None  # optional in the source data


class SearchResults(BaseModel):
    """One page of search results."""

    total: int  # how many sightings match, across all pages
    limit: int
    offset: int
    results: list[Sighting]


class RegionCount(BaseModel):
    """The number of sightings in one region."""

    region: str
    count: int


class PeriodCount(BaseModel):
    """The number of sightings in one week or month."""

    period: str  # "2024-01" for monthly, or the Monday a week starts, "2024-01-01"
    count: int
