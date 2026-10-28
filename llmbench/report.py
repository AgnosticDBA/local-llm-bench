"""Turn results.json into a terminal table, report.md and a self-contained report.html (inline SVG, no JS)."""
from __future__ import annotations

import html
import json
from pathlib import Path


def _f(v, fmt="{:.0f}", none="–"):
    return none if v is None else fmt.format(v)


def rows(results: dict) -> list[dict]:
    out = []
    for r in results["runs"]:
        m, c, mem = r["metrics"], r["check"], r["memory"]
        kept = c.get("kept") or {}
        out.append({
            "model": r["model"] + (f" #{r['repeat']}" if results.get("repeats", 1) > 1 else ""),
            "wall": _f(m.get("wall_s"), "{:.0f} s"),
            "prefill": _f(m.get("prefill_tok_s"), "{:.0f}"),
            "gen": _f(m.get("gen_tok_s"), "{:.1f}"),
            "tokens": _f(m.get("gen_tokens")),
            "kept": " / ".join(f"{len(v)}" for v in kept.values()) or "–",
            "dropped": str(len(c.get("dropped") or [])) if c.get("parsed") else "–",
            "judgement": (lambda j: f"{j['found']}/{j['expected']} gaps" + (f", {len(j['wrong'])} wrong" if j['wrong'] else "")
                          if j and j.get("expected") else "–")(c.get("judgement")),
            "quality": "PASS" if c.get("passed") else ("ERROR" if m.get("error") else "FAIL"),
            "min_free": _f(mem.get("free_pct_min"), "{:.0f} %"),
            "swap": (f"{(mem.get('swapped_in_mb') or 0) / 1024:.1f} / {(mem.get('swapped_out_mb') or 0) / 1024:.1f} GB"
                     if mem.get("available") else "–"),
            "peak": _f(mem.get("peak_swap_mb_s") if mem.get("available") else None, "{:.0f} MB/s"),
            "machine": r.get("memory_verdict", "unknown"),
            "note": m.get("error") or c.get("reason") or "",
        })
    return out


COLS = [("model", "Model"), ("wall", "Wall"), ("prefill", "Prefill tok/s"), ("gen", "Gen tok/s"),
        ("tokens", "Tokens"), ("kept", "Kept"), ("dropped", "Dropped"), ("judgement", "Judgement"), ("quality", "Quality"),
        ("min_free", "Min free"), ("swap", "Swap in / out"), ("peak", "Peak swap"), ("machine", "Rest of machine")]


def table(results: dict) -> str:
    rs = rows(results)
    w = {k: max(len(h), *(len(r[k]) for r in rs)) for k, h in COLS} if rs else {}
    line = "  ".join(h.ljust(w[k]) for k, h in COLS)
    body = ["  ".join(r[k].ljust(w[k]) for k, _ in COLS) for r in rs]
    notes = [f"  {r['model']}: {r['note']}" for r in rs if r["note"]]
    return "\n".join([line, "-" * len(line), *body] + (["", "Notes:", *notes] if notes else []))


def markdown(results: dict) -> str:
    rs = rows(results)
    t = results.get("task", {})
    out = [f"# local-llm-bench: {t.get('name', '')}", "",
           "> **Private.** This report shows model names, paths, error text and the time of day. "
           "To post a result, run `llmbench share` and post `share.md` instead.", "",
           f"**Machine:** {results['machine_text']}  ", f"**Backend:** {results['backend']}"
           + (f" {results['backend_version']}" if results.get("backend_version") else "") + "  ",
           f"**Started:** {results['started']}", "",
           "| " + " | ".join(h for _, h in COLS) + " |", "|" + "---|" * len(COLS)]
    out += ["| " + " | ".join(r[k] for k, _ in COLS) + " |" for r in rs]
    notes = [f"- **{r['model']}**: {r['note']}" for r in rs if r["note"]]
    if notes:
        out += ["", "Notes:", *notes]
    out += ["", "*Kept* = items whose quotes were found word for word in the sources (per list, in task order). "
            "*Rest of machine*: swap moved in and out plus swap growth: comfortable < 1 GB; swapping 1–8 GB; "
            "thrashing > 8 GB or > 500 MB/s.", ""]
    return "\n".join(out)


