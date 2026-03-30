"""Proactive monitoring system — Jarvis watches things and alerts you.

Unlike tools (which Claude calls on demand), monitors run continuously
in the background and trigger alerts via TTS when conditions are met.

Built-in monitors:
- System health: CPU > 90%, disk > 95%, memory > 90%
- Email: new unread emails (polling)
- Reminders: handled by APScheduler (see tools/reminders.py)
- Calendar: upcoming events (if configured)
- Custom: user-defined via Claude ("alert me if CPU goes above 80%")

Monitors are lightweight — each is a simple function that returns
None (all good) or a string (alert message). They run on intervals
via APScheduler.
"""

import threading
from datetime import datetime
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger
import psutil

import config

_scheduler = None
_alert_callback = None  # function(message) — called when a monitor triggers
_active_monitors = {}   # name -> job_id


def init_monitors(alert_callback):
    """Initialize the monitoring system.

    alert_callback: function(message) called when a monitor wants to alert the user.
    """
    global _scheduler, _alert_callback
    _alert_callback = alert_callback

    _scheduler = BackgroundScheduler()
    _scheduler.start()

    # Register built-in monitors
    add_monitor("system_health", _check_system_health, interval_minutes=5)
    add_monitor("email_check", _check_new_email, interval_minutes=15)

    print(f"[Monitors active: {', '.join(_active_monitors.keys())}]")


def add_monitor(name, check_function, interval_minutes=5):
    """Add a background monitor.

    Args:
        name: Unique name for this monitor.
        check_function: Callable that returns None (OK) or str (alert message).
        interval_minutes: How often to run the check.
    """
    if not _scheduler:
        return

    # Remove existing monitor with same name
    if name in _active_monitors:
        remove_monitor(name)

    job = _scheduler.add_job(
        _run_check,
        trigger=IntervalTrigger(minutes=interval_minutes),
        args=[name, check_function],
        id=f"monitor_{name}",
        replace_existing=True,
    )
    _active_monitors[name] = job.id


def remove_monitor(name):
    """Remove a background monitor."""
    if name in _active_monitors:
        try:
            _scheduler.remove_job(_active_monitors[name])
        except Exception:
            pass
        del _active_monitors[name]


def list_monitors():
    """List all active monitors."""
    if not _active_monitors:
        return "No active monitors."
    lines = []
    for name in sorted(_active_monitors.keys()):
        job = _scheduler.get_job(_active_monitors[name])
        next_run = job.next_run_time.strftime("%H:%M:%S") if job and job.next_run_time else "unknown"
        lines.append(f"- {name} (next check: {next_run})")
    return "\n".join(lines)


def _run_check(name, check_function):
    """Execute a monitor check and fire alert if needed."""
    try:
        result = check_function()
        if result and _alert_callback:
            _alert_callback(f"[Monitor: {name}] {result}")
    except Exception as e:
        print(f"[Monitor {name} error: {e}]")


# === Built-in monitors ===

# Track state to avoid repeat alerts
_last_email_count = None
_alert_cooldowns = {}  # name -> last alert time


def _check_system_health():
    """Alert if system resources are critically high."""
    now = datetime.now()

    # Cooldown: don't alert more than once per 30 minutes for same issue
    alerts = []

    cpu = psutil.cpu_percent(interval=1)
    if cpu > 90:
        key = "cpu_high"
        if _should_alert(key, cooldown_minutes=30):
            alerts.append(f"CPU usage is critically high at {cpu}%")

    memory = psutil.virtual_memory()
    if memory.percent > 90:
        key = "memory_high"
        if _should_alert(key, cooldown_minutes=30):
            alerts.append(f"Memory usage is at {memory.percent}%")

    disk = psutil.disk_usage("/")
    if disk.percent > 95:
        key = "disk_high"
        if _should_alert(key, cooldown_minutes=60):
            alerts.append(f"Disk is almost full at {disk.percent}%")

    if alerts:
        return "System alert: " + ". ".join(alerts)
    return None


def _check_new_email():
    """Alert if there are new unread emails."""
    global _last_email_count

    if not config.EMAIL_IMAP_SERVER or not config.EMAIL_ADDRESS:
        return None

    try:
        import imaplib
        mail = imaplib.IMAP4_SSL(config.EMAIL_IMAP_SERVER)
        mail.login(config.EMAIL_ADDRESS, config.EMAIL_PASSWORD)
        mail.select("INBOX", readonly=True)
        _, data = mail.search(None, "UNSEEN")
        unread_count = len(data[0].split()) if data[0] else 0
        mail.logout()

        if _last_email_count is not None and unread_count > _last_email_count:
            new = unread_count - _last_email_count
            _last_email_count = unread_count
            if _should_alert("new_email", cooldown_minutes=5):
                return f"You have {new} new email{'s' if new > 1 else ''}"
        else:
            _last_email_count = unread_count

        return None
    except Exception:
        return None


def _should_alert(key, cooldown_minutes=30):
    """Check if enough time has passed since the last alert for this key."""
    now = datetime.now()
    last = _alert_cooldowns.get(key)
    if last and (now - last).total_seconds() < cooldown_minutes * 60:
        return False
    _alert_cooldowns[key] = now
    return True


# === Custom monitors (created by Claude via tool_use) ===

def create_custom_monitor(name, metric, threshold, operator="above", interval_minutes=5):
    """Create a custom monitor for a system metric.

    Args:
        name: Monitor name.
        metric: "cpu", "memory", "disk", or "network_sent", "network_recv".
        threshold: Numeric threshold value.
        operator: "above" or "below".
        interval_minutes: Check interval.
    """
    def check():
        if metric == "cpu":
            value = psutil.cpu_percent(interval=1)
        elif metric == "memory":
            value = psutil.virtual_memory().percent
        elif metric == "disk":
            value = psutil.disk_usage("/").percent
        elif metric == "network_sent":
            value = psutil.net_io_counters().bytes_sent / (1024 ** 2)  # MB
        elif metric == "network_recv":
            value = psutil.net_io_counters().bytes_recv / (1024 ** 2)  # MB
        else:
            return None

        triggered = (value > threshold) if operator == "above" else (value < threshold)
        if triggered and _should_alert(f"custom_{name}", cooldown_minutes=interval_minutes * 2):
            return f"{metric} is {value:.1f}% ({operator} {threshold}% threshold)"
        return None

    add_monitor(name, check, interval_minutes=interval_minutes)
    return f"Monitor '{name}' created: alert when {metric} {operator} {threshold} (checking every {interval_minutes}m)"
