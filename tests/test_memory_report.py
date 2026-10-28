import json
import tempfile
import unittest
from pathlib import Path

from llmbench import cli, memory, report

VM_STAT = """Mach Virtual Memory Statistics: (page size of 16384 bytes)
Pages free:                               12345.
Pages occupied by compressor:            64000.
Swapins:                               8914989.
Swapouts:                             11649753.
"""
MEMINFO = """MemTotal:       65536000 kB
MemFree:         1000000 kB
MemAvailable:   32768000 kB
SwapTotal:       8388608 kB
SwapFree:        7340032 kB
"""


class Parsers(unittest.TestCase):
    def test_vm_stat(self):
        s = memory.parse_vm_stat(VM_STAT)
        self.assertEqual(s["swapin_bytes"], 8914989 * 16384)
        self.assertAlmostEqual(s["compressed_mb"], 1000.0)

    def test_swapusage_and_pressure(self):
        self.assertEqual(memory.parse_swapusage("total = 6144.00M  used = 5283.12M  free = 860.88M  (encrypted)"), 5283.12)
        self.assertEqual(memory.parse_swapusage("total = 8.00G  used = 1.50G  free = 6.50G"), 1536.0)
        self.assertEqual(memory.parse_memory_pressure("System-wide memory free percentage: 74%"), 74.0)
        self.assertIsNone(memory.parse_memory_pressure(""))

    def test_linux(self):
        s = memory.parse_meminfo(MEMINFO)
        self.assertAlmostEqual(s["free_pct"], 50.0)
        self.assertAlmostEqual(s["swap_used_mb"], 1024.0)
        self.assertEqual(memory.parse_vmstat("pswpin 10\npswpout 20\n", 4096), {"swapin_bytes": 40960, "swapout_bytes": 81920})


def fake_samples(t0, n, free, swap_step_mb):
    return [{"t": t0 + 2 * i, "free_pct": free(i), "swap_used_mb": 1000 + i * swap_step_mb,
             "swapin_bytes": i * swap_step_mb * 2 ** 20, "swapout_bytes": 0, "compressed_mb": 0} for i in range(n)]


class Summary(unittest.TestCase):
    def test_window_and_verdict(self):
        s = fake_samples(100, 50, lambda i: 70 if i < 5 or i > 44 else 3, 10)
        m = memory.summarise(s, 110, 190)
        self.assertEqual(m["free_pct_before"], 70)
        self.assertEqual(m["free_pct_min"], 3)
        self.assertAlmostEqual(m["swapped_in_mb"], 400, delta=11)
        self.assertAlmostEqual(m["peak_swap_mb_s"], 5.0)
        self.assertEqual(memory.verdict(m), "comfortable")
        self.assertEqual(memory.verdict({**m, "swapped_in_mb": 2048}), "swapping")
        self.assertEqual(memory.verdict({**m, "peak_swap_mb_s": 900}), "thrashing")
        self.assertEqual(memory.verdict({"available": False}), "unknown")
        # pushing other apps OUT to swap is the cost too, even if nothing is read back during the run
        self.assertEqual(memory.verdict({**m, "swapped_out_mb": 4096}), "swapping")
        self.assertEqual(memory.verdict({**m, "swapped_out_mb": 10240}), "thrashing")
        self.assertEqual(memory.verdict({**m, "swap_used_mb_before": 0, "swap_used_mb_peak": 9000}), "thrashing")
        reset = fake_samples(0, 10, lambda i: 50, 0)
        for i, x in enumerate(reset):
            x["swapout_bytes"] = (9 - i) * 2 ** 30         # a counter that went backwards must not cancel real swap
        self.assertGreaterEqual(memory.summarise(reset, 1, 17)["swapped_out_mb"], 0)

    def test_empty(self):
        self.assertEqual(memory.summarise([], 0, 1), {"available": False})


