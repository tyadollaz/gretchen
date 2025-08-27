from __future__ import annotations
import json
from pathlib import Path
from typing import Any, Dict, List, Optional
from datetime import datetime, timezone

DATA_DIR = Path(__file__).parent / "data"
REM_FILE = DATA_DIR / "reminders.json"
USR_FILE = DATA_DIR / "users.json"

def _ensure_files():
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    if not REM_FILE.exists():
        REM_FILE.write_text("[]", encoding="utf-8")
    if not USR_FILE.exists():
        USR_FILE.write_text("{}", encoding="utf-8")

def load_reminders() -> List[Dict[str, Any]]:
    _ensure_files()
    with open(REM_FILE, "r", encoding="utf-8") as f:
        return json.load(f)

def save_reminders(reminders: List[Dict[str, Any]]) -> None:
    _ensure_files()
    with open(REM_FILE, "w", encoding="utf-8") as f:
        json.dump(reminders, f, indent=2, ensure_ascii=False)

def load_users() -> Dict[str, Any]:
    _ensure_files()
    with open(USR_FILE, "r", encoding="utf-8") as f:
        return json.load(f)

def save_users(users: Dict[str, Any]) -> None:
    _ensure_files()
    with open(USR_FILE, "w", encoding="utf-8") as f:
        json.dump(users, f, indent=2, ensure_ascii=False)

def upsert_user_timezone(chat_id: int, tz: str) -> None:
    users = load_users()
    users[str(chat_id)] = users.get(str(chat_id), {})
    users[str(chat_id)]["timezone"] = tz
    save_users(users)

def get_user_timezone(chat_id: int) -> Optional[str]:
    users = load_users()
    return users.get(str(chat_id), {}).get("timezone")

def add_reminder(rem: Dict[str, Any]) -> None:
    reminders = load_reminders()
    reminders.append(rem)
    save_reminders(reminders)

def update_reminder_status(reminder_id: str, status: str) -> None:
    reminders = load_reminders()
    for r in reminders:
        if r["id"] == reminder_id:
            r["status"] = status
            r["updated_at"] = datetime.now(timezone.utc).isoformat()
            break
    save_reminders(reminders)

def delete_reminder(reminder_id: str) -> bool:
    reminders = load_reminders()
    new_list = [r for r in reminders if r["id"] != reminder_id]
    changed = len(new_list) != len(reminders)
    if changed:
        save_reminders(new_list)
    return changed
