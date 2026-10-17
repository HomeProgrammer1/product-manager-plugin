"""Tests for sdd-product. Run: python3 -m unittest discover -s tests
Set PM_SKILLS_DIR to a pm-skills checkout to also check every skill name the playbook references."""
import copy
import json
import os
import re
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PLUGIN = ROOT / "plugins" / "sdd-product"
CHARTS = PLUGIN / "skills" / "product-charts"
os.environ["SDD_PRODUCT_VERIFY_KEY"] = "test-key"
sys.path.insert(0, str(CHARTS / "scripts"))
import product_charts as pc  # noqa: E402

EXAMPLE = json.loads((CHARTS / "examples" / "example.data.json").read_text(encoding="utf-8"))
EXAMPLE_DIR = CHARTS / "examples"


def errs(data):
    return pc.check(data)[0]


class Check(unittest.TestCase):
    def test_example_is_clean(self):
        e, w = pc.check(EXAMPLE)
        self.assertEqual(e, [])

    def test_som_above_sam(self):
        d = copy.deepcopy(EXAMPLE)
        d["market"]["som"]["value"] = d["market"]["sam"]["value"] * 2
        self.assertTrue(any("SOM is larger than SAM" in x for x in errs(d)))

    def test_sourced_needs_source(self):
        d = copy.deepcopy(EXAMPLE)
        d["market"]["tam"]["sources"] = []
        self.assertTrue(any("marked sourced but cites no source" in x for x in errs(d)))

    def test_unknown_source(self):
        d = copy.deepcopy(EXAMPLE)
        d["market"]["tam"]["sources"] = ["S99"]
        self.assertTrue(any("unknown source S99" in x for x in errs(d)))

    def test_competitor_budget(self):
        d = copy.deepcopy(EXAMPLE)
        for i in range(5):
            c = copy.deepcopy(d["competitors"][1]); c["name"] = f"X{i}"; d["competitors"].append(c)
        self.assertTrue(any("keep at most 8" in x for x in errs(d)))

    def test_exactly_one_you(self):
        d = copy.deepcopy(EXAMPLE)
        d["competitors"][1]["you"] = True
        self.assertTrue(any("exactly one" in x for x in errs(d)))

    def test_experiment_needs_success(self):
        d = copy.deepcopy(EXAMPLE)
        d["experiments"][0]["success"] = ""
        self.assertTrue(any("success criterion" in x for x in errs(d)))

    def test_mixed_price_periods(self):
        d = copy.deepcopy(EXAMPLE)
        d["competitors"][1]["price"]["period"] = "one-time"
        self.assertTrue(any("one-time and recurring" in x for x in errs(d)))

    def test_ranges(self):
        d = copy.deepcopy(EXAMPLE)
        d["competitors"][1]["x"] = 11
        d["assumptions"][0]["impact"] = 7
        d["scorecard"]["dimensions"][0]["score"] = 6
        e = errs(d)
        self.assertTrue(any("x must be 0..10" in x for x in e))
        self.assertTrue(any("impact must be 1..5" in x for x in e))
        self.assertTrue(any("score must be 0..5" in x for x in e))


PAGES = {
    "https://a.test/pricing": "<html><body><h1>Plans</h1><p>Starter&nbsp;plan: $15 per month</p><script>x='$99'</script></body></html>",
    "https://a.test/report": "<p>There are 52 000 salons in Poland.</p>",
}


def fake_fetch(url, timeout=15):
    if url not in PAGES:
        raise OSError("404")
    return 200, url, PAGES[url]


def scored(scores, evidence="sourced", sources=("S1",), profile="bootstrapped"):
    ids = ["problem", "market", "competition", "wtp"]
    return {"meta": {"title": "t"},
            "sources": [{"id": "S1", "title": "pricing", "url": "https://a.test/pricing", "quotes": ["Starter plan: $15 per month"]},
                        {"id": "S2", "title": "report", "url": "https://a.test/report", "quotes": ["There are 52,000 salons in Poland"]},
                        {"id": "S3", "title": "made up", "url": "https://a.test/nowhere", "quotes": ["anything"]}],
            "scorecard": {"profile": profile, "dimensions": [
                {"id": ids[i], "label": ids[i], "score": s, "evidence": evidence, "sources": list(sources), "why": "x"}
                for i, s in enumerate(scores)]}}


