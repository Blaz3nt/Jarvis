import sqlite3
import os
import re
from datetime import datetime, timedelta
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.date import DateTrigger
from apscheduler.triggers.interval import IntervalTrigger
import config

_scheduler = None
_reminder_callback = None


def init_scheduler(callback=None):
    """Initialize the reminder scheduler. Call this at startup.

    callback: function(message) called when a reminder triggers.
    """
    global _scheduler, _reminder_callback
    _reminder_callback = callback

    # Ensure data directory exists
    os.makedirs(os.path.dirname(config.REMINDERS_DB), exist_ok=True)

    # Initialize database
    conn = sqlite3.connect(config.REMINDERS_DB)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS reminders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            message TEXT NOT NULL,
            trigger_time TEXT NOT NULL,
            recurring TEXT DEFAULT '',
            active INTEGER DEFAULT 1,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.commit()
    conn.close()

    # Start scheduler
    _scheduler = BackgroundScheduler()
    _scheduler.start()

    # Reload existing reminders
    _reload_reminders()


def _reload_reminders():
    """Reload active reminders from the database into the scheduler."""
    conn = sqlite3.connect(config.REMINDERS_DB)
    rows = conn.execute("SELECT id, message, trigger_time, recurring FROM reminders WHERE active = 1").fetchall()
    conn.close()

    for rid, message, trigger_time, recurring in rows:
        _schedule_reminder(rid, message, trigger_time, recurring)


def _fire_reminder(reminder_id, message, recurring):
    """Called when a reminder triggers."""
    print(f"\n🔔 REMINDER: {message}")
    if _reminder_callback:
        _reminder_callback(message)

    # Deactivate non-recurring reminders
    if not recurring:
        conn = sqlite3.connect(config.REMINDERS_DB)
        conn.execute("UPDATE reminders SET active = 0 WHERE id = ?", (reminder_id,))
        conn.commit()
        conn.close()


def _parse_relative_time(time_str):
    """Parse relative time strings like 'in 30 minutes', 'in 2 hours'."""
    time_str = time_str.strip().lower()
    match = re.match(r"in\s+(\d+)\s+(minute|minutes|min|hour|hours|hr|second|seconds|sec|day|days)", time_str)
    if not match:
        return None
    amount = int(match.group(1))
    unit = match.group(2)
    if unit.startswith("min"):
        return datetime.now() + timedelta(minutes=amount)
    elif unit.startswith("hour") or unit.startswith("hr"):
        return datetime.now() + timedelta(hours=amount)
    elif unit.startswith("sec"):
        return datetime.now() + timedelta(seconds=amount)
    elif unit.startswith("day"):
        return datetime.now() + timedelta(days=amount)
    return None


def _schedule_reminder(rid, message, trigger_time, recurring):
    """Add a reminder to the APScheduler."""
    if not _scheduler:
        return

    if recurring:
        interval_map = {
            "daily": {"days": 1},
            "weekly": {"weeks": 1},
            "monthly": {"days": 30},
        }
        kwargs = interval_map.get(recurring, {"days": 1})
        trigger = IntervalTrigger(**kwargs, start_date=trigger_time)
    else:
        dt = datetime.fromisoformat(trigger_time)
        if dt < datetime.now():
            return  # Skip past reminders
        trigger = DateTrigger(run_date=dt)

    _scheduler.add_job(
        _fire_reminder,
        trigger=trigger,
        args=[rid, message, recurring],
        id=f"reminder_{rid}",
        replace_existing=True,
    )


def create_reminder(message, time, recurring=""):
    """Create a new reminder."""
    # Parse time
    dt = _parse_relative_time(time)
    if dt is None:
        try:
            dt = datetime.fromisoformat(time)
        except ValueError:
            return f"Could not parse time: '{time}'. Use ISO 8601 format or relative (e.g. 'in 30 minutes')."

    trigger_time = dt.isoformat()

    conn = sqlite3.connect(config.REMINDERS_DB)
    cursor = conn.execute(
        "INSERT INTO reminders (message, trigger_time, recurring) VALUES (?, ?, ?)",
        (message, trigger_time, recurring)
    )
    rid = cursor.lastrowid
    conn.commit()
    conn.close()

    _schedule_reminder(rid, message, trigger_time, recurring)

    time_str = dt.strftime("%Y-%m-%d %H:%M:%S")
    recur_str = f" (recurring: {recurring})" if recurring else ""
    return f"Reminder #{rid} created: '{message}' at {time_str}{recur_str}"


def list_reminders():
    """List all active reminders."""
    conn = sqlite3.connect(config.REMINDERS_DB)
    rows = conn.execute(
        "SELECT id, message, trigger_time, recurring FROM reminders WHERE active = 1 ORDER BY trigger_time"
    ).fetchall()
    conn.close()

    if not rows:
        return "No active reminders."

    results = []
    for rid, message, trigger_time, recurring in rows:
        recur_str = f" [recurring: {recurring}]" if recurring else ""
        results.append(f"#{rid}: '{message}' — {trigger_time}{recur_str}")
    return "\n".join(results)


def delete_reminder(reminder_id):
    """Delete a reminder by ID."""
    conn = sqlite3.connect(config.REMINDERS_DB)
    cursor = conn.execute("UPDATE reminders SET active = 0 WHERE id = ? AND active = 1", (reminder_id,))
    conn.commit()
    conn.close()

    if cursor.rowcount == 0:
        return f"Reminder #{reminder_id} not found or already deleted."

    # Remove from scheduler
    if _scheduler:
        try:
            _scheduler.remove_job(f"reminder_{reminder_id}")
        except Exception:
            pass

    return f"Reminder #{reminder_id} deleted."
