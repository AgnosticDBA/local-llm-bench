import json
import re
import tempfile
import unittest
from pathlib import Path

from llmbench import cli, share

SECRETS = ["SECRET-QUOTE-FROM-MY-CONTRACT", "/Users/alice", "10.0.0.5", "18:28:20", "acme-merger-review",
           "Project Falcon", "reasoning about Falcon"]


def results(task_dir="built-in:gap-analysis", task_name="gap-analysis", fp=share.BUILTIN["gap-analysis"]):
    run = {
        "model": "/Users/alice/models/acme-7b-q4.gguf", "repeat": 1,
        "metrics": {"wall_s": 41.234, "ttft_s": 2.0, "gen_tok_s": 12.345, "gen_tokens": 500,
                    "done_reason": "stop", "error": "HTTP 500: upstream http://10.0.0.5:8080 said no"},
        "check": {"parsed": True, "passed": True,
                  "kept": {"strengths": [{"requirement": "x", "evidence": "SECRET-QUOTE-FROM-MY-CONTRACT"}], "gaps": []},
                  "dropped": [{"list": "gaps", "item": {"requirement": "Project Falcon"}, "why": "not in source"}],
                  "judgement": {"found": 1, "expected": 2, "missed": ["Project Falcon"], "wrong": ["Project Falcon listed in gaps"]},
                  "reason": "wrong: Project Falcon listed in gaps"},
        "memory": {"available": True, "free_pct_min": 9.0, "swapped_in_mb": 2048.0},
        "memory_verdict": "swapping", "fit_estimate": {"verdict": "tight", "need_gb": 20},
        "answer": {"strengths": [{"evidence": "SECRET-QUOTE-FROM-MY-CONTRACT"}]},
        "raw_head": "reasoning about Falcon", "samples": [{"t": 1, "free_pct": 50}], "t_start": 1, "t_end": 2,
    }
    return {"tool_version": "0.1.0", "started": "2026-10-28 18:28:20 CET",
            "machine": {"os": "macOS 26.6.2", "arch": "arm64", "cpu": "Apple M1 Pro", "cores": "8P+2E",
                        "ram_gb": 32, "gpu": "Apple GPU (unified memory)", "hostname": "alices-mbp"},
            "machine_text": "Apple M1 Pro on /Users/alice", "backend": "ollama", "backend_version": "0.40.11",
            "task": {"name": task_name, "description": "Project Falcon", "dir": task_dir, **({"fingerprint": fp} if fp else {})},
            "repeats": 1, "runs": [run]}


