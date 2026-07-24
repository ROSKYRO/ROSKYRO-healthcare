import uuid
from datetime import datetime, timezone


def new_id() -> str:
    """String UUIDs (not ObjectId) as _id everywhere, matching the original
    Postgres build's `id` shape 1:1 so the React frontend and every URL
    pattern (`/app/patients/:id`, etc.) needs zero changes."""
    return str(uuid.uuid4())


def now() -> datetime:
    return datetime.now(timezone.utc)


def now_iso() -> str:
    return now().isoformat()


def as_aware(dt: datetime | None) -> datetime | None:
    """MongoDB (mongomock included -- verified directly, and this matches
    real PyMongo's default codec behaviour too) round-trips datetimes as
    UTC but strips their tzinfo on read-back, so anything fetched from the
    DB comes back naive even though it was inserted via now() (aware).
    Comparing that directly against now() raises `TypeError: can't compare
    offset-naive and offset-aware datetimes`. Any code comparing a
    DB-fetched datetime against now() (or doing arithmetic across the two)
    must pass the DB value through this first."""
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


def to_out(doc: dict | None) -> dict | None:
    """Mongo doc -> API dict: rename _id -> id, drop the raw _id key."""
    if doc is None:
        return None
    doc = dict(doc)
    doc["id"] = doc.pop("_id")
    return doc


def to_out_many(docs) -> list:
    return [to_out(d) for d in docs]
