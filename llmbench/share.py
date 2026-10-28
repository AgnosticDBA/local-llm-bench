"""Make a run safe to post in public.

An allow-list, not a block-list: a field reaches the share file only if it is named here. Nothing the
model wrote, no source text, no file paths, no memory timeline, no time of day. A run on a custom task is
refused unless asked for explicitly, because a custom task's name, keywords and quotes can all be private;
even then only a fingerprint of the task files goes out, never their content or name.
"""
from __future__ import annotations

import hashlib
import json
import math
import re
from pathlib import Path

SCHEMA_VERSION = 1
MACHINE = ("cpu", "cores", "ram_gb", "gpu", "arch")
METRICS = ("wall_s", "ttft_s", "load_s", "prompt_tokens", "prefill_tok_s", "gen_tokens", "gen_tok_s", "done_reason")
MEMORY = ("free_pct_before", "free_pct_min", "free_pct_after", "swap_used_mb_before", "swap_used_mb_peak",
          "swapped_in_mb", "swapped_out_mb", "peak_swap_mb_s")
DONE_REASONS = ("stop", "length", "load", "other", None)
# sha256 of each shipped task folder. A task folder of the same name with other content is a custom task:
# an edited copy of a built-in can carry private text just as well as a new one.
BUILTIN = {"gap-analysis": "c99600b5b8d9ab0b61cd9745062de242f72a896cdb06afb9a2e7c2b8c3144045"}


class Refused(Exception):
    pass


def _num(v):
    return v is None or (isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v))


def _int(v):
    return v is None or (isinstance(v, int) and not isinstance(v, bool))


def _bool(v):
    return isinstance(v, bool)


def _text(pattern):
    rx = re.compile(pattern)
    return lambda v: v is None or (isinstance(v, str) and rx.fullmatch(v) is not None)


def _enum(*vals):
    return lambda v: v in vals


def _kept(v):
    return (_int(v) and v is not None) or (isinstance(v, dict) and all(re.fullmatch(r"[a-z_]{1,20}", str(k)) and _int(n)
                                                   for k, n in v.items()))


SAFE = r"[\w .,()+-]{0,64}(?: @ \d+(?:\.\d+)?GHz)?"         # hardware names: "Intel(R) Core(TM) i7-1360P", "8P+2E"
VERSION = r"[\w.+-]{1,24}"
# Every field a share file may hold, and what its value must look like. `summary` writes only these and
# `unexpected` reports anything else, so the two cannot drift apart.
FIELDS = {
    "": {"llmbench_share": _enum(SCHEMA_VERSION), "tool_version": _text(VERSION), "date": _text(r"\d{4}-\d{2}-\d{2}"),
         "backend": _enum("ollama", "openai", "other"), "backend_version": _text(VERSION)},
    "machine": {"cpu": _text(SAFE), "cores": lambda v: _int(v) or _text(r"\d+P\+\d+E|\d+")(v), "ram_gb": _num, "gpu": _text(SAFE), "arch": _text(SAFE),
                "os": _text(r"\w+ [\d.]+|unknown")},
    "task": {"name": _text(r"[\w-]{1,40}"), "builtin": _bool, "fingerprint": _text(r"[0-9a-f]{12}")},
    "run": {"model": _text(r"[\w.:/+@-]{1,120}"), "repeat": _int,
            "memory_verdict": _enum("comfortable", "swapping", "thrashing", "unknown"),
            "preflight": _enum("fits", "tight", "will swap", "too big for the GPU", None)},
    "metrics": {**{k: _num for k in METRICS if k != "done_reason"}, "done_reason": _enum(*DONE_REASONS),
                "error": _bool},
    "check": {"parsed": _bool, "passed": _bool, "kept": _kept, "dropped": _int, "gaps_found": _int,
              "gaps_expected": _int, "wrong": _int},
    "memory": {k: _num for k in MEMORY},
}
SECTIONS = {"": None, "machine": "machine", "task": "task"}


