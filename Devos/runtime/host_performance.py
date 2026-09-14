#!/usr/bin/env python3
"""Bounded, read-only host performance snapshot for DevOS.

Stdlib-only and portable across Windows/Linux/macOS where possible.
Produces a stable JSON contract suitable for DevOS tool invocation and evidence capture.
"""
from __future__ import annotations

import argparse
import ctypes
import json
import math
import os
import platform
import shutil
import socket
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SCHEMA_VERSION = "devos.host_performance.v1"
DEFAULT_SAMPLE_MS = 250


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _round(value: float | None, digits: int = 2) -> float | None:
    if value is None or not math.isfinite(value):
        return None
    return round(value, digits)


def _percent(used: int, total: int) -> float | None:
    if total <= 0:
        return None
    return _round((used / total) * 100.0)


class CpuTimes:
    def __init__(self, idle: int, total: int):
        self.idle = idle
        self.total = total


def _windows_cpu_times() -> CpuTimes:
    class FILETIME(ctypes.Structure):
        _fields_ = [("dwLowDateTime", ctypes.c_uint32), ("dwHighDateTime", ctypes.c_uint32)]

    idle = FILETIME(); kernel = FILETIME(); user = FILETIME()
    ok = ctypes.windll.kernel32.GetSystemTimes(ctypes.byref(idle), ctypes.byref(kernel), ctypes.byref(user))
    if not ok:
        raise OSError("GetSystemTimes failed")

    def value(ft: FILETIME) -> int:
        return (ft.dwHighDateTime << 32) | ft.dwLowDateTime
    return CpuTimes(value(idle), value(kernel) + value(user))


def _linux_cpu_times() -> CpuTimes:
    line = Path("/proc/stat").read_text(encoding="utf-8").splitlines()[0]
    parts = line.split()
    if not parts or parts[0] != "cpu":
        raise OSError("unexpected /proc/stat format")
    vals = [int(x) for x in parts[1:]]
    vals += [0] * (8 - len(vals))
    idle = vals[3] + vals[4]
    total = sum(vals)
    return CpuTimes(idle, total)


def _cpu_times() -> CpuTimes | None:
    try:
        if os.name == "nt":
            return _windows_cpu_times()
        if sys.platform.startswith("linux"):
            return _linux_cpu_times()
    except (OSError, ValueError):
        return None
    return None


def cpu_percent(sample_ms: int) -> float | None:
    before = _cpu_times()
    if before is None:
        return None
    time.sleep(max(0, sample_ms) / 1000.0)
    after = _cpu_times()
    if after is None:
        return None
    idle = after.idle - before.idle
    total = after.total - before.total
    if total <= 0:
        return None
    busy = max(0, total - idle)
    return _round((busy / total) * 100.0)


def memory_snapshot() -> dict[str, Any]:
    if os.name == "nt":
        class MEMORYSTATUSEX(ctypes.Structure):
            _fields_ = [
                ("dwLength", ctypes.c_ulong),
                ("dwMemoryLoad", ctypes.c_ulong),
                ("ullTotalPhys", ctypes.c_ulonglong),
                ("ullAvailPhys", ctypes.c_ulonglong),
                ("ullTotalPageFile", ctypes.c_ulonglong),
                ("ullAvailPageFile", ctypes.c_ulonglong),
                ("ullTotalVirtual", ctypes.c_ulonglong),
                ("ullAvailVirtual", ctypes.c_ulonglong),
                ("sullAvailExtendedVirtual", ctypes.c_ulonglong),
            ]
        status = MEMORYSTATUSEX(); status.dwLength = ctypes.sizeof(MEMORYSTATUSEX)
        if not ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status)):
            raise OSError("GlobalMemoryStatusEx failed")
        total = int(status.ullTotalPhys); available = int(status.ullAvailPhys)
        used = total - available
        return {"total_bytes": total, "available_bytes": available, "used_bytes": used, "used_percent": _percent(used, total)}

    if sys.platform.startswith("linux") and Path("/proc/meminfo").exists():
        values: dict[str, int] = {}
        for line in Path("/proc/meminfo").read_text(encoding="utf-8").splitlines():
            key, raw = line.split(":", 1)
            first = raw.strip().split()[0]
            values[key] = int(first) * 1024
        total = values.get("MemTotal", 0)
        available = values.get("MemAvailable", values.get("MemFree", 0))
        used = max(0, total - available)
        return {"total_bytes": total, "available_bytes": available, "used_bytes": used, "used_percent": _percent(used, total)}

    return {"total_bytes": None, "available_bytes": None, "used_bytes": None, "used_percent": None}


def uptime_seconds() -> float | None:
    try:
        if os.name == "nt":
            ctypes.windll.kernel32.GetTickCount64.restype = ctypes.c_ulonglong
            return _round(ctypes.windll.kernel32.GetTickCount64() / 1000.0)
        if sys.platform.startswith("linux"):
            return _round(float(Path("/proc/uptime").read_text(encoding="utf-8").split()[0]))
    except (OSError, ValueError):
        return None
    return None