# --- SVG ---------------------------------------------------------------------------------

def short(model: str, n: int = 34) -> str:
    """hf.co/org/Repo-GGUF:QUANT -> Repo-GGUF:QUANT, so chart labels fit."""
    name = model.rsplit("/", 1)[-1]
    return name if len(name) <= n else name[:n - 1] + "\u2026"


def status(r: dict) -> str:
    c = r["check"]
    if r["metrics"].get("error"):
        return "error"
    if c.get("passed"):
        return "passed"
    if not c.get("parsed"):
        return "no answer" + (" (hit token limit)" if r["metrics"].get("done_reason") == "length" else "")
    return "failed: " + (c.get("reason") or "check")


def svg_walls(results: dict) -> str:
    runs = results["runs"]
    if not runs:
        return ""
    W, lab, bh, gap = 860, 290, 26, 14
    vmax = max((r["metrics"].get("wall_s") or 0) for r in runs) or 1
    H = 20 + len(runs) * (bh + gap)
    out = [f'<svg viewBox="0 0 {W} {H}" role="img" aria-label="Wall time per run" class="chart">']
    for i, r in enumerate(runs):
        y = 10 + i * (bh + gap)
        wall = r["metrics"].get("wall_s") or 0
        w = (W - lab - 300) * wall / vmax
        ok = r["check"].get("passed")
        name = html.escape(short(r["model"]) + (f" #{r['repeat']}" if results.get("repeats", 1) > 1 else ""))
        gen = r["metrics"].get("gen_tok_s")
        out += [f'<text x="{lab - 10}" y="{y + bh * 0.68}" text-anchor="end" class="lbl">{name}</text>',
                f'<rect x="{lab}" y="{y}" width="{max(w, 1):.1f}" height="{bh}" rx="3" class="{"bar" if ok else "bar fail"}"/>',
                f'<text x="{lab + w + 8:.1f}" y="{y + bh * 0.45}" class="val">{wall:.0f} s</text>',
                f'<text x="{lab + w + 8:.1f}" y="{y + bh * 0.95}" class="sub">'
                f'{_f(gen, "{:.1f}")} tok/s · {html.escape(status(r))} · {html.escape(r.get("memory_verdict", ""))}</text>']
    out.append("</svg>")
    return "\n".join(out)


def svg_memory(run: dict) -> str:
    s = run.get("samples") or []
    if len(s) < 2:
        return "<p class='sub'>No memory samples on this platform.</p>"
    W, H, top, mid, bot = 760, 300, 20, 150, 280
    t0, t1 = s[0]["t"], s[-1]["t"]
    span = (t1 - t0) or 1
    X = lambda t: 50 + (W - 70) * (t - t0) / span
    pts = " ".join(f"{X(p['t']):.1f},{mid - (mid - top) * (p.get('free_pct') or 0) / 100:.1f}"
                   for p in s if p.get("free_pct") is not None)
    rates = []
    for a, b in zip(s, s[1:]):
        dt = (b["t"] - a["t"]) or 1
        moved = (b["swapin_bytes"] - a["swapin_bytes"]) + (b["swapout_bytes"] - a["swapout_bytes"])
        rates.append((a["t"], b["t"], max(moved, 0) / 2 ** 20 / dt))
    rmax = max(max((r for *_, r in rates), default=0), 100)   # floor: a few MB/s of noise must look small
    out = [f'<svg viewBox="0 0 {W} {H}" role="img" aria-label="Memory during the run" class="chart">',
           f'<rect x="{X(run["t_start"]):.1f}" y="{top}" width="{X(run["t_end"]) - X(run["t_start"]):.1f}" '
           f'height="{bot - top}" class="window"/>',
           f'<text x="44" y="{top + 4}" text-anchor="end" class="sub">100</text>',
           f'<text x="44" y="{mid + 4}" text-anchor="end" class="sub">0</text>',
           f'<line x1="50" x2="{W - 20}" y1="{mid}" y2="{mid}" class="axis"/>',
           f'<text x="54" y="{top + 14}" class="sub">free memory %</text>',
           f'<polyline points="{pts}" class="line"/>',
           f'<line x1="50" x2="{W - 20}" y1="{bot}" y2="{bot}" class="axis"/>',
           f'<text x="44" y="{mid + 34}" text-anchor="end" class="sub">{rmax:.0f}</text>',
           f'<text x="54" y="{mid + 34}" class="sub">swap traffic MB/s</text>']
    for ta, tb, r in rates:
        h = (bot - mid - 30) * r / rmax
        out.append(f'<rect x="{X(ta):.1f}" y="{bot - h:.1f}" width="{max(X(tb) - X(ta) - 1, 1):.1f}" '
                   f'height="{h:.1f}" class="swap"/>')
    out += [f'<text x="{X(run["t_start"]) + 4:.1f}" y="{bot - 4}" class="sub">request</text>',
            f'<text x="50" y="{H - 2}" class="sub">0 s</text>',
            f'<text x="{W - 20}" y="{H - 2}" text-anchor="end" class="sub">{span:.0f} s</text>', "</svg>"]
    return "\n".join(out)


