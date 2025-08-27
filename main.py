from __future__ import annotations
import os
import re
import uuid
import html 
from telegram.constants import ParseMode
from dataclasses import dataclass
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from typing import Optional, Tuple

from dotenv import load_dotenv
from dateutil import parser as dtparser

from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import (
    Application, CommandHandler, MessageHandler, filters,
    ContextTypes, ConversationHandler
)

import json
from storage import (
    add_reminder, load_reminders, save_reminders, update_reminder_status,
    delete_reminder, upsert_user_timezone, get_user_timezone
)

# ---- Conversation states ----
ASK_WHEN, ASK_TEXT = range(2)

load_dotenv()
TOKEN = os.getenv("TELEGRAM_TOKEN")
DEFAULT_TZ = os.getenv("DEFAULT_TZ", "Asia/Ho_Chi_Minh")

if not TOKEN:
    raise RuntimeError("TELEGRAM_TOKEN environment variable not set. Put it in .env")

@dataclass
class WhenParseResult:
    due_at: datetime  # timezone-aware
    source: str       # human-readable source (for echoing back)

def _now_in_tz(tz_name: str) -> datetime:
    return datetime.now(ZoneInfo(tz_name))

def parse_when(text: str, tz_name: str) -> Optional[WhenParseResult]:
    """
    Supported:
      - in 10m / in 2h / in 1d
      - at 18:30
      - tomorrow 09:00
      - absolute dates, e.g. 2025-08-26 18:30 or 'Aug 26 18:30'
    """
    text = text.strip().lower()
    now = _now_in_tz(tz_name)

    # in X[d/h/m]
    m = re.fullmatch(r"in\s+(\d+)\s*([dhm])", text)
    if m:
        value = int(m.group(1))
        unit = m.group(2)
        delta = timedelta(minutes=value) if unit == "m" else timedelta(hours=value) if unit == "h" else timedelta(days=value)
        due = now + delta
        return WhenParseResult(due_at=due, source=f"in {value}{unit}")

    # at HH:MM (today or tomorrow)
    m = re.fullmatch(r"at\s+(\d{1,2}):(\d{2})", text)
    if m:
        hh, mm = int(m.group(1)), int(m.group(2))
        candidate = now.replace(hour=hh, minute=mm, second=0, microsecond=0)
        if candidate <= now:
            candidate += timedelta(days=1)
        return WhenParseResult(due_at=candidate, source=f"at {hh:02d}:{mm:02d}")

    # tomorrow HH:MM
    m = re.fullmatch(r"tomorrow\s+(\d{1,2}):(\d{2})", text)
    if m:
        hh, mm = int(m.group(1)), int(m.group(2))
        candidate = (now + timedelta(days=1)).replace(hour=hh, minute=mm, second=0, microsecond=0)
        return WhenParseResult(due_at=candidate, source=f"tomorrow {hh:02d}:{mm:02d}")

    # Try dateutil absolute-ish parse (interprets in local tz)
    try:
        dt = dtparser.parse(text)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=ZoneInfo(tz_name))
        else:
            # convert to user's tz
            dt = dt.astimezone(ZoneInfo(tz_name))
        if dt > now:
            return WhenParseResult(due_at=dt, source=text)
    except Exception:
        pass

    return None

async def _send_html(update, text: str) -> None:
    if update.message is None:
        return
    await update.message.reply_text(text, parse_mode=ParseMode.HTML, disable_web_page_preview=True)
# ------------ Command handlers -------------

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.effective_chat is None:
        return
    chat_id = update.effective_chat.id
    tz = get_user_timezone(chat_id) or DEFAULT_TZ
    msg = (
        "<b>Hi, I’m Gretchen</b> — your reminders &amp; tasks helper!\n\n"
        "<b>Quick commands</b>\n"
        "• /setreminder — create a reminder\n"
        "• /reminders — list your reminders\n"
        "• /deletereminder &lt;id&gt; — delete by id\n"
        "• /timezone — view or set your timezone\n"
        "• /help — tips and examples\n\n"
        f"Your current timezone: <code>{html.escape(tz)}</code>"
    )
    await _send_html(update, msg)