def process_count() -> int | None:
    try:
        if sys.platform.startswith("linux"):
            return sum(1 for p in Path("/proc").iterdir() if p.name.isdigit())
        if os.name == "nt":
            proc = subprocess.run(
                ["tasklist", "/FO", "CSV", "/NH"],
                capture_output=True,
                text=True,
                timeout=5,
                check=False,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
            if proc.returncode == 0:
                return sum(1 for line in proc.stdout.splitlines() if line.strip())
    except (OSError, subprocess.SubprocessError):
        return None
    return None


def _default_roots() -> list[str]:
    if os.name == "nt":
        drive = os.environ.get("SystemDrive", "C:")
        return [drive + "\\" if not drive.endswith("\\") else drive]
    return ["/"]


def disk_snapshot(roots: list[str]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    seen: set[str] = set()
    for root in roots:
        p = str(Path(root))
        if p in seen:
            continue
        seen.add(p)
        try:
            usage = shutil.disk_usage(p)
            rows.append({
                "root": p,
                "total_bytes": usage.total,
                "free_bytes": usage.free,
                "used_bytes": usage.used,
                "used_percent": _percent(usage.used, usage.total),
            })
        except OSError as exc:
            rows.append({"root": p, "error": str(exc)})
    return rows


def load_average() -> dict[str, float | None]:
    try:
        one, five, fifteen = os.getloadavg()
        return {"one_min": _round(one), "five_min": _round(five), "fifteen_min": _round(fifteen)}
    except (AttributeError, OSError):
        return {"one_min": None, "five_min": None, "fifteen_min": None}


def classify_pressure(cpu: float | None, mem: float | None, disks: list[dict[str, Any]]) -> dict[str, Any]:
    disk_max = max((float(d["used_percent"]) for d in disks if isinstance(d.get("used_percent"), (int, float))), default=None)
    scores = [x for x in (cpu, mem, disk_max) if isinstance(x, (int, float))]
    peak = max(scores, default=0.0)
    if peak >= 95:
        level = "CRITICAL"
    elif peak >= 85:
        level = "HIGH"
    elif peak >= 70:
        level = "ELEVATED"
    else:
        level = "NORMAL"
    return {"level": level, "peak_percent": _round(peak), "disk_max_used_percent": _round(disk_max) if disk_max is not None else None}


def collect_snapshot(sample_ms: int = DEFAULT_SAMPLE_MS, roots: list[str] | None = None) -> dict[str, Any]:
    roots = roots or _default_roots()
    warnings: list[str] = []
    try:
        mem = memory_snapshot()
    except OSError as exc:
        mem = {"total_bytes": None, "available_bytes": None, "used_bytes": None, "used_percent": None}
        warnings.append(f"memory_probe_failed: {exc}")
    cpu = cpu_percent(sample_ms)
    if cpu is None:
        warnings.append("cpu_percent_unavailable")
    disks = disk_snapshot(roots)
    proc_count = process_count()
    if proc_count is None:
        warnings.append("process_count_unavailable")

    logical = os.cpu_count()
    payload = {
        "schema_version": SCHEMA_VERSION,
        "captured_at_utc": _utc_now(),
        "host": {"hostname": socket.gethostname(), "platform": platform.system(), "release": platform.release(), "machine": platform.machine()},
        "cpu": {"logical_processors": logical, "sample_ms": sample_ms, "used_percent": cpu, "load_average": load_average()},
        "memory": mem,
        "disks": disks,
        "uptime_seconds": uptime_seconds(),
        "process_count": proc_count,
        "pressure": classify_pressure(cpu, mem.get("used_percent"), disks),
        "warnings": warnings,
        "provenance": {"collector": "Devos/runtime/host_performance.py", "mode": "read_only_local", "authority_effect": "NONE"},
    }
    return payload


def write_json(payload: dict[str, Any], output: Path | None, compact: bool = False) -> str:
    text = json.dumps(payload, indent=None if compact else 2, sort_keys=True) + "\n"
    if output is not None:
        output.parent.mkdir(parents=True, exist_ok=True)
        temp = output.with_suffix(output.suffix + ".tmp")
        temp.write_text(text, encoding="utf-8")
        os.replace(temp, output)
    return text


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="DevOS bounded host performance snapshot")
    sub = p.add_subparsers(dest="command", required=True)
    s = sub.add_parser("snapshot", help="capture one read-only host performance snapshot")
    s.add_argument("--sample-ms", type=int, default=DEFAULT_SAMPLE_MS, choices=range(50, 5001), metavar="50..5000")
    s.add_argument("--root", action="append", default=[], help="filesystem root to measure; repeatable")
    s.add_argument("--output", type=Path, help="write JSON atomically to this path")
    s.add_argument("--compact", action="store_true")
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "snapshot":
        payload = collect_snapshot(sample_ms=args.sample_ms, roots=args.root or None)
        sys.stdout.write(write_json(payload, args.output, args.compact))
        return 0
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
