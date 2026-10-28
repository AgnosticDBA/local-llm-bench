"""Sample free memory and swap while a model runs (macOS and Linux; elsewhere nothing is recorded).

Why this exists: a model that "fits" can still push everything else you have open into swap.
Speed numbers alone will not show it; this timeline does.
"""
from __future__ import annotations

import os
import re
import subprocess
import sys
import threading
import time

MB = 2 ** 20


def _run(cmd: list[str]) -> str:
    try:
        return subprocess.run(cmd, capture_output=True, text=True, timeout=10).stdout
    except (OSError, subprocess.SubprocessError):
        return ""


# --- parsers (pure, so they can be tested with captured output) ---------------------------

def parse_vm_stat(text: str) -> dict:
    page = re.search(r"page size of (\d+) bytes", text)
    page = int(page.group(1)) if page else 4096

    def n(label: str) -> int:
        m = re.search(rf"^{re.escape(label)}:\s+(\d+)", text, re.M)
        return int(m.group(1)) if m else 0

    return {"swapin_bytes": n("Swapins") * page, "swapout_bytes": n("Swapouts") * page,
            "compressed_mb": n("Pages occupied by compressor") * page / MB}


def parse_swapusage(text: str) -> float | None:
    m = re.search(r"used = ([\d.]+)([MG])", text)
    if not m:
        return None
    return float(m.group(1)) * (1024 if m.group(2) == "G" else 1)


def parse_memory_pressure(text: str) -> float | None:
    m = re.search(r"free percentage: (\d+)%", text)
    return float(m.group(1)) if m else None


def parse_meminfo(text: str) -> dict:
    kb = {}
    for line in text.splitlines():
        k, _, v = line.partition(":")
        if v.split():
            kb[k] = int(v.split()[0])
    avail = kb.get("MemAvailable", kb.get("MemFree", 0))
    return {"free_pct": 100.0 * avail / kb["MemTotal"] if kb.get("MemTotal") else None,
            "swap_used_mb": (kb.get("SwapTotal", 0) - kb.get("SwapFree", 0)) / 1024}


def parse_vmstat(text: str, page: int) -> dict:
    v = dict(line.split()[:2] for line in text.splitlines() if len(line.split()) >= 2)
    return {"swapin_bytes": int(v.get("pswpin", 0)) * page,
            "swapout_bytes": int(v.get("pswpout", 0)) * page}


# --- readers -------------------------------------------------------------------------------

def read() -> dict | None:
    if sys.platform == "darwin":
        s = parse_vm_stat(_run(["vm_stat"]))
        s["swap_used_mb"] = parse_swapusage(_run(["sysctl", "-n", "vm.swapusage"]))
        s["free_pct"] = parse_memory_pressure(_run(["memory_pressure"]))
        return s
    if sys.platform.startswith("linux"):
        try:
            with open("/proc/meminfo") as f:
                s = parse_meminfo(f.read())
            with open("/proc/vmstat") as f:
                s.update(parse_vmstat(f.read(), os.sysconf("SC_PAGE_SIZE")))
            s["compressed_mb"] = None
            return s
        except OSError:
            return None
    return None


class Sampler(threading.Thread):
    """Samples every `interval` s. If swap grows more than `max_swap_growth_mb` above where it
    started, sets `tripped`, so the run can be stopped before the machine becomes unusable."""

    def __init__(self, interval: float = 2.0, max_swap_growth_mb: float | None = None):
        super().__init__(daemon=True)
        self.interval, self.limit = interval, max_swap_growth_mb
        self.samples: list[dict] = []
        self.tripped = threading.Event()
        self.trip_reason = ""
        self._halt = threading.Event()

    def run(self) -> None:
        while not self._halt.is_set():
            s = read()
            if s:
                s["t"] = time.time()
                self.samples.append(s)
                base = self.samples[0].get("swap_used_mb")
                if (self.limit and base is not None and s.get("swap_used_mb") is not None
                        and s["swap_used_mb"] - base > self.limit and not self.tripped.is_set()):
                    self.trip_reason = (f"swap grew {s['swap_used_mb'] - base:.0f} MB "
                                        f"(limit {self.limit:.0f} MB)")
                    self.tripped.set()
            self._halt.wait(self.interval)

    def stop(self) -> None:
        self._halt.set()
        self.join(timeout=15)


def summarise(samples: list[dict], t_start: float, t_end: float) -> dict:
    """Memory figures for the window [t_start, t_end] (the request itself, not the idle edges)."""
    win = [s for s in samples if t_start <= s["t"] <= t_end]
    if not samples:
        return {"available": False}
    before = [s for s in samples if s["t"] < t_start] or samples[:1]
    after = [s for s in samples if s["t"] > t_end]
    first, last = before[-1], (win or before)[-1]
    frees = [s["free_pct"] for s in win if s.get("free_pct") is not None]
    swaps = [s["swap_used_mb"] for s in win if s.get("swap_used_mb") is not None]
    peak_rate = 0.0
    for a, b in zip(samples, samples[1:]):
        if b["t"] < t_start or a["t"] > t_end or b["t"] <= a["t"]:
            continue
        moved = max(0, b["swapin_bytes"] - a["swapin_bytes"]) + max(0, b["swapout_bytes"] - a["swapout_bytes"])
        peak_rate = max(peak_rate, moved / MB / (b["t"] - a["t"]))
    return {
        "available": True,
        "free_pct_before": first.get("free_pct"),
        "free_pct_min": min(frees) if frees else None,
        "free_pct_after": after[-1].get("free_pct") if after else None,
        "swap_used_mb_before": first.get("swap_used_mb"),
        "swap_used_mb_peak": max(swaps) if swaps else None,
        "swapped_in_mb": max(0, last["swapin_bytes"] - first["swapin_bytes"]) / MB,   # counters can reset
        "swapped_out_mb": max(0, last["swapout_bytes"] - first["swapout_bytes"]) / MB,
        "peak_swap_mb_s": peak_rate,
    }


def verdict(mem: dict) -> str:
    """One word on how the rest of the machine fared. Thresholds are judgement calls, stated in the README."""
    if not mem.get("available"):
        return "unknown"
    moved = (mem.get("swapped_in_mb") or 0) + (mem.get("swapped_out_mb") or 0)
    grew = (mem.get("swap_used_mb_peak") or 0) - (mem.get("swap_used_mb_before") or 0)
    if moved > 8 * 1024 or grew > 8 * 1024 or (mem.get("peak_swap_mb_s") or 0) > 500:
        return "thrashing"
    if moved > 1024 or grew > 1024:
        return "swapping"
    return "comfortable"
