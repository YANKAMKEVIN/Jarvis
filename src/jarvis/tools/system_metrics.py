"""Live machine metrics via psutil (CPU, memory, disk, network, battery).

Thin and injectable: the capability passes a psutil-like module in tests so the
probe needs no real hardware. All reads are local and read-only.
"""

from __future__ import annotations

import os
import re
import time

try:  # psutil is a desktop extra; the probe degrades gracefully without it.
    import psutil as _psutil
except Exception:  # pragma: no cover - environment without psutil
    _psutil = None


_VERSION_NAME = re.compile(r"^\d+(\.\d+)+$")


def app_name(name: str | None, exe: str | None) -> str:
    """Human app name for a process: the outermost `.app` bundle in its path
    ('Google Chrome Helper (Renderer)' -> 'Google Chrome'), and Claude Code for
    its CLI, whether named after its version ('2.1.303') or bundled by the
    desktop app ('.../claude-code/2.1.309/.../claude.app')."""
    name = name or "?"
    exe = exe or ""
    low = exe.lower()
    if "/claude-code/" in low or (_VERSION_NAME.match(name) and "claude" in low):
        return "Claude Code"
    bundle = re.search(r"/([^/]+)\.app/", exe)
    if bundle:
        return bundle.group(1)
    return name


class SystemMetricsProbe:
    def __init__(self, psutil_module=None, clock=None, sleep=None):
        self.ps = psutil_module if psutil_module is not None else _psutil
        self._clock = clock if clock is not None else time.time
        self._sleep = sleep if sleep is not None else time.sleep

    def available(self) -> bool:
        return self.ps is not None

    def snapshot(self, cpu_interval: float | None = 0.15) -> dict:
        """One reading of the machine's state. `cpu_interval` blocks briefly for
        a meaningful CPU figure; the background sampler passes None (compares to
        the previous call instead)."""
        ps = self.ps
        if ps is None:
            raise RuntimeError("psutil indisponible")
        vm = ps.virtual_memory()
        swap = ps.swap_memory()
        # On modern macOS "/" is the sealed read-only system volume; the user's
        # home sits on the data volume, which is the meaningful fill figure.
        disk = ps.disk_usage(os.path.expanduser("~"))
        net = ps.net_io_counters()
        battery = None
        try:
            battery = ps.sensors_battery()
        except Exception:
            battery = None
        try:
            load1 = os.getloadavg()[0]
        except (OSError, AttributeError):
            load1 = None
        return {
            "ts": self._clock(),
            "cpu": float(ps.cpu_percent(interval=cpu_interval)),
            "mem": float(vm.percent),
            "mem_used": int(vm.used),
            "mem_total": int(vm.total),
            "swap": float(swap.percent),
            "disk": float(disk.percent),
            "disk_used": int(disk.used),
            "disk_total": int(disk.total),
            "net_sent": int(net.bytes_sent),
            "net_recv": int(net.bytes_recv),
            "load1": float(load1) if load1 is not None else None,
            "battery": float(battery.percent) if battery is not None else None,
            "power_plugged": bool(battery.power_plugged) if battery is not None else None,
        }

    def top_apps(self, limit: int = 6) -> list[dict]:
        """Resident memory summed per application, largest first. Helper
        processes (Chrome renderers, Electron helpers) fold into their app, so
        the list says which app is heavy rather than which tab."""
        ps = self.ps
        if ps is None:
            raise RuntimeError("psutil indisponible")
        limit = max(1, min(int(limit) if isinstance(limit, (int, float)) else 6, 20))
        total = float(ps.virtual_memory().total) or 1.0
        apps: dict[str, dict] = {}
        for proc in ps.process_iter(["pid", "name", "exe", "memory_info"]):
            info = proc.info
            mem = info.get("memory_info")
            rss = int(getattr(mem, "rss", 0) or 0)
            if rss <= 0:
                continue
            name = app_name(info.get("name"), info.get("exe"))
            row = apps.setdefault(name, {"name": name, "bytes": 0, "processes": 0})
            row["bytes"] += rss
            row["processes"] += 1
        rows = sorted(apps.values(), key=lambda r: r["bytes"], reverse=True)[:limit]
        for row in rows:
            row["value"] = round(row["bytes"] / total * 100, 1)
        return rows

    def top_processes(self, by: str = "memory", limit: int = 5) -> list[dict]:
        ps = self.ps
        if ps is None:
            raise RuntimeError("psutil indisponible")
        limit = max(1, min(int(limit) if isinstance(limit, (int, float)) else 5, 20))
        if by == "cpu":
            return self._top_cpu(limit)
        rows = []
        for proc in ps.process_iter(["pid", "name", "memory_percent"]):
            info = proc.info
            rows.append({
                "pid": info.get("pid"),
                "name": info.get("name") or "?",
                "value": round(float(info.get("memory_percent") or 0.0), 1),
            })
        rows.sort(key=lambda r: r["value"], reverse=True)
        return rows[:limit]

    def _top_cpu(self, limit: int) -> list[dict]:
        ps = self.ps
        procs = list(ps.process_iter(["pid", "name"]))
        for proc in procs:  # prime: first call always returns 0.0
            try:
                proc.cpu_percent(None)
            except Exception:
                pass
        self._sleep(0.1)
        rows = []
        for proc in procs:
            try:
                rows.append({
                    "pid": proc.info.get("pid"),
                    "name": proc.info.get("name") or "?",
                    "value": round(float(proc.cpu_percent(None)), 1),
                })
            except Exception:
                continue
        rows.sort(key=lambda r: r["value"], reverse=True)
        return rows[:limit]
