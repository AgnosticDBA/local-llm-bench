import unittest

from llmbench import check

POSTING = "- Infrastructure as code with Terraform in a team setting.\n- Hands-on experience with Microsoft SQL Server administration."
CV = "- Wrote Terraform modules that provision every RDS instance, parameter group and alarm, reviewed by a team of six."
RULES = {"strengths[].requirement": "posting", "strengths[].evidence": "cv", "gaps[].requirement": "posting"}
GATE = {"min_kept": {"strengths": 1, "gaps": 1}, "min_kept_ratio": 0.6}


class Found(unittest.TestCase):
    def test_exact_and_normalised(self):
        self.assertTrue(check.found("Infrastructure as code with Terraform in a team setting", POSTING)[0])
        self.assertTrue(check.found("  infrastructure AS code with   terraform in a team setting.", POSTING)[0])

    def test_curly_quotes_and_dashes(self):
        self.assertTrue(check.found("Hands–on experience with Microsoft SQL Server", POSTING.replace("-on", "–on"))[0])

    def test_paraphrase_rejected(self):
        ok, why = check.found("Terraform experience in a team", POSTING)
        self.assertFalse(ok)
        self.assertEqual(why, "not in source")

    def test_short_quote_rejected(self):
        self.assertEqual(check.found("Terraform", POSTING), (False, "quote too short"))

    def test_ellipsis_pieces_in_order(self):
        self.assertTrue(check.found("Wrote Terraform modules ... reviewed by a team of six", CV)[0])
        self.assertFalse(check.found("reviewed by a team of six ... Wrote Terraform modules", CV)[0])


class Extract(unittest.TestCase):
    def test_fenced_with_think(self):
        txt = '<think>{"not": "this"}</think>Here you go:\n```json\n{"fit_percent": 80}\n```'
        self.assertEqual(check.extract_json(txt), {"fit_percent": 80})

    def test_prose_around_object(self):
        self.assertEqual(check.extract_json('Sure! {"a": [1, 2]} Hope that helps.'), {"a": [1, 2]})

    def test_garbage(self):
        self.assertIsNone(check.extract_json("no json here"))
        self.assertIsNone(check.extract_json("{broken"))


class Verify(unittest.TestCase):
    def test_pass_and_drop(self):
        ans = {"strengths": [
                   {"requirement": "Infrastructure as code with Terraform in a team setting.",
                    "evidence": "Wrote Terraform modules that provision every RDS instance"},
                   {"requirement": "Infrastructure as code with Terraform in a team setting.",
                    "evidence": "Ten years of Terraform"}],          # invented evidence
               "gaps": [{"requirement": "Hands-on experience with Microsoft SQL Server administration.", "kind": "soft"}]}
        v = check.verify(ans, {"posting": POSTING, "cv": CV}, RULES, GATE)
        self.assertTrue(v["passed"], v)
        self.assertEqual(len(v["kept"]["strengths"]), 1)
        self.assertEqual(v["dropped"][0]["why"], "evidence not in source")

    def test_fail_when_too_few_kept(self):
        ans = {"strengths": [{"requirement": "Five years of Kubernetes", "evidence": "x" * 20}], "gaps": []}
        v = check.verify(ans, {"posting": POSTING, "cv": CV}, RULES, GATE)
        self.assertFalse(v["passed"])
        self.assertIn("too few verified", v["reason"])

    def test_judgement_must_include_and_exclude(self):
        rules = {"gaps": {"field": "requirement", "must_include": ["SQL Server", "Kafka"], "must_exclude": ["Terraform"]}}
        ans = {"strengths": [{"requirement": "Infrastructure as code with Terraform in a team setting.",
                              "evidence": "Wrote Terraform modules that provision every RDS instance"}],
               "gaps": [{"requirement": "Hands-on experience with Microsoft SQL Server administration."}]}
        src = {"posting": POSTING, "cv": CV}
        v = check.verify(ans, src, RULES, {**GATE, "min_found": 1, "max_wrong": 0}, rules)
        self.assertTrue(v["passed"], v)
        self.assertEqual(v["judgement"]["missed"], ["Kafka"])
        v = check.verify(ans, src, RULES, {**GATE, "min_found": 2}, rules)
        self.assertEqual(v["reason"], "found 1 of 2 known gaps")
        ans["gaps"].append({"requirement": "Infrastructure as code with Terraform in a team setting."})
        v = check.verify(ans, src, RULES, {**GATE, "max_wrong": 0}, rules)
        self.assertFalse(v["passed"])
        self.assertIn("Terraform listed in gaps", v["reason"])

    def test_not_a_dict(self):
        self.assertFalse(check.verify(None, {}, RULES, GATE)["parsed"])

    def test_items_of_wrong_type_are_dropped_not_crashing(self):
        v = check.verify({"strengths": ["a string"], "gaps": "nope"}, {"posting": POSTING, "cv": CV}, RULES, GATE)
        self.assertFalse(v["passed"])
        self.assertEqual(len(v["dropped"]), 1)


if __name__ == "__main__":
    unittest.main()
