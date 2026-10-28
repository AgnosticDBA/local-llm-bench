"""llmbench: will this model run on my machine, and can I trust what it says?"""
from __future__ import annotations

import argparse
import dataclasses
import json
import re
import sys
import threading
import time
from pathlib import Path

from . import __version__, backends, check, memory, report, share, sysinfo

TASKS = Path(__file__).parent / "tasks"


def load_task(name: str) -> dict:
    d = Path(name) if Path(name).is_dir() else TASKS / name
    if not (d / "task.json").exists():
        sys.exit(f"no task at {d} (built in: {', '.join(p.name for p in TASKS.iterdir() if p.is_dir())})")
    t = json.loads((d / "task.json").read_text(encoding="utf-8"))
    t["fingerprint"] = share.fingerprint(str(d))
    builtin = d.resolve().parent == TASKS.resolve() and share.BUILTIN.get(d.name) == t["fingerprint"]
    if d.resolve().parent == TASKS.resolve() and not builtin:
        print(f"note: {d.name} is not the task this version shipped with, so it counts as a custom task", flush=True)
    t["dir"] = f"built-in:{d.name}" if builtin else str(d)   # no home paths in shared results
    t["source_text"] = {k: (d / f).read_text(encoding="utf-8") for k, f in t["sources"].items()}
    return t


def messages(task: dict) -> list[dict]:
    user = task["user"]
    for k, v in task["source_text"].items():
        user = user.replace("{" + k + "}", v)
    return [{"role": "system", "content": task["system"]}, {"role": "user", "content": user}]


def fit_estimate(model_bytes, ram_gb, free_pct, apple: bool) -> dict | None:
    """Rough: weights + ~15 % for KV cache and runtime + 1.5 GB, against what is free right now."""
    if not (model_bytes and ram_gb) or free_pct is None:
        return None
    need = model_bytes / 2 ** 30 * 1.15 + 1.5
    in_use = ram_gb * (100 - free_pct) / 100
    headroom = ram_gb - in_use - need
    if apple and need > ram_gb * 0.75:
        word = "too big for the GPU"   # macOS lets the GPU wire about 75 % of RAM by default
    else:
        word = "fits" if headroom > 4 else "tight" if headroom > 0 else "will swap"
    return {"need_gb": round(need, 1), "in_use_gb": round(in_use, 1), "headroom_gb": round(headroom, 1),
            "verdict": word}


def parse_opts(pairs: list[str]) -> dict:
    out = {}
    for p in pairs:
        k, _, v = p.partition("=")
        try:
            out[k] = json.loads(v)
        except ValueError:
            out[k] = v
    return out


def one_run(be, model: str, rep: int, task: dict, a, info: dict) -> dict:
    be.unload(model)                                     # cold start: no warm weights, no cached prompt
    now = memory.read()
    est = fit_estimate(be.model_bytes(model), info.get("ram_gb"), now and now.get("free_pct"),
                       apple=info.get("gpu", "") == "Apple GPU (unified memory)")
    if est:
        print(f"  preflight: needs ~{est['need_gb']} GB, other apps use ~{est['in_use_gb']} GB now "
              f"-> {est['verdict']} (headroom {est['headroom_gb']} GB)", flush=True)
    sampler = memory.Sampler(a.interval, a.max_swap_gb * 1024 if a.max_swap_gb else None)
    sampler.start()
    time.sleep(a.idle)

    stop, done = threading.Event(), threading.Event()

    def watch():
        while not done.is_set():
            if sampler.tripped.wait(1):
                print(f"  WATCHDOG: {sampler.trip_reason}; stopping", flush=True)
                stop.set()
                be.unload(model)
                return
    threading.Thread(target=watch, daemon=True).start()

    opts = {**task.get("options", {}), **({"num_ctx": a.num_ctx} if a.num_ctx else {}), **parse_opts(a.option)}
    t_start = time.time()
    try:
        res = be.chat(model, messages(task), opts, a.timeout, stop)
        t_end = time.time()
        done.set()
        be.unload(model)
        time.sleep(a.idle)                               # show the machine recovering
    finally:                                             # Ctrl-C or a crash must not leave the model loaded
        done.set()
        sampler.stop()
        if sys.exc_info()[0]:
            be.unload(model)

    if stop.is_set():
        res.error = f"stopped: {sampler.trip_reason}"
    answer = check.extract_json(res.content) or check.extract_json(res.thinking)
    chk = (check.verify(answer, task["source_text"], task["checks"], task.get("gate", {}), task.get("judgement"))
           if not res.error else {"parsed": False, "passed": False, "kept": {}, "dropped": [], "reason": res.error})
    mem = memory.summarise(sampler.samples, t_start, t_end)
    metrics = {k: v for k, v in dataclasses.asdict(res).items() if k not in ("content", "thinking")}
    metrics.update(thinking_chars=len(res.thinking), content_chars=len(res.content))
    return {"model": model, "repeat": rep, "metrics": metrics, "check": chk, "memory": mem,
            "memory_verdict": memory.verdict(mem), "fit_estimate": est, "answer": answer,
            "raw_head": res.content[:2000], "t_start": t_start, "t_end": t_end, "samples": sampler.samples}