class Quotes(unittest.TestCase):
    CV = cli.load_task("gap-analysis")["source_text"]["cv"]

    def test_stitched_quotes_fail(self):
        from llmbench import check
        self.assertFalse(check.found("Lead engineer in the ... SQL Server ... migration", self.CV)[0])
        self.assertFalse(check.found("e ... e ... e ... e ... e", self.CV)[0])
        line = next(l for l in self.CV.splitlines() if len(l) > 80)
        a, b = line[2:30], line[-30:-2]
        self.assertTrue(check.found(f"{a} ... {b}", self.CV)[0])      # a real elision on one line still counts

    def test_elision_across_a_wrapped_line(self):
        from llmbench import check
        posting = cli.load_task("gap-analysis")["source_text"]["posting"]
        self.assertTrue(check.found("about 180 PostgreSQL clusters on AWS ... a small SQL Server estate we inherited "
                                    "from an acquisition", posting)[0])

    def test_round3_quote_rules(self):
        from llmbench import check
        cv = cli.load_task("gap-analysis")["source_text"]["cv"]
        self.assertFalse(check.found("Dutch (beginner, A1 evening course) Summary Database reliability engineer", cv)[0])
        self.assertTrue(check.found("Reduced monthly AWS database spend by 22%", cv)[0])
        line = next(l for l in cv.splitlines() if len(l) > 80)
        self.assertTrue(check.found(f"{line[2:30]} [...] {line[-30:-2]}", cv)[0])

    def test_nice_to_have_copied_as_gaps_fails(self):
        from llmbench import check
        t = cli.load_task("gap-analysis")
        post = t["source_text"]["posting"]
        nice = [l[2:] for l in post[post.find("Nice to have"):].splitlines() if l.startswith("- ")][:5]
        cv_lines = [l[2:] for l in t["source_text"]["cv"].splitlines() if l.startswith("- ")]
        must = [l[2:] for l in post.splitlines() if l.startswith("- ")][:2]
        ans = {"strengths": [{"requirement": must[0], "evidence": cv_lines[0]}, {"requirement": must[1], "evidence": cv_lines[1]}],
               "gaps": [{"requirement": n} for n in nice]}
        v = check.verify(ans, t["source_text"], t["checks"], t["gate"], t["judgement"])
        self.assertFalse(v["passed"], v["reason"])

    def test_content_failure_reported_before_cap(self):
        from llmbench import check
        src = {"s": "alpha bravo charlie delta echo foxtrot golf hotel"}
        v = check.verify({"l": [{"q": "alpha bravo charlie"}, {"q": "delta echo foxtrot"}]}, src, {"l[].q": "s"},
                         {"max_kept": {"l": 1}, "min_found": 1}, {"l": {"field": "q", "must_include": ["hotel"]}})
        self.assertTrue(v["reason"].startswith("found 0 of 1"), v["reason"])

    def test_verdict_figures(self):
        self.assertEqual(memory.why({"available": True, "swapped_in_mb": 205, "swapped_out_mb": 9626, "peak_swap_mb_s": 812.4}),
                         " (0.2 GB in, 9.4 GB out, peak 812 MB/s)")
        self.assertEqual(memory.why({"available": False}), "")

    def test_near_duplicates(self):
        from llmbench import check
        src = {"s": "the quick brown fox jumps over the lazy dog"}
        v = check.verify({"l": [{"q": "quick brown fox jumps"}, {"q": "Quick brown fox jumps.."}]}, src, {"l[].q": "s"}, {})
        self.assertEqual(len(v["kept"]["l"]), 1)

    def test_duplicates_and_cap(self):
        from llmbench import check
        src = {"s": "the quick brown fox jumps over the lazy dog"}
        item = {"q": "quick brown fox jumps"}
        v = check.verify({"l": [item, item]}, src, {"l[].q": "s"}, {})
        self.assertEqual((len(v["kept"]["l"]), v["dropped"][0]["why"]), (1, "duplicate"))
        v = check.verify({"l": [item, {"q": "over the lazy dog"}]}, src, {"l[].q": "s"}, {"max_kept": {"l": 1}})
        self.assertIn("too many l", v["reason"])


class Fit(unittest.TestCase):
    def test_estimate(self):
        gb = 2 ** 30
        self.assertEqual(cli.fit_estimate(5 * gb, 64, 80, apple=False)["verdict"], "fits")
        self.assertEqual(cli.fit_estimate(17 * gb, 32, 74, apple=True)["verdict"], "tight")
        self.assertEqual(cli.fit_estimate(23 * gb, 32, 74, apple=True)["verdict"], "too big for the GPU")
        self.assertEqual(cli.fit_estimate(23 * gb, 32, 30, apple=False)["verdict"], "will swap")
        self.assertIsNone(cli.fit_estimate(None, 32, 50, apple=True))


class Report(unittest.TestCase):
    def test_renders(self):
        task = cli.load_task("gap-analysis")
        self.assertIn("Halvorsen", cli.messages(task)[1]["content"])
        s = fake_samples(0, 30, lambda i: 60 - i, 50)
        run = {"model": "demo:1b", "repeat": 1, "t_start": 10, "t_end": 50, "samples": s,
               "metrics": {"wall_s": 40.2, "prefill_tok_s": 300, "gen_tok_s": 12.5, "gen_tokens": 500, "error": None},
               "check": {"parsed": True, "passed": False, "kept": {"strengths": [], "gaps": [1]},
                         "dropped": [1, 2], "reason": "too few verified strengths"},
               "memory": memory.summarise(s, 10, 50), "memory_verdict": "swapping"}
        results = {"runs": [run], "repeats": 1, "machine_text": "Test box", "backend": "ollama",
                   "backend_version": "0.0", "started": "now", "task": {"name": "gap-analysis"}}
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / "results.json").write_text(json.dumps(results), encoding="utf-8")
            report.write(Path(d))
            page = (Path(d) / "report.html").read_text(encoding="utf-8")
            self.assertIn("<svg", page)
            self.assertIn("failed: too few verified strengths", page)
            self.assertIn("| demo:1b | 40 s |", (Path(d) / "report.md").read_text(encoding="utf-8"))
        self.assertIn("FAIL", report.table(results))


if __name__ == "__main__":
    unittest.main()