class Verdict(unittest.TestCase):
    def verified(self, data):
        pc.verify_sources(data, ROOT, "2026-10-16", fetcher=fake_fetch)
        return data

    def test_go_needs_verified_sources(self):
        d = scored([4, 4, 4, 4])
        self.assertEqual(pc.compute_verdict(d)["verdict"], "pivot")       # unverified -> capped at 3
        v = pc.compute_verdict(self.verified(d))
        self.assertEqual(v["verdict"], "go")
        self.assertEqual(v["confidence_level"], "high")

    def test_quote_matching_is_tolerant(self):
        d = self.verified(scored([4, 4, 4, 4], sources=("S2",)))
        self.assertEqual(d["sources"][1]["verification"]["status"], "quote")
        self.assertIn("52000 salons", d["sources"][1]["verification"]["excerpt"])

    def test_dead_or_fake_source_is_unverified(self):
        d = self.verified(scored([4, 4, 4, 4], sources=("S3",)))
        self.assertEqual(d["sources"][2]["verification"]["status"], "failed")
        v = pc.compute_verdict(d)
        self.assertEqual(set(v["evidence"].values()), {"unverified"})
        self.assertEqual(v["verdict"], "pivot")

    def test_quote_missing_caps_at_4(self):
        d = scored([5, 5, 5, 5])
        d["sources"][0]["quotes"] = ["Enterprise plan: $5 per month"]
        v = pc.compute_verdict(self.verified(d))
        self.assertEqual(set(v["evidence"].values()), {"resolved"})
        self.assertEqual(max(v["used"].values()), 4.0)

    def test_editing_after_verify_voids_it(self):
        d = self.verified(scored([4, 4, 4, 4]))
        d["sources"][0]["quotes"] = ["Starter plan: $1 per month"]
        self.assertEqual(pc.compute_verdict(d)["verdict"], "pivot")

    def test_handwritten_verification_is_rejected(self):
        d = scored([4, 4, 4, 4], sources=("S3",))
        d["sources"][2]["verification"] = {"status": "quote", "checked": "2026-10-16",
                                           "sig": pc.hashlib.sha1(b"forged").hexdigest()[:20]}
        self.assertEqual(pc.compute_verdict(d)["verdict"], "pivot")

    def test_original_attack_title_only_source(self):
        d = copy.deepcopy(EXAMPLE)
        d["sources"].append({"id": "S9", "title": "мені так здається"})
        for x in d["scorecard"]["dimensions"]:
            x["evidence"] = "sourced"; x["sources"] = ["S9"]; x["score"] = min(5, x["score"] + 0.5)
        self.assertTrue(any("none of its sources has a url" in e for e in errs(d)))
        self.assertNotEqual(pc.compute_verdict(d, EXAMPLE_DIR)["verdict"], "go")

    def test_tested_needs_founder_file(self):
        d = scored([5, 5, 5, 5], evidence="tested")
        self.assertTrue(any("marked tested" in e for e in errs(d)))
        with tempfile.TemporaryDirectory() as tmp:
            Path(tmp, "notes.md").write_text("12 of 40 owners paid a deposit", encoding="utf-8")
            d["sources"].append({"id": "S4", "title": "notes", "path": "notes.md", "quotes": ["12 of 40 owners paid"]})
            for x in d["scorecard"]["dimensions"]:
                x["sources"] = ["S4"]
            pc.verify_sources(d, tmp, "2026-10-16", fetcher=fake_fetch)
            v = pc.compute_verdict(d, tmp)
            self.assertEqual(set(v["evidence"].values()), {"tested"})
            self.assertEqual(v["verdict"], "go")
            Path(tmp, "notes.md").write_text("40 of 40 owners paid", encoding="utf-8")   # edited after verify
            self.assertEqual(set(pc.compute_verdict(d, tmp)["evidence"].values()), {"unverified"})

    def test_red_team_challenge_needs_evidence_to_count_in_full(self):
        d = self.verified(scored([4, 4, 4, 4]))
        d["red_team"] = [{"dimension": "wtp", "claimed": 4, "proposed": 1.5, "reason": "nobody paid"}]
        v = pc.compute_verdict(d)
        self.assertEqual(v["used"]["wtp"], 3.5)                                      # thin-evidence challenge: at most -0.5
        d["red_team"][0]["sources"] = ["S3"]                                         # counter-evidence that does not verify
        self.assertEqual(pc.compute_verdict(d)["used"]["wtp"], 3.5)
        d["red_team"][0]["sources"] = ["S2"]                                         # verified counter-evidence
        v = pc.compute_verdict(d)
        self.assertEqual(v["used"]["wtp"], 1.5)
        self.assertNotEqual(v["verdict"], "go")
        d["red_team"][0].update(resolution="rebutted", rebuttal_sources=["S3"])      # unverified rebuttal
        self.assertNotEqual(pc.compute_verdict(d)["verdict"], "go")
        d["red_team"][0]["rebuttal_sources"] = ["S1"]                                # verified rebuttal
        self.assertEqual(pc.compute_verdict(d)["verdict"], "go")

    def test_kill_needs_evidence_against(self):
        d = scored([2, 2, 2, 2], evidence="assumed", sources=())
        v = pc.compute_verdict(d)
        self.assertEqual(v["verdict"], "unproven")                                   # low only for lack of evidence
        self.assertEqual(v["grounded"]["guess"], 100)
        d = self.verified(scored([2, 2, 2, 2]))
        self.assertEqual(pc.compute_verdict(d)["verdict"], "kill")                   # verified sources say it is weak

    def test_indirect_source_counts_less(self):
        d = self.verified(scored([5, 5, 5, 5]))
        d["scorecard"]["dimensions"][0]["direct"] = False
        v = pc.compute_verdict(d)
        self.assertEqual(v["evidence"]["problem"], "proxy")
        self.assertEqual(v["used"]["problem"], 4.0)
        self.assertGreater(v["grounded"]["proxy"], 0)

    def test_pdf_without_reader_counts_as_found_not_verified(self):
        d = scored([4, 4, 4, 4])

        def pdf_fetch(url, timeout=15):
            raise pc.PdfUnreadable("PDF: quotes need pdftotext")
        pc.verify_sources(d, ROOT, "2026-10-16", fetcher=pdf_fetch)
        self.assertEqual(d["sources"][0]["verification"]["status"], "url")
        self.assertEqual(pc.compute_verdict(d)["evidence"]["problem"], "resolved")

    def test_provenance_lists_every_number(self):
        table = pc.provenance(EXAMPLE, EXAMPLE_DIR)
        self.assertIn("TAM", table)
        self.assertIn("BookFlow", table)
        self.assertIn("4.5 → 4", table)

    def test_fragment_quote_does_not_verify(self):
        d = scored([4, 4, 4, 4])
        d["sources"][0]["quotes"] = ["$15 per month"]
        self.verified(d)
        self.assertEqual(d["sources"][0]["verification"]["status"], "url")
        self.assertIn("too short", d["sources"][0]["verification"]["reason"])
        self.assertTrue(any("fragment" in w for w in pc.check(d)[1]))

    def test_market_inputs_must_multiply_and_show_guesses(self):
        d = copy.deepcopy(EXAMPLE)
        sam = d["market"]["sam"]["value"]
        d["market"]["sam"]["inputs"] = [{"label": "agencies", "value": sam / 1000, "basis": "sourced", "sources": ["S1"]},
                                        {"label": "price", "value": 1000, "basis": "assumed"}]
        e, w = pc.check(d)
        self.assertFalse(any("inputs multiply" in x for x in e))
        self.assertTrue(any("assumed factor(s): price" in x for x in w))
        d["market"]["sam"]["inputs"][1]["value"] = 999999
        self.assertTrue(any("inputs multiply" in x for x in errs(d)))

    def test_skipped_step_needs_reason(self):
        d = copy.deepcopy(EXAMPLE)
        d["meta"]["steps"] = [{"n": 4, "skill": "pm-market-research:market-sizing", "mode": "reduced"}]
        self.assertTrue(any("without a reason" in x for x in errs(d)))
        d["meta"]["steps"][0]["reason"] = "to save time"
        self.assertTrue(any("to save time" in x for x in pc.check(d)[1]))

    def test_profiles_and_fixed_weights(self):
        d = self.verified(scored([3.5, 2, 3.5, 3.5]))
        self.assertEqual(pc.compute_verdict(d)["verdict"], "pivot")
        d["scorecard"]["profile"] = "side"
        self.assertEqual(pc.compute_verdict(d)["verdict"], "go")
        d["scorecard"]["profile"] = "venture"
        self.assertEqual(pc.compute_verdict(d)["verdict"], "pivot")
        d["scorecard"]["profile"] = "bootstrapped"
        d["scorecard"]["dimensions"][1]["weight"] = 0.01
        self.assertEqual(pc.compute_verdict(d)["verdict"], "pivot")
        self.assertTrue(any("custom weight ignored" in w for w in pc.check(d)[1]))

    def test_red_flags_and_fragile(self):
        d = self.verified(scored([5, 5, 5, 1.5]))
        self.assertEqual(pc.compute_verdict(d)["verdict"], "pivot")
        d = self.verified(scored([5, 5, 1, 1]))
        self.assertEqual(pc.compute_verdict(d)["verdict"], "kill")
        d = self.verified(scored([3.5, 3.5, 3.5, 3.5]))
        v = pc.compute_verdict(d)
        self.assertEqual(v["verdict"], "go")
        self.assertTrue(v["fragile"])

    def test_example(self):
        self.assertEqual(pc.compute_verdict(EXAMPLE, EXAMPLE_DIR)["verdict"], "pivot")

    def test_real_http_fetch(self):
        import http.server
        import threading

        class H(http.server.BaseHTTPRequestHandler):
            def do_GET(self):
                body = "<html><body><p>Pro: 29 zł / miesiąc</p></body></html>".encode("utf-8")
                self.send_response(200); self.send_header("Content-Type", "text/html; charset=utf-8"); self.end_headers()
                self.wfile.write(body)

            def log_message(self, *a):
                pass

        srv = http.server.HTTPServer(("127.0.0.1", 0), H)
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        try:
            d = {"sources": [{"id": "S1", "url": f"http://127.0.0.1:{srv.server_port}/p", "quotes": ["Pro: 29 zł / miesiąc"]}]}
            pc.verify_sources(d, ROOT, "2026-10-16")
            self.assertEqual(d["sources"][0]["verification"]["status"], "quote")
        finally:
            srv.shutdown()
            srv.server_close()