def failed_run(model: str, rep: int, why: str) -> dict:
    return {"model": model, "repeat": rep, "metrics": {"wall_s": 0, "error": why},
            "check": {"parsed": False, "passed": False, "kept": {}, "dropped": [], "reason": why},
            "memory": {"available": False}, "memory_verdict": "unknown", "fit_estimate": None, "answer": None,
            "raw_head": "", "t_start": 0, "t_end": 0, "samples": []}


def cmd_run(a) -> None:
    task = load_task(a.task)
    be = backends.make(a.backend, a.url)
    info = sysinfo.collect()
    started = time.strftime("%Y-%m-%d %H:%M:%S %Z")
    Path(a.out).mkdir(parents=True, exist_ok=True)
    stamp, n = time.strftime("%Y%m%d-%H%M%S"), 1
    while True:
        out = Path(a.out) / (stamp if n == 1 else f"{stamp}-{n}")
        try:
            out.mkdir()
            break
        except FileExistsError:
            n += 1
    (out / ".gitignore").write_text(                     # runs hold model output: keep them out of any repo
        "# written by llmbench: this run holds model output, keep it out of git\n*\n", encoding="utf-8")
    results = {"tool_version": __version__, "started": started, "machine": info,
               "machine_text": sysinfo.describe(info), "backend": be.kind, "backend_version": be.version(),
               "task": {"name": task["name"], "description": task.get("description", ""), "dir": task["dir"],
                        "fingerprint": task["fingerprint"]},
               "repeats": a.repeat, "runs": []}
    print(f"machine: {results['machine_text']}\nbackend: {be.kind} {results['backend_version'] or ''} at {be.url}\n"
          f"task:    {task['name']}\nresults: {out}\n", flush=True)
    interrupted = False
    for model in a.model:
        if interrupted:
            break
        for rep in range(1, a.repeat + 1):
            print(f"> {model}" + (f"  (run {rep} of {a.repeat})" if a.repeat > 1 else ""), flush=True)
            try:
                r = one_run(be, model, rep, task, a, info)
            except KeyboardInterrupt:
                print("\ninterrupted: writing the report for the runs that finished", flush=True)
                interrupted = True
                break
            except Exception as e:                       # one bad run must not cost the others
                r = failed_run(model, rep, f"crashed: {type(e).__name__}: {e}")
            results["runs"].append(r)
            (out / "results.json").write_text(json.dumps(results, indent=1, default=str), encoding="utf-8")
            m, c = r["metrics"], r["check"]
            print(f"  {m['wall_s']:.0f} s, {m.get('gen_tok_s') or 0:.1f} tok/s, "
                  f"{'PASS' if c['passed'] else 'FAIL'}{' (' + c['reason'] + ')' if c.get('reason') else ''}, "
                  f"machine {r['memory_verdict']}\n", flush=True)
    if not results["runs"]:
        sys.exit(130 if interrupted else "no runs finished")
    report.write(out)
    print(report.table(results))
    print(f"\nreport: {out / 'report.html'}\n        {out / 'report.md'}\n"
          "These reports are private, like results.json. To post a result, run: llmbench share")
    if interrupted:
        sys.exit(130)


