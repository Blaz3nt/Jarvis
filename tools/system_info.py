import platform
import psutil
from datetime import datetime, timedelta


def get_system_info(detail="summary"):
    """Get system information."""
    cpu_percent = psutil.cpu_percent(interval=1)
    memory = psutil.virtual_memory()
    disk = psutil.disk_usage("/")
    boot_time = datetime.fromtimestamp(psutil.boot_time())
    uptime = datetime.now() - boot_time

    if detail == "summary":
        return (
            f"System: {platform.system()} {platform.release()}\n"
            f"CPU: {cpu_percent}% used ({psutil.cpu_count()} cores)\n"
            f"Memory: {memory.percent}% used ({memory.used // (1024**3):.1f}/{memory.total // (1024**3):.1f} GB)\n"
            f"Disk: {disk.percent}% used ({disk.used // (1024**3):.1f}/{disk.total // (1024**3):.1f} GB)\n"
            f"Uptime: {str(uptime).split('.')[0]}"
        )

    # Full detail
    net = psutil.net_io_counters()
    temps = psutil.sensors_temperatures() if hasattr(psutil, "sensors_temperatures") else {}

    lines = [
        f"System: {platform.system()} {platform.release()} ({platform.machine()})",
        f"Python: {platform.python_version()}",
        f"Hostname: {platform.node()}",
        f"CPU: {cpu_percent}% used ({psutil.cpu_count(logical=False)} physical / {psutil.cpu_count()} logical cores)",
        f"Memory: {memory.percent}% ({memory.used // (1024**2)} MB / {memory.total // (1024**2)} MB)",
        f"Swap: {psutil.swap_memory().percent}% ({psutil.swap_memory().used // (1024**2)} MB / {psutil.swap_memory().total // (1024**2)} MB)",
        f"Disk /: {disk.percent}% ({disk.used // (1024**3):.1f} GB / {disk.total // (1024**3):.1f} GB)",
        f"Network: Sent {net.bytes_sent // (1024**2)} MB / Recv {net.bytes_recv // (1024**2)} MB",
        f"Uptime: {str(uptime).split('.')[0]}",
        f"Boot time: {boot_time.strftime('%Y-%m-%d %H:%M:%S')}",
    ]

    if temps:
        for name, entries in temps.items():
            for entry in entries:
                lines.append(f"Temp ({name}/{entry.label or 'core'}): {entry.current}°C")

    # Top 5 processes by memory
    lines.append("\nTop processes by memory:")
    procs = sorted(psutil.process_iter(["pid", "name", "memory_percent"]),
                   key=lambda p: p.info["memory_percent"] or 0, reverse=True)[:5]
    for p in procs:
        lines.append(f"  PID {p.info['pid']}: {p.info['name']} ({p.info['memory_percent']:.1f}%)")

    return "\n".join(lines)