class Build(unittest.TestCase):
    def test_build_all_charts(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            rep = pc.build(EXAMPLE, out, pc.load_theme(), base=EXAMPLE_DIR)
            names = [c["name"] for c in rep["charts"]]
            self.assertEqual(names, [n for n, _, _ in pc.CHARTS])
            for n in names:
                root = ET.fromstring((out / f"{n}.svg").read_text(encoding="utf-8"))
                self.assertEqual(root.get("role"), "img")
                tags = [c.tag.split("}")[-1] for c in root]
                self.assertEqual(tags[:2], ["title", "desc"])
                self.assertEqual(root.get("data-source-sha1"), pc.chart_hash(EXAMPLE, n))
            html_ = (out / "index.html").read_text(encoding="utf-8")
            self.assertIn("prefers-color-scheme: dark", html_)
            self.assertEqual(html_.count("<details>"), len(names))
            self.assertEqual(pc.stale(EXAMPLE, out), [])
            d = copy.deepcopy(EXAMPLE); d["market"]["tam"]["value"] += 1
            self.assertTrue(any(m.startswith("market") for m in pc.stale(d, out)))

    def test_partial_data_skips(self):
        d = {"meta": {"title": "t"}, "assumptions": EXAMPLE["assumptions"]}
        with tempfile.TemporaryDirectory() as tmp:
            rep = pc.build(d, Path(tmp), pc.load_theme())
            self.assertEqual([c["name"] for c in rep["charts"]], ["assumptions"])

    def test_cli_refuses_errors(self):
        d = copy.deepcopy(EXAMPLE); d["market"]["som"]["value"] = 10 ** 12
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "data.json"; p.write_text(json.dumps(d), encoding="utf-8")
            self.assertEqual(pc.main(["build", str(p)]), 1)
            self.assertFalse((Path(tmp) / "charts").exists())

    def test_themes_contrast(self):
        self.assertEqual(pc.contrast_issues(pc.DEFAULT_THEME), [])
        self.assertEqual(pc.contrast_issues({**pc.DEFAULT_THEME, **pc.DARK_THEME}, "dark"), [])

    def test_tokens(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "t.json"
            p.write_text(json.dumps({"color": {"primary": {"$value": "{base.brand}"}}, "base": {"brand": {"$value": "#0b5cad"}}}))
            self.assertEqual(pc.load_theme(tokens_path=p)["accent"], "#0b5cad")

    def test_money(self):
        self.assertEqual(pc.money(1_300_000, "USD", "uk"), "$1,3 млн")
        self.assertEqual(pc.money(4_200_000_000, "EUR", "en"), "€4.2B")
        self.assertEqual(pc.money(9, "UAH", "en"), "₴9")


class Plugin(unittest.TestCase):
    def frontmatter(self, path):
        text = path.read_text(encoding="utf-8")
        m = re.match(r"---\n(.*?)\n---\n", text, re.S)
        self.assertIsNotNone(m, path)
        return dict(re.findall(r"^(\w[\w-]*):\s*(.+)$", m.group(1), re.M))

    def test_skills_and_agent(self):
        for skill in (PLUGIN / "skills").iterdir():
            fm = self.frontmatter(skill / "SKILL.md")
            self.assertEqual(fm["name"], skill.name)
            self.assertLessEqual(len(fm["description"]), 1024)
        fm = self.frontmatter(PLUGIN / "agents" / "market-researcher.md")
        self.assertEqual(fm["name"], "market-researcher")
        self.assertNotIn("Write", fm["tools"])

    def test_orchestrator_is_explicit_only(self):
        text = (PLUGIN / "skills" / "product" / "SKILL.md").read_text(encoding="utf-8")
        fm = text.split("---")[1]
        self.assertNotIn("disable-model-invocation", fm)  # the desktop app hides such skills from the / menu
        self.assertIn("Use only when the user types /sdd-product:product", fm)

    def test_skeptic_cannot_write(self):
        fm = self.frontmatter(PLUGIN / "agents" / "skeptic.md")
        self.assertFalse({"Write", "Edit", "Bash"} & {x.strip() for x in fm["tools"].split(",")})

    def test_no_hooks(self):
        self.assertFalse((PLUGIN / "hooks").exists(), "sdd-product must not install hooks")

    def test_playbook_names_exist(self):
        pm = os.environ.get("PM_SKILLS_DIR")
        if not pm:
            self.skipTest("PM_SKILLS_DIR not set")
        text = "".join(p.read_text(encoding="utf-8") for p in (PLUGIN / "skills").rglob("*.md"))
        names = set(re.findall(r"`(pm-[a-z-]+):([a-z0-9-]+)`", text))
        self.assertGreater(len(names), 20)
        missing = [f"{p}:{s}" for p, s in names if not (Path(pm) / p / "skills" / s / "SKILL.md").exists()]
        self.assertEqual(missing, [])


if __name__ == "__main__":
    unittest.main()