def _r(v):
    return round(v, 1) if isinstance(v, float) else v


def _keep(sect: str, key: str, v, default=None):
    """The value if it has the shape its field allows, else the default: odd input never passes through."""
    v = _r(v)
    return v if FIELDS[sect][key](v) else default


def os_major(s: str) -> str:
    """'macOS 26.6.2' -> 'macOS 26'; 'Linux 6.8.0-45-generic' -> 'Linux 6.8'."""
    m = re.match(r"(\w+) (\d+)(?:\.(\d+))?", s if isinstance(s, str) else "")
    if not m:
        return "unknown"
    return f"{m.group(1)} {m.group(2)}" + (f".{m.group(3)}" if m.group(1) == "Linux" and m.group(3) else "")


# 'qwen3:14b', 'library/qwen3', 'org/repo:tag', 'hf.co/org/repo:Q4_K_M': a registry name, not a location.
# LM Studio adds '@q4_k_m', Ollama digests '@sha256:...'.
REGISTRY = re.compile(r"(?:(?:hf\.co|huggingface\.co)/)?(?:[\w-]+/)?[\w-][\w.-]*(?:@(?:i?q\d\w*|b?f16|fp\d+|int\d+|\d+bit|sha256))?(?::[\w.-]+)?", re.I)
MODEL_FILE = re.compile(r"\.(gguf|safetensors|bin|pt|pth|onnx|mlx|npz)$", re.I)
HOSTLIKE = re.compile(r"(\d{1,3}\.){3}\d{1,3}\b|[\w-]+(\.[\w-]+)*\.(lan|local|localdomain|home|arpa|internal|corp)\b", re.I)


def model_name(name) -> str:
    """Keep a model's public name, drop where it lives. A file path ('/home/me/x.gguf', 'C:\\m\\x.gguf',
    'models/me/x.gguf') keeps its file name; a URL keeps its last part, without any user:password@.
    Registry names such as 'qwen3:14b' or 'hf.co/org/repo:Q4_K_M' pass unchanged."""
    name = name if isinstance(name, str) else ""
    if "://" in name:                                    # a URL: only a path after the host can be a name
        rest = name.split("://", 1)[1].split("/", 1)
        name = rest[1].rstrip("/").rsplit("/", 1)[-1] if len(rest) > 1 else ""
    if (MODEL_FILE.search(name) or not REGISTRY.fullmatch(name)):   # path-like: keep only the last part
        name = re.split(r"[\\/]", name)[-1]
    if HOSTLIKE.search(name) or ("@" in name and not REGISTRY.fullmatch(name)):   # user@host, not a quant
        return "withheld"
    return name if FIELDS["run"]["model"](name) and name else "withheld"


def fingerprint(task_dir: str) -> str:
    """sha256 over every file in a task folder (subfolders too, hidden files skipped)."""
    d = Path(task_dir)
    if not d.is_dir():
        return "unknown"
    h = hashlib.sha256()
    for f in sorted(p for p in d.rglob("*") if p.is_file()
                    and not any(part.startswith(".") or part == "__pycache__" for part in p.relative_to(d).parts)):
        data = f.read_bytes().replace(b"\r\n", b"\n")      # a Windows checkout is the same task
        h.update(f.relative_to(d).as_posix().encode() + b"\0" + data + b"\0")
    return h.hexdigest()


def is_builtin(task: dict) -> bool:
    name = task.get("name")
    return (task.get("dir") == f"built-in:{name}" and name in BUILTIN
            and task.get("fingerprint") == BUILTIN[name])


