"""What machine is this? Recorded with every run, because the numbers mean nothing without it."""
from __future__ import annotations

import os
import platform
import shutil
import subprocess
import sys


def _run(cmd: list[str]) -> str:
    try:
        return subprocess.run(cmd, capture_output=True, text=True, timeout=10).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return ""


def collect() -> dict:
    info = {"os": f"{platform.system()} {platform.release()}", "arch": platform.machine(),
            "cpu": platform.processor() or platform.machine(), "cores": os.cpu_count(),
            "ram_gb": None, "gpu": None}
    if sys.platform == "darwin":
        info["os"] = f"macOS {_run(['sw_vers', '-productVersion'])}"
        info["cpu"] = _run(["sysctl", "-n", "machdep.cpu.brand_string"]) or info["cpu"]
        mem = _run(["sysctl", "-n", "hw.memsize"])
        info["ram_gb"] = round(int(mem) / 2 ** 30) if mem.isdigit() else None
        p, e = _run(["sysctl", "-n", "hw.perflevel0.physicalcpu"]), _run(["sysctl", "-n", "hw.perflevel1.physicalcpu"])
        if p.isdigit():
            info["cores"] = f"{p}P+{e}E" if e.isdigit() else p
        if platform.machine() == "arm64":
            info["gpu"] = "Apple GPU (unified memory)"
    elif sys.platform.startswith("linux"):
        try:
            with open("/proc/cpuinfo") as f:
                for line in f:
                    if line.startswith("model name"):
                        info["cpu"] = line.split(":", 1)[1].strip()
                        break
            with open("/proc/meminfo") as f:
                kb = int(f.readline().split()[1])
                info["ram_gb"] = round(kb / 2 ** 20)
        except (OSError, ValueError, IndexError):
            pass
        if shutil.which("nvidia-smi"):
            info["gpu"] = _run(["nvidia-smi", "--query-gpu=name,memory.total", "--format=csv,noheader"]) or None
    return info


def describe(info: dict) -> str:
    ram = f"{info['ram_gb']} GB" if info.get("ram_gb") else "? GB"
    gpu = f", {info['gpu']}" if info.get("gpu") else ""
    return f"{info['cpu']} ({info['cores']} cores), {ram} RAM{gpu}, {info['os']}"
