from __future__ import annotations
import os
from typing import Any, Dict, List, Optional
from datetime import datetime, timezone
from bson import ObjectId
from db import get_db, ensure_indexes


def _coll():
    ensure_indexes()
    return get_db().reminders


def _users():
    ensure_indexes()
    return get_db().users


# ---- users ----
def upsert_user_timezone(chat_id: int, tz: str) -> None:
    _users().update_one(
        {"chatId": chat_id},
        {"$set": {"timezone": tz, "updatedAt": datetime.now(timezone.utc)}, "$setOnInsert": {"createdAt": datetime.now(timezone.utc)}},
        upsert=True,
    )


def get_user_timezone(chat_id: int) -> Optional[str]:
    doc = _users().find_one({"chatId": chat_id}, {"timezone": 1})
    return (doc or {}).get("timezone")


# ---- reminders ----
def load_reminders() -> List[Dict[str, Any]]:
    docs = list(_coll().find({}, {"_id": 0}))
    return docs


def save_reminders(reminders: List[Dict[str, Any]]) -> None:
    # Not used in Mongo backend; provided for API parity
    pass


def add_reminder(rem: Dict[str, Any]) -> None:
    rem = dict(rem)
    rem.setdefault("created_at", datetime.now(timezone.utc).isoformat())
    rem.setdefault("updated_at", datetime.now(timezone.utc).isoformat())
    _coll().insert_one(rem)


def update_reminder_status(reminder_id: str, status: str) -> None:
    _coll().update_one(
        {"id": reminder_id},
        {"$set": {"status": status, "updated_at": datetime.now(timezone.utc).isoformat()}},
    )


def delete_reminder(reminder_id: str) -> bool:
    res = _coll().delete_one({"id": reminder_id})
    return res.deleted_count > 0


