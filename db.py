from __future__ import annotations
import os
from typing import Optional
from pymongo import MongoClient, ASCENDING

_client: Optional[MongoClient] = None


def get_mongo_client() -> MongoClient:
    global _client
    if _client is not None:
        return _client
    uri = os.getenv("MONGODB_URI")
    if not uri:
        raise RuntimeError("MONGODB_URI not set")
    _client = MongoClient(uri, serverSelectionTimeoutMS=5000)
    # Trigger early server selection to fail fast if invalid
    _client.admin.command("ping")
    return _client


def get_db():
    name = os.getenv("MONGODB_DB", "gretchen")
    return get_mongo_client()[name]


def ensure_indexes() -> None:
    db = get_db()
    # Users: unique chatId
    db.users.create_index([("chatId", ASCENDING)], unique=True)
    # Reminders / Tasks / Habits / Events: id unique per chat, and nextRunAt/status for scanning
    for col in ("reminders", "tasks", "habits", "events"):
        db[col].create_index([("chatId", ASCENDING), ("id", ASCENDING)], unique=True)
        db[col].create_index([("status", ASCENDING), ("nextRunAt", ASCENDING)])


