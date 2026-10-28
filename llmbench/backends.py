"""Model servers: Ollama's native API, and any OpenAI-compatible server
(llama.cpp's llama-server, LM Studio, vLLM, mlx_lm.server, ...).

Both stream, so a run can be stopped between chunks and time-to-first-token is real.
"""
from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from dataclasses import dataclass


@dataclass
class Result:
    content: str = ""
    thinking: str = ""
    wall_s: float = 0.0
    ttft_s: float | None = None        # first token of any kind (thinking or answer)
    load_s: float | None = None        # model load, when the server reports it
    prompt_tokens: int | None = None
    prefill_tok_s: float | None = None
    gen_tokens: int | None = None
    gen_tok_s: float | None = None
    done_reason: str | None = None
    error: str | None = None


def _post(url: str, body: dict, timeout: float):
    req = urllib.request.Request(url, data=json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json"})
    return urllib.request.urlopen(req, timeout=timeout)


def _http_error(e: Exception) -> str:
    if isinstance(e, urllib.error.HTTPError):
        try:
            return f"HTTP {e.code}: {e.read().decode(errors='replace')[:300]}"
        except OSError:
            return f"HTTP {e.code}"
    return f"{type(e).__name__}: {e}"


class Ollama:
    kind = "ollama"

    def __init__(self, url: str = "http://127.0.0.1:11434"):
        self.url = url.rstrip("/")

    def version(self) -> str | None:
        try:
            with urllib.request.urlopen(self.url + "/api/version", timeout=5) as r:
                return json.load(r).get("version")
        except (OSError, ValueError):
            return None

    def has_model(self, model: str) -> bool | None:
        """True or False if the server lists its models, None if it could not be asked."""
        try:
            with urllib.request.urlopen(self.url + "/api/tags", timeout=10) as r:
                names = {n for m in json.load(r).get("models", []) for n in (m.get("name"), m.get("model")) if n}
        except (OSError, ValueError, AttributeError):
            return None
        return model in names or f"{model}:latest" in names

    def model_bytes(self, model: str) -> int | None:
        """Size on disk: the best cheap guess at how much memory the weights will take."""
        try:
            with urllib.request.urlopen(self.url + "/api/tags", timeout=10) as r:
                for m in json.load(r).get("models", []):
                    if model in (m.get("name"), m.get("model")):
                        return m.get("size")
        except (OSError, ValueError):
            pass
        return None

    def unload(self, model: str) -> None:
        """Evict the model, so the next run loads cold and cannot reuse a cached prompt."""
        try:
            _post(self.url + "/api/generate", {"model": model, "keep_alive": 0}, 60).close()
        except OSError:
            pass

    def chat(self, model, messages, options, timeout, stop) -> Result:
        opts = dict(options)
        body = {"model": model, "messages": messages, "stream": True, "keep_alive": "5m"}
        if "think" in opts:
            body["think"] = opts.pop("think")
        body["options"] = opts
        res, t0, finished = Result(), time.time(), False
        try:
            with _post(self.url + "/api/chat", body, timeout) as r:
                for line in r:
                    if stop.is_set():
                        res.error = "stopped by the memory watchdog"
                        break
                    if not line.strip():
                        continue
                    d = json.loads(line)
                    if not isinstance(d, dict):
                        raise ValueError("server sent something other than a JSON object")
                    if d.get("error"):
                        res.error = d["error"]
                        break
                    m = d.get("message") or {}
                    if res.ttft_s is None and (m.get("content") or m.get("thinking")):
                        res.ttft_s = time.time() - t0
                    res.content += m.get("content") or ""
                    res.thinking += m.get("thinking") or ""
                    if d.get("done"):
                        finished = True
                        ns = 1e9
                        res.done_reason = d.get("done_reason")
                        res.load_s = d["load_duration"] / ns if (d.get("load_duration") or 0) > 0 else None
                        res.prompt_tokens = d.get("prompt_eval_count")
                        if res.prompt_tokens and (d.get("prompt_eval_duration") or 0) > 0:
                            res.prefill_tok_s = res.prompt_tokens / (d["prompt_eval_duration"] / ns)
                        res.gen_tokens = d.get("eval_count")
                        if res.gen_tokens and (d.get("eval_duration") or 0) > 0:
                            res.gen_tok_s = res.gen_tokens / (d["eval_duration"] / ns)
        except (OSError, ValueError, TypeError, AttributeError, ZeroDivisionError) as e:
            res.error = res.error or _http_error(e)
        if not (res.error or finished):
            res.error = "incomplete: the server closed the stream before saying it was done"
        res.wall_s = time.time() - t0
        return res


class OpenAICompat:
    """Any server exposing /v1/chat/completions. Pass the base URL ending in /v1."""
    kind = "openai"

    def __init__(self, url: str = "http://127.0.0.1:8080/v1"):
        self.url = url.rstrip("/")

    def version(self) -> str | None:
        return None

    def model_bytes(self, model: str) -> int | None:
        return None

    def has_model(self, model: str) -> bool | None:
        try:
            with urllib.request.urlopen(self.url + "/models", timeout=10) as r:
                ids = {m.get("id") for m in json.load(r).get("data", [])}
        except (OSError, ValueError, AttributeError):
            return None
        return model in ids if ids else None          # some servers list nothing yet serve anything

    def unload(self, model: str) -> None:
        pass  # no standard way; restart the server between models for a cold load

    def chat(self, model, messages, options, timeout, stop) -> Result:
        body = {"model": model, "messages": messages, "stream": True,
                "stream_options": {"include_usage": True}}
        for ours, theirs in (("temperature", "temperature"), ("top_p", "top_p"),
                             ("seed", "seed"), ("num_predict", "max_tokens")):
            if ours in options:
                body[theirs] = options[ours]
        res, t0 = Result(), time.time()
        t_first = t_last = None
        chunks, usage, timings, finished = 0, {}, {}, False
        try:
            with _post(self.url + "/chat/completions", body, timeout) as r:
                for raw in r:
                    if stop.is_set():
                        res.error = "stopped by the memory watchdog"
                        break
                    line = raw.decode(errors="replace").strip()
                    if not line.startswith("data:"):
                        continue
                    data = line[5:].strip()
                    if data == "[DONE]":
                        finished = True
                        break
                    d = json.loads(data)
                    if not isinstance(d, dict):
                        raise ValueError("server sent something other than a JSON object")
                    usage = d.get("usage") or usage
                    timings = d.get("timings") or timings      # llama.cpp extension
                    for ch in d.get("choices") or []:
                        delta = ch.get("delta") or {}
                        think = delta.get("reasoning_content") or delta.get("reasoning") or ""
                        text = delta.get("content") or ""
                        if think or text:
                            now = time.time()
                            t_first = t_first or now
                            t_last = now
                            chunks += 1
                        res.thinking += think
                        res.content += text
                        res.done_reason = ch.get("finish_reason") or res.done_reason
        except (OSError, ValueError, TypeError, AttributeError) as e:
            res.error = res.error or _http_error(e)
        if not (res.error or finished or res.done_reason):
            res.error = "incomplete: the server closed the stream before saying it was done"
        res.wall_s = time.time() - t0
        if t_first:
            res.ttft_s = t_first - t0
        res.prompt_tokens = timings.get("prompt_n") or usage.get("prompt_tokens")
        res.gen_tokens = timings.get("predicted_n") or usage.get("completion_tokens") or chunks or None
        if timings.get("prompt_per_second"):
            res.prefill_tok_s = timings["prompt_per_second"]
        elif res.prompt_tokens and res.ttft_s:
            res.prefill_tok_s = res.prompt_tokens / res.ttft_s   # upper bound on time, so a lower bound on speed
        if timings.get("predicted_per_second"):
            res.gen_tok_s = timings["predicted_per_second"]
        elif res.gen_tokens and t_first and t_last and t_last > t_first:
            res.gen_tok_s = res.gen_tokens / (t_last - t_first)
        return res


def make(kind: str, url: str | None):
    if kind == "ollama":
        return Ollama(url or "http://127.0.0.1:11434")
    if kind == "openai":
        return OpenAICompat(url or "http://127.0.0.1:8080/v1")
    raise ValueError(f"unknown backend {kind!r} (use ollama or openai)")