def summary(results: dict, include_custom: bool = False) -> dict:
    if not isinstance(results, dict):
        raise Refused("not a results.json from llmbench")
    task = results.get("task") if isinstance(results.get("task"), dict) else {}
    builtin = is_builtin(task)
    if not builtin and not include_custom:
        raise Refused("this run used a custom task (or a changed copy of a built-in one), whose name, keywords "
                      "and quotes may be private. Re-run with --include-custom-task to share its numbers with only "
                      "a fingerprint of the task.")
    mach = results.get("machine") if isinstance(results.get("machine"), dict) else {}
    fp = (task.get("fingerprint") if isinstance(task.get("fingerprint"), str) else
          fingerprint(task["dir"]) if isinstance(task.get("dir"), str) else "unknown")
    out = {
        "llmbench_share": SCHEMA_VERSION,
        "tool_version": _keep("", "tool_version", results.get("tool_version")),
        "date": _keep("", "date", str(results.get("started", ""))[:10]),
        "machine": {**{k: _keep("machine", k, mach.get(k)) for k in MACHINE}, "os": os_major(mach.get("os"))},
        "backend": _keep("", "backend", results.get("backend"), "other"),
        "backend_version": _keep("", "backend_version", results.get("backend_version")),
        "task": ({"name": task["name"], "builtin": True} if builtin else
                 {"name": "custom", "builtin": False, "fingerprint": _keep("task", "fingerprint", fp[:12])}),
        "runs": [],
    }
    for r in results.get("runs") or []:
        if not isinstance(r, dict):
            continue
        m, c, mem = (r.get(k) if isinstance(r.get(k), dict) else {} for k in ("metrics", "check", "memory"))
        j = c.get("judgement") if isinstance(c.get("judgement"), dict) else {}
        kept = c.get("kept") if isinstance(c.get("kept"), dict) else {}
        n = {k: len(v) for k, v in kept.items() if isinstance(v, list)}
        out["runs"].append({
            "model": model_name(r.get("model")),
            "repeat": _keep("run", "repeat", r.get("repeat")),
            "metrics": {**{k: _keep("metrics", k, m.get(k)) for k in METRICS if k != "done_reason"},
                        "done_reason": m.get("done_reason") if m.get("done_reason") in DONE_REASONS else "other",
                        "error": bool(m.get("error"))},
            "check": {"parsed": bool(c.get("parsed")), "passed": bool(c.get("passed")),
                      "kept": _keep("check", "kept", n, sum(n.values())) if builtin else sum(n.values()),
                      "dropped": len(c.get("dropped")) if isinstance(c.get("dropped"), list) else 0,
                      "gaps_found": _keep("check", "gaps_found", j.get("found")),
                      "gaps_expected": _keep("check", "gaps_expected", j.get("expected")),
                      "wrong": len(j.get("wrong")) if isinstance(j.get("wrong"), list) else 0},
            "memory": {k: _keep("memory", k, mem.get(k)) for k in MEMORY} if mem.get("available") else None,
            "memory_verdict": _keep("run", "memory_verdict", r.get("memory_verdict"), "unknown"),
            "preflight": _keep("run", "preflight", (r.get("fit_estimate") or {}).get("verdict")
                               if isinstance(r.get("fit_estimate"), dict) else None),
        })
    return out


