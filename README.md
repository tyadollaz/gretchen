# gretchen
Great at Reminders, Events, Tasks, Calendar and Habits with Engaging Notifications

## Overview
GRETCHEN is a Telegram bot that helps you manage reminders, tasks, habits, and events with one-time and recurring schedules, with timezone support and friendly notifications.

- Local/dev: runs with polling and can use simple JSON storage or MongoDB
- Production (Vercel): uses serverless cron to process due items and MongoDB for storage

## Features
- /start guided onboarding (nickname and timezone)
- /help quick reference
- /timezone [IANA] view/set timezone
- /setreminder one-time or recurring reminders (hourly/daily/weekly)
- /managereminder edit/delete reminders
- /reminders list reminders
- (Scaffolding in place for tasks/habits/events)

## Requirements
- Python 3.11+
- Telegram Bot token
- MongoDB (Atlas or self-hosted) for production

## Environment Variables
- TELEGRAM_TOKEN: Telegram bot token
- MONGODB_URI: Mongo connection string (enables Mongo backend)
- MONGODB_DB: Database name (default: gretchen)
- DEFAULT_TZ: Default IANA timezone (default: Asia/Ho_Chi_Minh)
- USE_MONGO: Set to "1" to force Mongo backend (optional)

## Install
```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```
```
Run the bot (polling):
```bash
python main.py
```
The bot will use JSON storage by default, or Mongo if `USE_MONGO=1` or `MONGODB_URI` is set.

## MongoDB backend
- Indexes are created on first use.
- Collections: `users`, `reminders` (future: `tasks`, `habits`, `events`).

## Serverless cron on Vercel
This repo includes `api/cron.py` and `vercel.json`.
- Endpoint: `/api/cron/process-due`
- Runs every minute via Vercel Cron
- It scans scheduled reminders that are due and sends Telegram messages, then marks them done (for one-time reminders).

## Commands
- /start: intro and current timezone
- /help: usage examples
- /timezone [IANA]: set or view timezone (e.g., `/timezone Europe/London`)
- /setreminder: interactive flow (when → what)
- /reminders: list reminders
- /deletereminder <id>: delete by id

## Notes
- HTML in messages is sanitized; bot uses ParseMode.HTML where appropriate.
- Time parsing supports: `in 10m`, `in 2h`, `in 1d`, `at 18:30`, `tomorrow 09:00`, or absolute times like `2025-08-26 18:00`.

## Roadmap
- Add flows for tasks, habits, and events sharing the same schedule engine
- Inline keyboards for snooze/done
- Rich recurrence rules and exclusions
