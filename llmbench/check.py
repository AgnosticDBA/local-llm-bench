"""The quality gate: is every quoted claim actually in the source text?

A model that writes fluent, confident output in half the time is worthless if it invents
the evidence. So each item the model returns must quote its sources word for word; an item
whose quote cannot be found is dropped, and a run that keeps too little fails.
"""
from __future__ import annotations

import json
import re

MIN_QUOTE = 12          # shorter "quotes" ("PostgreSQL") prove nothing
_TRANS = str.maketrans({"‘": "'", "’": "'", "“": '"', "”": '"',
                        "–": "-", "—": "-", " ": " ", "•": " "})


def norm(s: str) -> str:
    s = str(s).translate(_TRANS).lower()
    s = re.sub(r"[*_`#>]", " ", s)               # markdown emphasis and bullets
    s = re.sub(r"\s+", " ", s).strip()
    s = re.sub(r" %", "%", s)                     # "22 %" and "22%" are the same quote
    return s.strip(" .,;:-\"'")


def found(quote: str, source: str) -> tuple[bool, str]:
    """True if `quote` appears in `source`. A quote elided with '...' must match piece by piece, in order,
    with every piece at least MIN_QUOTE long and all of them in one paragraph or bullet of the source, so
    that a "quote" cannot be stitched together from scattered fragments."""
    q = norm(quote)
    if len(q) < MIN_QUOTE:
        return False, "quote too short"
    parts = [p.strip(" .,;:-") for p in re.split(r"[\[(]?(?:\.\.\.|…|\. \. \.)[\])]?", q)]
    parts = [p for p in parts if p]
    if len(parts) > 1 and any(len(p) < MIN_QUOTE for p in parts):
        return False, "elided piece too short"
    for block in blocks(source):
        src, pos = norm(block), 0
        for part in parts:
            i = src.find(part, pos)
            if i < 0:
                break
            pos = i + len(part)
        else:
            return True, ""
    return False, "not in source"


def blocks(source: str) -> list[str]:
    """Markdown blocks: a paragraph (hard-wrapped lines joined), one bullet, or one heading."""
    out, cur = [], []
    for line in str(source).splitlines():
        if not line.strip() or re.match(r"\s*([-*+]|\d+[.)]|#+)\s|\s*\|", line):
            if cur:
                out.append(" ".join(cur))
            cur = [line] if line.strip() else []
        else:
            cur.append(line)
    if cur:
        out.append(" ".join(cur))
    return out


def extract_json(text: str):
    """The answer may arrive wrapped in a <think> block, a ```json fence, or prose. Take the object."""
    text = re.sub(r"<think>.*?</think>", "", text or "", flags=re.S)
    fence = re.search(r"```(?:json)?\s*(\{.*\})\s*```", text, re.S)
    if fence:
        text = fence.group(1)
    start, end = text.find("{"), text.rfind("}")
    if start < 0 or end <= start:
        return None
    try:
        return json.loads(text[start:end + 1])
    except ValueError:
        return None


def verify(answer, sources: dict[str, str], rules: dict[str, str], gate: dict, judgement: dict | None = None) -> dict:
    """rules: {"strengths[].evidence": "cv", ...}: field of each list item -> source it must quote.
    judgement: optional keyword rules applied to the kept items (see judge)."""
    if not isinstance(answer, dict):
        return {"parsed": False, "passed": False, "kept": {}, "dropped": [], "reason": "no JSON object"}
    by_list: dict[str, list[tuple[str, str]]] = {}
    for path, src in rules.items():
        lst, field = path.split("[].")
        by_list.setdefault(lst, []).append((field, src))
    kept, dropped, seen = {}, [], {}
    for lst, fields in by_list.items():
        items = answer.get(lst) or []
        kept[lst] = []
        for item in items if isinstance(items, list) else []:
            why = ""
            for field, src in fields:
                ok, reason = found((item or {}).get(field, "") if isinstance(item, dict) else "", sources[src])
                if not ok:
                    why = f"{field} {reason}"
                    break
            key = tuple(norm(item.get(f, "")) for f, _ in fields) if isinstance(item, dict) else None
            if not why and key in seen.setdefault(lst, set()):
                why = "duplicate"
            if not why:
                seen[lst].add(key)
            if why:
                dropped.append({"list": lst, "item": item, "why": why})
            else:
                kept[lst].append(item)
    n_kept = sum(len(v) for v in kept.values())
    total = n_kept + len(dropped)
    ratio = n_kept / total if total else 0.0
    short = [k for k, need in gate.get("min_kept", {}).items() if len(kept.get(k, [])) < need]
    many = [k for k, cap in gate.get("max_kept", {}).items() if len(kept.get(k, [])) > cap]
    j = judge(kept, judgement or {})
    reason = (f"too few verified {', '.join(short)}" if short else
              f"too many {', '.join(many)} (listing everything is not an answer)" if many else
              f"only {n_kept} of {total} items verified" if ratio < gate.get("min_kept_ratio", 0.5) else
              f"found {j['found']} of {j['expected']} known gaps" if j["expected"] and j["found"] < gate.get("min_found", 0) else
              f"wrong: {'; '.join(j['wrong'])}" if len(j["wrong"]) > gate.get("max_wrong", 99) else "")
    return {"parsed": True, "passed": not reason, "kept": kept, "dropped": dropped,
            "kept_ratio": round(ratio, 2), "judgement": j, "reason": reason}


def judge(kept: dict, rules: dict) -> dict:
    """Faithful is not the same as right. Keyword rules say which items a sound answer must and must not
    contain, e.g. a gap the CV plainly covers, or a "strength" resting on a line that does not support it."""
    found = expected = 0
    wrong, missed = [], []
    for lst, r in rules.items():
        texts = [norm(i.get(r.get("field", "requirement"), "")) for i in kept.get(lst, []) if isinstance(i, dict)]
        for kw in r.get("must_include", []):
            expected += 1
            if any(norm(kw) in t for t in texts):
                found += 1
            else:
                missed.append(kw)
        wrong += [f"{kw} listed in {lst}" for kw in r.get("must_exclude", []) if any(norm(kw) in t for t in texts)]
    return {"found": found, "expected": expected, "missed": missed, "wrong": wrong}