def unexpected(shared) -> list[str]:
    """For whoever receives a share file: every field `summary` would not have written, and every value
    that does not have the shape its field allows. Empty means the file has the expected shape (it does
    not prove the numbers are honest)."""
    if not isinstance(shared, dict):
        return ["(the file is not a JSON object)"]
    bad = []

    def check(sect, d, where, extra=()):
        if d is None and sect == "memory":
            return
        if not isinstance(d, dict):
            bad.append(f"{where} (not an object)")
            return
        for k, v in d.items():
            if k in extra:
                continue
            if k not in FIELDS[sect]:
                bad.append(f"{where}.{k}".lstrip("."))
            elif not FIELDS[sect][k](v):
                bad.append(f"{where}.{k} = {json.dumps(v)[:60]}".lstrip("."))

    check("", shared, "", extra=("machine", "task", "runs"))
    check("machine", shared.get("machine"), "machine")
    check("task", shared.get("task"), "task")
    task = shared.get("task") if isinstance(shared.get("task"), dict) else {}
    if task.get("builtin") is True and (task.get("name") not in BUILTIN or "fingerprint" in task):
        bad.append("task (a built-in task must be one this version ships, with no fingerprint)")
    if task.get("builtin") is False and (task.get("name") != "custom" or "fingerprint" not in task):
        bad.append("task (a custom task must be named 'custom' and carry a fingerprint)")
    runs = shared.get("runs")
    if not isinstance(runs, list):
        bad.append("runs (not a list)")
        runs = []
    for i, r in enumerate(runs):
        check("run", r, f"runs[{i}]", extra=("metrics", "check", "memory"))
        if isinstance(r, dict):
            for sect in ("metrics", "check", "memory"):
                check(sect, r.get(sect), f"runs[{i}].{sect}")
    return bad


def verify_text(text: str) -> list[str]:
    """Check a whole share.md as received: its JSON block must have the expected shape, contain no
    duplicate keys, and the file must be exactly what `markdown` renders from that block, so that
    nothing can ride along in the header, the table or around them."""
    text = text.lstrip("\ufeff").replace("\r\n", "\n").replace("\r", "\n")    # Notepad, old Macs
    start, end = text.find("```json"), text.rfind("```")
    if not 0 <= start < end:
        return ["(no ```json block: a share file is the whole share.md)"]
    raw = text[start + 7:end]

    def no_dupes(pairs):
        keys = [k for k, _ in pairs]
        if len(keys) != len(set(keys)):
            raise ValueError(f"duplicate key {next(k for k in keys if keys.count(k) > 1)!r}")
        return dict(pairs)
    shared = json.loads(raw, object_pairs_hook=no_dupes)
    bad = unexpected(shared)
    if not bad:
        try:
            same = markdown(shared).strip("\n ") == text.strip("\n ")
        except (KeyError, TypeError, ValueError, AttributeError):
            same = False
        if not same:
            bad.append("(text outside the JSON block differs from what llmbench share writes)")
    return bad


def markdown(shared: dict) -> str:
    mach = shared["machine"]
    lines = [f"**llmbench {shared['tool_version']}** · {shared['date']} · {mach['cpu']} ({mach['cores']} cores), "
             f"{mach['ram_gb']} GB, {mach['os']} · {shared['backend']} {shared.get('backend_version') or ''} · "
             f"task `{shared['task']['name']}`", "",
             "| Model | Wall | Gen tok/s | Quality | Kept / dropped | Gaps found | Min free | Swap in / out | Peak swap | Rest of machine |",
             "|---|---|---|---|---|---|---|---|---|---|"]
    for r in shared["runs"]:
        m, c, mem = r["metrics"], r["check"], r["memory"] or {}
        kept = c["kept"] if isinstance(c["kept"], int) else sum(c["kept"].values())
        lines.append(
            f"| {r['model']} | {m.get('wall_s') if m.get('wall_s') is not None else '–'} s | {m.get('gen_tok_s') or '–'} | "
            f"{'PASS' if c['passed'] else 'FAIL'} | {kept} / {c['dropped']} | "
            f"{c['gaps_found'] if c['gaps_expected'] else '–'}{'/' + str(c['gaps_expected']) if c['gaps_expected'] else ''} | "
            f"{mem.get('free_pct_min') if mem.get('free_pct_min') is not None else '–'} % | {round((mem.get('swapped_in_mb') or 0) / 1024, 1)} / {round((mem.get('swapped_out_mb') or 0) / 1024, 1)} GB | "
            f"{mem.get('peak_swap_mb_s') if mem.get('peak_swap_mb_s') is not None else '–'} MB/s | "
            f"{r['memory_verdict']} |")
    return "\n".join(lines + ["", "```json", json.dumps(shared, indent=1), "```", ""])