class Share(unittest.TestCase):
    def assert_clean(self, shared):
        text = json.dumps(shared) + share.markdown(shared)
        for s in SECRETS + ["alices-mbp"]:
            self.assertNotIn(s, text, f"leaked {s!r}")

    def test_builtin_keeps_only_allowed_fields(self):
        s = share.summary(results())
        self.assert_clean(s)
        self.assertEqual(share.unexpected(s), [])
        run = s["runs"][0]
        self.assertEqual(run["model"], "acme-7b-q4.gguf")
        self.assertEqual(run["metrics"]["wall_s"], 41.2)
        self.assertIs(run["metrics"]["error"], True)
        self.assertEqual(run["check"]["kept"], {"strengths": 1, "gaps": 0})
        self.assertEqual(run["check"]["wrong"], 1)
        self.assertEqual(s["date"], "2026-10-28")
        self.assertEqual(s["machine"]["os"], "macOS 26")

    def test_custom_task_refused_by_default(self):
        with self.assertRaises(share.Refused):
            share.summary(results("/Users/alice/tasks/acme", "acme-merger-review"))

    def test_custom_task_fingerprint_only(self):
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / "task.json").write_text('{"name": "acme-merger-review"}', encoding="utf-8")
            (Path(d) / "contract.md").write_text("SECRET-QUOTE-FROM-MY-CONTRACT", encoding="utf-8")
            s = share.summary(results(d, "acme-merger-review", fp=None), include_custom=True)
            self.assert_clean(s)
            self.assertNotIn(d, json.dumps(s))
            self.assertEqual(s["task"]["name"], "custom")
            self.assertRegex(s["task"]["fingerprint"], r"^[0-9a-f]{12}$")
            self.assertEqual(s["runs"][0]["check"]["kept"], 1)    # a total, not per-list names
            again = share.summary(results(d, "other-name", fp=None), include_custom=True)["task"]["fingerprint"]
            self.assertEqual(again, s["task"]["fingerprint"])
            (Path(d) / "contract.md").write_text("changed", encoding="utf-8")
            self.assertNotEqual(share.fingerprint(d)[:12], s["task"]["fingerprint"])

    def test_changed_builtin_counts_as_custom(self):
        with self.assertRaises(share.Refused):           # same name, other content: e.g. a private CV dropped in
            share.summary(results(fp="0" * 64))
        with self.assertRaises(share.Refused):
            share.summary(results(fp=None))
        s = share.summary(results(fp="0" * 64), include_custom=True)
        self.assertEqual(s["task"], {"name": "custom", "builtin": False, "fingerprint": "0" * 12})

    def test_shipped_task_matches_its_fingerprint(self):
        self.assertTrue(cli.load_task("gap-analysis")["dir"].startswith("built-in:"))
        with tempfile.TemporaryDirectory() as d:          # a copy elsewhere is a custom task by path, not name
            for f in (cli.TASKS / "gap-analysis").iterdir():
                (Path(d) / f.name).write_bytes(f.read_bytes())
            self.assertEqual(cli.load_task(d)["dir"], d)

    def test_model_paths_and_urls(self):
        for raw, want in [("C:/Users/alice/models/x.gguf", "x.gguf"), ("C:\\Users\\alice\\x.gguf", "x.gguf"),
                          ("models/alice/secret.gguf", "secret.gguf"), ("~/m/y.safetensors", "y.safetensors"),
                          ("http://user:pass@10.0.0.5/v1/mymodel", "mymodel"), ("me@host:qwen", "withheld"),
                          ("qwen3:14b", "qwen3:14b"), ("hf.co/unsloth/Qwen3.6-35B-A3B-GGUF:UD-Q3_K_XL",
                                                       "hf.co/unsloth/Qwen3.6-35B-A3B-GGUF:UD-Q3_K_XL"),
                          ("bad | name", "withheld"), (None, "withheld")]:
            self.assertEqual(share.model_name(raw), want, raw)

    def test_odd_values_never_pass_through(self):
        r = results()
        r["started"] = "SECRET-not-a-date"
        r["machine"]["cpu"] = {"SECRET": 1}
        r["backend_version"] = "SECRET text with spaces"
        r["runs"][0].update(repeat="SECRET", memory_verdict="SECRET")
        r["runs"][0]["metrics"]["wall_s"] = "SECRET"
        r["runs"][0]["memory"]["free_pct_min"] = "SECRET"
        s = share.summary(r)
        self.assertNotIn("SECRET", json.dumps(s))
        self.assertEqual(share.unexpected(s), [])

    def test_verify_checks_values_and_bad_files(self):
        s = share.summary(results())
        s["runs"][0]["metrics"]["wall_s"] = "my secret"
        s["machine"]["cpu"] = "x" * 200
        self.assertEqual(sorted(b.split(" =")[0] for b in share.unexpected(s)),
                         ["machine.cpu", "runs[0].metrics.wall_s"])
        self.assertTrue(share.unexpected([1, 2]))
        self.assertTrue(share.unexpected({"runs": "x"}))
        with tempfile.TemporaryDirectory() as d:
            for name, body in [("list.json", "[1]"), ("junk.md", "not json")]:
                (Path(d) / name).write_text(body, encoding="utf-8")
                with self.assertRaises(SystemExit) as e:
                    cli.main(["share", "--verify", str(Path(d) / name)])
                self.assertNotEqual(e.exception.code, 0)
            with self.assertRaises(SystemExit) as e:
                cli.main(["share", "--verify", str(Path(d) / "missing.md")])
            self.assertNotEqual(e.exception.code, 0)

    def test_model_names_round2(self):
        for raw, want in [("Users/alice/models/qwen-private", "qwen-private"), ("srv/models/acme/ft-v3", "ft-v3"),
                          ("192.168.1.20:8080/qwen", "qwen"), ("gpu-box.corp.acme.com/qwen", "qwen"),
                          ("library/qwen3:8b", "library/qwen3:8b"), ("qwen3.6:35b-a3b", "qwen3.6:35b-a3b"),
                          ("peter/x.gguf", "x.gguf"), ("http://10.0.0.5:8080", "withheld"),
                          ("http://gpu-box.lan:11434/", "withheld"), ("nas.home.arpa:5000", "withheld"),
                          ("peter@192.168.1.10:qwen3", "withheld"),
                          ("llama-3.1-8b-instruct@q4_k_m", "llama-3.1-8b-instruct@q4_k_m")]:
            self.assertEqual(share.model_name(raw), want, raw)

    def test_cores_and_cpu_shapes(self):
        r = results()
        r["machine"].update(cores=16, cpu="Intel(R) Core(TM) i7-9750H CPU @ 2.60GHz")
        s = share.summary(r)
        self.assertEqual((s["machine"]["cores"], s["machine"]["cpu"]), (16, "Intel(R) Core(TM) i7-9750H CPU @ 2.60GHz"))
        r["machine"]["cpu"] = "Peter peter@example.com"
        self.assertIsNone(share.summary(r)["machine"]["cpu"])

    def test_crlf_checkout_is_still_builtin(self):
        with tempfile.TemporaryDirectory() as d:
            for f in (cli.TASKS / "gap-analysis").iterdir():
                (Path(d) / f.name).write_bytes(f.read_bytes().replace(b"\n", b"\r\n"))
            self.assertEqual(share.fingerprint(d), share.BUILTIN["gap-analysis"])

    def test_verify_rejects_anything_around_the_json(self):
        md = share.markdown(share.summary(results()))
        self.assertEqual(share.verify_text(md), [])
        self.assertTrue(share.verify_text(md.replace("**llmbench", "Peter, 12 Example St **llmbench", 1)))
        self.assertTrue(share.verify_text(md + "\nhttp://10.0.0.5:11434\n"))
        self.assertTrue(share.verify_text(md.replace("| PASS |", "| FAIL |", 1).replace("| FAIL |", "| PASS |", 1)
                                          .replace("41.2 s", "4.1 s", 1)))
        with self.assertRaises(ValueError):
            share.verify_text(md.replace('"llmbench_share": 1,', '"llmbench_share": 1, "tool_version": "my CV",', 1))
        with self.assertRaises((RecursionError, ValueError)):     # 3.14's json raises ValueError here
            share.verify_text("```json\n" + "[" * 100000 + "\n```")
        self.assertEqual(share.verify_text("\ufeff" + md.replace("\n", "\r\n")), [])
        self.assertTrue(share.verify_text(md[md.find("```json") + 7:md.rfind("```")]))       # bare JSON
        forged = md.replace("task `gap-analysis`", "task `acme-merger`").replace('"name": "gap-analysis"', '"name": "acme-merger"')
        self.assertTrue(share.verify_text(forged))
        self.assertTrue(share.verify_text(md.replace('"kept": {', '"kept": null, "_": {', 1)))

    def test_unexpected_flags_added_fields(self):
        s = share.summary(results())
        s["runs"][0]["answer"] = "x"
        s["machine"]["hostname"] = "y"
        self.assertEqual(sorted(share.unexpected(s)), ["machine.hostname", "runs[0].answer"])

    def test_os_major(self):
        self.assertEqual(share.os_major("Linux 6.8.0-45-generic"), "Linux 6.8")
        self.assertEqual(share.os_major("Windows 11"), "Windows 11")
        self.assertEqual(share.os_major(""), "unknown")

    def test_cli_writes_and_verifies(self):
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / "results.json").write_text(json.dumps(results()), encoding="utf-8")
            cli.main(["share", d])
            md = (Path(d) / "share.md").read_text(encoding="utf-8")
            self.assert_clean(json.loads(re.search(r"```json\s*(\{.*\})\s*```", md, re.S).group(1)))
            with self.assertRaises(SystemExit) as ok:
                cli.main(["share", "--verify", str(Path(d) / "share.md")])
            self.assertEqual(ok.exception.code, 0)
            (Path(d) / "share.md").write_text(md.replace('"repeat": 1', '"repeat": 1, "answer": "x"'), encoding="utf-8")
            with self.assertRaises(SystemExit) as bad:
                cli.main(["share", "--verify", str(Path(d) / "share.md")])
            self.assertEqual(bad.exception.code, 1)


if __name__ == "__main__":
    unittest.main()
