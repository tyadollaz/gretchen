from __future__ import annotations
import os
from datetime import datetime, timezone
from fastapi import FastAPI, Response
from pydantic import BaseModel
from dateutil import parser as dtparser
from zoneinfo import ZoneInfo

# Storage selection mirrors main.py
USE_MONGO = os.getenv("USE_MONGO", "0") == "1" or bool(os.getenv("MONGODB_URI"))
if USE_MONGO:
    from storage_mongo import load_reminders, update_reminder_status
else:
    from storage import load_reminders, update_reminder_status

from telegram import Bot

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
DEFAULT_TZ = os.getenv("DEFAULT_TZ", "Asia/Ho_Chi_Minh")

app = FastAPI()


@app.get("/process-due")
async def process_due() -> dict:
    if not TELEGRAM_TOKEN:
        return {"ok": False, "error": "TELEGRAM_TOKEN not set"}
    bot = Bot(TELEGRAM_TOKEN)
    now_utc = datetime.now(timezone.utc)
    count = 0
    for r in load_reminders():
        if r.get("status") != "scheduled":
            continue
        due_at = dtparser.isoparse(r["due_at"]) if isinstance(r.get("due_at"), str) else r.get("due_at")
        if due_at is None:
            continue
        if due_at.tzinfo is None:
            tz = r.get("timezone") or DEFAULT_TZ
            due_at = due_at.replace(tzinfo=ZoneInfo(tz))
        if due_at <= now_utc:
            await bot.send_message(r["chat_id"], f"⏰ Reminder: {r['text']}")
            update_reminder_status(r["id"], "done")
            count += 1
    return {"ok": True, "notified": count}