def cmd_share(a) -> None:
    if a.verify:
        try:
            if Path(a.verify).stat().st_size > 1_000_000:
                sys.exit(f"{a.verify} is far larger than any share file")
            bad = share.verify_text(Path(a.verify).read_text(encoding="utf-8"))
        except (OSError, ValueError, RecursionError, AttributeError) as e:
            sys.exit(f"cannot read {a.verify} as a share file: {e}")
        print("ok: only expected fields" if not bad else "UNEXPECTED fields:\n  " + "\n  ".join(bad))
        sys.exit(1 if bad else 0)
    run_dir = Path(a.run_dir) if a.run_dir else max(Path("runs").glob("*/results.json"), key=lambda p: p.stat().st_mtime, default=Path()).parent
    if not (run_dir / "results.json").exists():
        sys.exit(f"no results.json in {run_dir}")
    try:
        md = share.markdown(share.summary(json.loads((run_dir / "results.json").read_text(encoding="utf-8")),
                                          a.include_custom_task))
    except ValueError as e:
        sys.exit(f"cannot read {run_dir / 'results.json'}: {e}")
    except share.Refused as e:
        sys.exit(f"not shared: {e}")
    (run_dir / "share.md").write_text(md, encoding="utf-8")
    print(md)
    print("Written to share.md in the run folder. Above is everything in it: read it before you post it, and\n"
          "post the file's contents, not this terminal output. Check the model names in particular; a private\n"
          "fine-tune's name is the one thing this cannot judge.", file=sys.stderr)


def main(argv=None) -> None:
    p = argparse.ArgumentParser(prog="llmbench", description=__doc__)
    p.add_argument("--version", action="version", version=__version__)
    sub = p.add_subparsers(dest="cmd", required=True)

    r = sub.add_parser("run", help="benchmark one or more models on a task")
    r.add_argument("-m", "--model", action="append", required=True, help="model name; repeat for several")
    r.add_argument("-t", "--task", default="gap-analysis", help="built-in task name or a task directory")
    r.add_argument("--backend", default="ollama", choices=["ollama", "openai"])
    r.add_argument("--url", help="server URL (ollama default http://127.0.0.1:11434, openai .../v1)")
    r.add_argument("--repeat", type=int, default=1, help="runs per model (each one cold)")
    r.add_argument("--num-ctx", type=int, help="context window override")
    r.add_argument("-o", "--option", action="append", default=[], help="model option key=value, e.g. temperature=0")
    r.add_argument("--max-swap-gb", type=float, default=16, help="stop a run if swap grows by more (0 = never)")
    r.add_argument("--idle", type=float, default=10, help="seconds of idle sampling before and after each run")
    r.add_argument("--interval", type=float, default=2, help="memory sample interval, seconds")
    r.add_argument("--timeout", type=float, default=3600, help="per-request timeout, seconds")
    r.add_argument("--out", default="runs", help="where run folders go")
    r.set_defaults(fn=cmd_run)

    s = sub.add_parser("report", help="re-render report.md/report.html from a run folder")
    s.add_argument("run_dir")
    s.set_defaults(fn=lambda a: (report.write(Path(a.run_dir)),
                                 print(report.table(json.loads((Path(a.run_dir) / "results.json").read_text(encoding="utf-8")))),
                                 print("\nPrivate, like results.json. To post a result, run: llmbench share")))

    sh = sub.add_parser("share", help="write share.md: a run's numbers with nothing private, ready to post")
    sh.add_argument("run_dir", nargs="?", help="a run folder (default: the newest under runs/)")
    sh.add_argument("--include-custom-task", action="store_true",
                    help="allow a custom-task run; only a fingerprint of the task goes out")
    sh.add_argument("--verify", metavar="FILE", help="check a share file someone sent you for unexpected fields")
    sh.set_defaults(fn=cmd_share)

    i = sub.add_parser("sysinfo", help="show what the tool sees: machine and memory right now")
    i.set_defaults(fn=lambda a: print(sysinfo.describe(sysinfo.collect()), "\n", json.dumps(memory.read(), indent=1)))

    t = sub.add_parser("tasks", help="list built-in tasks")
    t.set_defaults(fn=lambda a: [print(f"{d.name:16} {json.loads((d / 'task.json').read_text(encoding='utf-8')).get('description', '')}")
                                 for d in sorted(TASKS.iterdir()) if (d / "task.json").exists()])

    a = p.parse_args(argv)
    a.fn(a)