CSS = """
:root{--bg:#fbfaf7;--fg:#1f1e1c;--muted:#6b6a65;--bar:#2b6fd6;--fail:#d9d7cf;--swap:#b9b6aa;--win:#f0eee8;--axis:#c9c6bd}
@media (prefers-color-scheme: dark){:root{--bg:#1b1b1a;--fg:#ecebe7;--muted:#a3a29c;--bar:#5d97f0;--fail:#45443f;--swap:#6d6b63;--win:#262624;--axis:#4a4944}}
body{background:var(--bg);color:var(--fg);font:15px/1.5 -apple-system,system-ui,sans-serif;max-width:900px;margin:0 auto;padding:24px 16px}
table{border-collapse:collapse;width:100%;font-size:13px;display:block;overflow-x:auto}
th,td{text-align:left;padding:6px 8px;border-bottom:1px solid var(--axis);white-space:nowrap}
.chart{width:100%;height:auto}.lbl{fill:var(--fg);font-size:12px}.val{fill:var(--fg);font-size:13px}
.sub{fill:var(--muted);font-size:11px;color:var(--muted)}.bar{fill:var(--bar)}.bar.fail{fill:var(--fail)}
.swap{fill:var(--swap)}.window{fill:var(--win)}.axis{stroke:var(--axis)}
.line{fill:none;stroke:var(--bar);stroke-width:2}.PASS{color:var(--bar);font-weight:600}
"""


def html_page(results: dict) -> str:
    rs = rows(results)
    head = "".join(f"<th>{h}</th>" for _, h in COLS)
    body = "".join("<tr>" + "".join(f'<td class="{html.escape(r[k])}">{html.escape(r[k])}</td>' for k, _ in COLS)
                   + "</tr>" for r in rs)
    mem = "".join(f"<h3>{html.escape(short(r['model'], 60))}" + (f" #{r['repeat']}" if results.get('repeats', 1) > 1 else "")
                  + f"</h3>{svg_memory(r)}" for r in results["runs"])
    t = results.get("task", {})
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>local-llm-bench report</title>
<style>{CSS}</style></head><body>
<h1>{html.escape(t.get('name', 'local-llm-bench'))}</h1>
<p><strong>Private.</strong> This report shows model names, paths, error text and the time of day. To post a result,
run <code>llmbench share</code> and post <code>share.md</code> instead.</p>
<p class="sub">{html.escape(results['machine_text'])} · {html.escape(results['backend'])} {html.escape(results.get('backend_version') or '')} · {html.escape(results['started'])}</p>
<h2>Wall time per run</h2><p class="sub">Faded bars failed the quality check: whatever their speed, their answers cannot be trusted.</p>
{svg_walls(results)}
<h2>Every run</h2><table><tr>{head}</tr>{body}</table>
<h2>Memory during each run</h2><p class="sub">Shaded band = the request. Line = free memory; bars = data moved to and from swap.</p>
{mem}
</body></html>"""


def write(run_dir: Path) -> None:
    results = json.loads((run_dir / "results.json").read_text(encoding="utf-8"))
    (run_dir / "report.md").write_text(markdown(results), encoding="utf-8")
    (run_dir / "report.html").write_text(html_page(results), encoding="utf-8")