async def help_(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    msg = (
        "<b>How to set a reminder</b>\n"
        "1. Send /setreminder\n"
        "2. When prompted for <i>when</i>, try formats like:\n"
        "   • <code>in 10m</code>   • <code>in 2h</code>   • <code>in 1d</code>\n"
        "   • <code>at 18:30</code>\n"
        "   • <code>tomorrow 09:00</code>\n"
        "   • or an absolute time like <code>2025-08-26 18:00</code>\n"
        "3. Then tell me <i>what</i> to remind you about\n\n"
        "<b>Example</b>\n"
        "<code>/setreminder</code> → <code>in 15m</code> → <code>stretch and drink water</code>\n\n"
        "Use <code>/timezone</code> to view or set your timezone, e.g. "
        "<code>/timezone Asia/Ho_Chi_Minh</code>"
    )
    await _send_html(update, msg)


async def timezone_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.effective_chat is None or update.message is None:
        return
    chat_id = update.effective_chat.id
    if context.args:
        candidate = " ".join(context.args).strip()
        try:
            _ = ZoneInfo(candidate)  # validate
            upsert_user_timezone(chat_id, candidate)
            await update.message.reply_text(f"Timezone set to {candidate}")
        except Exception:
            await update.message.reply_text("That doesn't look like a valid IANA timezone. Try something like `Asia/Ho_Chi_Minh` or `Europe/London`.")
        return

    # show current
    tz = get_user_timezone(chat_id) or DEFAULT_TZ
    now_str = _now_in_tz(tz).strftime("%Y-%m-%d %H:%M")
    await update.message.reply_text(f"Your timezone is {tz}. Local time there is {now_str}.\nSet a new one: /timezone <IANA>")

# ---- setreminder conversation ----

async def setreminder_entry(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if update.message is None:
        return ConversationHandler.END
    await update.message.reply_text(
        "When should I remind you? Try `in 10m`, `in 2h`, `at 18:30`, or `tomorrow 09:00`. Send /cancel to abort."
    )
    return ASK_WHEN

async def setreminder_ask_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if update.effective_chat is None or update.message is None or update.message.text is None:
        return ConversationHandler.END
    chat_id = update.effective_chat.id
    tz = get_user_timezone(chat_id) or DEFAULT_TZ
    when_str = update.message.text.strip()

    parsed = parse_when(when_str, tz)
    if not parsed:
        await update.message.reply_text("I couldn't parse that time. Try `in 10m`, `in 2h`, `at 18:30`, `tomorrow 09:00`, or an absolute like `2025-08-26 18:00`.")
        return ASK_WHEN

    if context.user_data is None:
        return ConversationHandler.END
    context.user_data["pending_due_at"] = parsed.due_at
    context.user_data["pending_when_src"] = parsed.source
    await update.message.reply_text("What should I say when it's time?")
    return ASK_TEXT

async def setreminder_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if update.effective_chat is None or update.message is None or update.message.text is None or context.user_data is None:
        return ConversationHandler.END
    chat_id = update.effective_chat.id
    tz = get_user_timezone(chat_id) or DEFAULT_TZ
    text = update.message.text.strip()
    due_at = context.user_data.pop("pending_due_at", None)
    when_src = context.user_data.pop("pending_when_src", None)
    if not due_at:
        await update.message.reply_text("Oops, I lost the schedule time. Let's try again. /setreminder")
        return ConversationHandler.END

    # Create reminder
    rem_id = uuid.uuid4().hex[:8]
    rem = {
        "id": rem_id,
        "chat_id": chat_id,
        "text": text,
        "due_at": due_at.isoformat(),
        "timezone": tz,
        "status": "scheduled",
        "created_at": datetime.utcnow().isoformat() + "Z",
        "updated_at": datetime.utcnow().isoformat() + "Z",
    }
    add_reminder(rem)

    # Schedule job
    # job name will be 'rem:<id>' so we can identify/remove
    job_name = f"rem:{rem_id}"
    if context.job_queue is not None:
        context.job_queue.run_once(reminder_job, when=due_at, chat_id=chat_id, name=job_name, data={"id": rem_id, "text": text})

    human_due = due_at.strftime("%Y-%m-%d %H:%M")
    msg = (
        "Got it ✅ I’ll remind you "
        f"<i>{html.escape(when_src)}</i> — "
        f"<code>{html.escape(human_due)} ({html.escape(tz)})</code>\n"
        f"ID: <code>{html.escape(rem_id)}</code>"
        )
    await update.message.reply_text(msg, parse_mode=ParseMode.HTML, disable_web_page_preview=True)
    return ConversationHandler.END

async def cancel_flow(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if context.user_data is not None:
        context.user_data.clear() 
    if update.message is not None:
        await update.message.reply_text("Cancelled.")
    return ConversationHandler.END

# ---- jobs ----
async def reminder_job(context: ContextTypes.DEFAULT_TYPE) -> None:
    job = context.job
    if job is None or job.data is None:
        return
    data = job.data  # type: ignore
    rem_id = data["id"]  # type: ignore
    text = data["text"]  # type: ignore
    chat_id = job.chat_id
    if chat_id is None:
        return
    await context.bot.send_message(chat_id, f"⏰ Reminder: {text}")
    update_reminder_status(rem_id, "done")

# ---- listing & deleting ----
async def list_reminders(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.effective_chat is None or update.message is None:
        return
    chat_id = update.effective_chat.id
    tz = get_user_timezone(chat_id) or DEFAULT_TZ
    tzinfo = ZoneInfo(tz)
    rows = []
    now = datetime.now(tzinfo)
    for r in load_reminders():
        if r.get("chat_id") != chat_id:
            continue
        if r.get("status") not in ("scheduled", "done"):
            continue
        due_at = dtparser.isoparse(r["due_at"])
        if due_at.tzinfo is None:
            due_at = due_at.replace(tzinfo=tzinfo)
        local_due = due_at.astimezone(tzinfo).strftime("%Y-%m-%d %H:%M")
        rows.append((r["id"], r["status"], local_due, r["text"]))

    if not rows:
        await update.message.reply_text("You have no reminders yet. Try /setreminder")
        return

    rows.sort(key=lambda x: (x[1] != "scheduled", x[2]))  # scheduled first, then by due time
    lines = ["Your reminders"]
    for rid, status, due, text in rows[:50]:
        emoji = "🟢" if status == "scheduled" else "✅"
        lines.append(f"{emoji} `{rid}` — {due} — {text}")
    await update.message.reply_text("\n".join(lines))


async def delete_reminder_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.message is None:
        return
    if not context.args:
        await update.message.reply_text("Usage: /deletereminder <id>")
        return
    rid = context.args[0].strip()
    # cancel job if present
    if context.job_queue is not None:
        jobs = context.job_queue.get_jobs_by_name(f"rem:{rid}")
        for j in jobs:
            j.schedule_removal()

    ok = delete_reminder(rid)
    if ok:
        await update.message.reply_text(f"Deleted reminder {rid}")
    else:
        await update.message.reply_text("Couldn't find that reminder ID.")

# ---- bootstrapping: reschedule persisted reminders ----
async def _reschedule_persisted(app: Application) -> None:
    all_rems = load_reminders()
    now_utc = datetime.utcnow()
    count = 0
    for r in all_rems:
        if r.get("status") != "scheduled":
            continue
        rid = r["id"]
        chat_id = r["chat_id"]
        text = r["text"]
        due_at = dtparser.isoparse(r["due_at"])
        # If timezone-naive in file, assume DEFAULT_TZ to be safe
        if due_at.tzinfo is None:
            due_at = due_at.replace(tzinfo=ZoneInfo(os.getenv("DEFAULT_TZ", "Asia/Ho_Chi_Minh")))
        if due_at.astimezone(ZoneInfo("UTC")).replace(tzinfo=None) <= now_utc:
            # In the past; mark as done (we missed it)
            update_reminder_status(rid, "done")
            continue
        job_name = f"rem:{rid}"
        # Avoid duplicate scheduling if job exists
        if app.job_queue is not None and app.job_queue.get_jobs_by_name(job_name):
            continue
        if app.job_queue is not None:
            app.job_queue.run_once(reminder_job, when=due_at, chat_id=chat_id, name=job_name, data={"id": rid, "text": text})
            count += 1
    print(f"[bootstrap] Rescheduled {count} reminders.")

def main() -> None:
    if TOKEN is None:
        raise RuntimeError("TELEGRAM_TOKEN environment variable not set. Put it in .env")
    application = Application.builder().token(TOKEN).build()

    # Basic commands
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_))
    application.add_handler(CommandHandler("timezone", timezone_cmd))
    application.add_handler(CommandHandler("reminders", list_reminders))
    application.add_handler(CommandHandler("deletereminder", delete_reminder_cmd))

    # Conversation: /setreminder
    conv = ConversationHandler(
        entry_points=[CommandHandler("setreminder", setreminder_entry)],
        states={
            ASK_WHEN: [MessageHandler(filters.TEXT & ~filters.COMMAND, setreminder_ask_text)],
            ASK_TEXT: [MessageHandler(filters.TEXT & ~filters.COMMAND, setreminder_confirm)],
        },
        fallbacks=[CommandHandler("cancel", cancel_flow)],
    )
    application.add_handler(conv)

    # Bootstrap: reschedule persisted reminders after start
    application.post_init = _reschedule_persisted  # type: ignore

    print("Bot is starting...")
    application.run_polling(close_loop=False)

if __name__ == "__main__":
    main()
