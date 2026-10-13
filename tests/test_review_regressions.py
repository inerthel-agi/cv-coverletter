"""Offline regressions: the eighteen findings of the read-only review (tests 1-18), then the six defects of the
final pre-commit review (tests 19-24). Each test failed on the code before its fix."""
import copy
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest import mock
import zipfile
import zlib

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / ".claude/skills/cv-ats-us/scripts"
sys.path.insert(0, str(SCRIPTS))
sys.path.insert(0, str(ROOT / "tests/e2e"))  # run_e2e, imported by test_15
import audit_package
import build_docs
import check_docs


class ReviewRegressionTests(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory(prefix="cvats-regression-")
        self.folder = Path(folder.name)
        if not self.folder.resolve().is_relative_to(Path(tempfile.gettempdir()).resolve()):
            raise RuntimeError("temporary test folder is outside the expected temp directory")
        self.addCleanup(folder.cleanup)

    def package(self):
        return json.loads((ROOT / "tests/fixtures/packages/brindlewood.json").read_text(encoding="utf-8"))

    def verdicts(self):
        return json.loads((ROOT / "tests/fixtures/verdicts/brindlewood.json").read_text(encoding="utf-8"))

    def write(self, name, data, encoding="utf-8"):
        path = self.folder / name
        path.write_text(json.dumps(data, ensure_ascii=False), encoding=encoding)
        return path

    def run_script(self, name, *args):
        return subprocess.run([sys.executable, str(SCRIPTS / name)] + list(map(str, args)),
                              capture_output=True, encoding="utf-8",
                              env=dict(os.environ, PYTHONDONTWRITEBYTECODE="1"))

    def audit(self, package, verdicts=None):
        au = audit_package.Audit(package, str(ROOT)).run()
        if verdicts is not None:
            au.check_verdicts(verdicts)
        return au

    def test_01_visible_fields_invalidate_old_verdicts(self):
        mutations = {
            "label": lambda p: p["cv"]["sections"][-1]["items"][0].update(
                label="Ph.D. in Artificial Intelligence, awarded 2035"),
            "recipient": lambda p: p["letter"]["recipient"].__setitem__(0, "Avery Fabricant"),
            "date": lambda p: p["letter"].update(date="October 8, 2035"),
            "subject": lambda p: p["letter"].update(subject="Ph.D. in Computer Science, 2035, fluent in German"),
            "identity": lambda p: p["cv"].update(name="Avery Fabricant"),
            "signature": lambda p: p["letter"].update(signature="Avery Fabricant"),
        }
        for field, mutate in mutations.items():
            with self.subTest(field=field):
                p = self.package()
                mutate(p)
                self.assertTrue(self.audit(p, self.verdicts()).errors)
        p = self.package()
        p["letter"]["recipient"][0] = "Avery Fabricant"
        self.assertIn("E_RECIPIENT_UNSOURCED", {e["code"] for e in self.audit(p).errors})
        p = self.package()
        p["cv"]["sections"][-1]["items"][0]["label"] = "Tools actually used"
        self.assertIn("Tools actually used", check_docs.expectations(p, "cv"))

    def test_02_dossier_and_contract_facts_need_current_verdicts(self):
        mutations = {
            "profile_claim": lambda p: next(c for c in p["company_claims"] if c["id"] == "C6").update(
                text="Brindlewood raised 9000 million dollars in 2035 and employs 9000 engineers."),
            "new_claim": lambda p: p["company_claims"].append({"id": "C99", "status": "confirmed",
                "text": "Brindlewood acquired 9000 customers in 2035.", "sources": ["S1"]}),
            "contract": lambda p: p["job"]["contract"].update(start="2035-01"),
            "hiring_context": lambda p: p["strategy"]["hiring_context"].update(problem="Manage 9000 engineers"),
            "contribution": lambda p: p["strategy"]["contribution"].update(scope="Supervise 9000 engineers"),
        }
        for field, mutate in mutations.items():
            with self.subTest(field=field):
                p = self.package()
                mutate(p)
                self.assertTrue(self.audit(p, self.verdicts()).errors)

    def test_03_normalized_empty_quotes_are_not_verbatim(self):
        for excerpt in ("`", "***", ">", "#", "_", "   "):
            with self.subTest(excerpt=excerpt):
                v = self.verdicts()
                v["verdicts"][0]["excerpt"] = excerpt
                self.assertIn("E_VERDICT_EXCERPT", {e["code"] for e in self.audit(self.package(), v).errors})
                p = self.package()
                p["evidence"].append({"id": "E99", "title": "Management", "stage": "experience", "source": "S6",
                    "facts": ["Managed a regional recruiting team"], "tools": [], "metrics": [], "excerpts": [excerpt]})
                self.assertTrue(self.audit(p).errors)

    def partial_pdf(self, second):
        sentence = "Resolved device and account issues for library staff and patrons."
        streams = [b"BT /F1 11 Tf 50 700 Td (" + sentence.encode() + b") Tj ET",
                   b"BT /F1 11 Tf 50 680 Td <" + second.encode().hex().encode() + b"> Tj ET"]
        objects = [b"<< /Type /Catalog /Pages 2 0 R >>", b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
                   b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Resources "
                   b"<< /Font << /F1 6 0 R >> >> /Contents [4 0 R 5 0 R] >>"]
        for raw in streams:
            compressed = zlib.compress(raw)
            while compressed.endswith(b"\r"):
                raw += b" "
                compressed = zlib.compress(raw)
            objects.append(b"<< /Length %d /Filter /FlateDecode >>\nstream\n" % len(compressed) +
                           compressed + b"\nendstream")
        objects.append(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>")
        data, offsets = bytearray(b"%PDF-1.4\n"), []
        for i, body in enumerate(objects, 1):
            offsets.append(len(data))
            data += b"%d 0 obj\n" % i + body + b"\nendobj\n"
        xref = len(data)
        data += b"xref\n0 7\n0000000000 65535 f \n"
        for offset in offsets:
            data += b"%010d 00000 n \n" % offset
        data += b"trailer\n<< /Size 7 /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n" % xref
        path = self.folder / "partial.pdf"
        path.write_bytes(data)
        return path, sentence

    @mock.patch.object(check_docs, "independent_text", return_value=None)
    def test_04_partial_pdf_never_complete_and_changes_stale_verdicts(self, independent):
        path, sentence = self.partial_pdf("Work performed by Camille.")
        p = self.package()
        p["sources"].append({"id": "S9", "kind": "candidate", "url": str(path), "title": "CV PDF"})
        p["evidence"].append({"id": "E9", "title": "IT support", "stage": "experience", "source": "S9",
            "facts": [sentence], "tools": [], "metrics": [], "excerpts": [sentence]})
        bullet = p["cv"]["sections"][2]["items"][0]["bullets"][1]
        bullet["evidence"] = ["E9"]
        au = self.audit(p)
        self.assertFalse(au.verification()["complete"])
        reference = {v["target"]: v for v in self.verdicts()["verdicts"]}
        verdicts = []
        for t in au.targets():
            v = dict(reference[t["target"]], fingerprint=t["fingerprint"])
            if t["text"].startswith("Resolved device"):
                v.update(source="S9", excerpt=sentence)
            verdicts.append(v)
        self.partial_pdf("Correction: the device-support work belonged to a teammate, never to Camille.")
        self.assertIn("E_VERDICT_STALE", {e["code"] for e in self.audit(p, {"verdicts": verdicts}).errors})
        text = self.folder / "plaintext.md"
        text.write_bytes(b"FICTITIOUS source\nSame text\n")
        p["sources"][-1]["url"] = str(text)
        before = self.audit(p).source_digest("S9")
        text.write_bytes(b"FICTITIOUS source\r\nSame text\r\n")
        self.assertEqual(self.audit(p).source_digest("S9"), before)

    def test_05_conflicting_current_verdicts_fail_in_both_orders(self):
        package = self.write("package.json", self.package())
        first = self.write("audit.round1.json", self.verdicts())
        rejected = dict(self.verdicts()["verdicts"][0], verdict="unsupported", note="Not established by the sources")
        second = self.write("audit.round2.json", {"verdicts": [rejected]})
        for files in ((first, second), (second, first)):
            with self.subTest(files=files):
                r = self.run_script("audit_package.py", package, "--root", ROOT, "--verdicts", *files)
                self.assertEqual(r.returncode, 1)
                self.assertIn("E_VERDICT_CONFLICT", {e["code"] for e in json.loads(r.stdout)["errors"]})

    def hidden_docx(self, value):
        result = build_docs.build(self.package(), str(self.folder / "source"), only="cv", pdf=False)
        source = result["files"][0]["docx"]
        path = self.folder / ("hidden-" + value + ".docx")
        with zipfile.ZipFile(source) as z, zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as out:
            for name in z.namelist():
                content = z.read(name)
                if name == "word/styles.xml":
                    tag = b'<w:vanish w:val="' + value.encode() + b'"/>'
                    content = content.replace(b"<w:rPr><w:rFonts", b"<w:rPr>" + tag + b"<w:rFonts", 1)
                out.writestr(name, content)
        return path

    def test_06_styles_with_hidden_text_are_refused_but_false_is_allowed(self):
        for value, hidden in (("true", True), ("1", True), ("false", False), ("0", False)):
            with self.subTest(value=value):
                result = check_docs.check_file(str(self.hidden_docx(value)), "US", ["Camille Testard"], 2)
                self.assertEqual(any("hidden text" in e for e in result["errors"]), hidden)

    def test_07_mistyped_schema_cannot_fall_back_to_legacy(self):
        for schema in ("2", None, True, 2.0):
            with self.subTest(schema=schema):
                p = self.package()
                p["meta"]["schema"] = schema
                self.assertIn("E_STRUCTURE", {e["code"] for e in self.audit(p).errors})

    def test_08_provenance_metadata_and_posting_status_are_validated(self):
        for field, value in (("reachable", None), ("reachable", "false"), ("accessed", "2026-99-99"),
                             ("published", "2035-99-99")):
            with self.subTest(field=field, value=value):
                p = self.package()
                source = next(s for s in p["sources"] if s["id"] == "S2")
                if value is None:
                    source.pop(field)
                else:
                    source[field] = value
                self.assertTrue(self.audit(p).errors)
        p = self.package()
        p["job"]["posting_status"] = "confirmed-open"
        self.assertIn("E_POSTING_STATUS", {e["code"] for e in self.audit(p).errors})
        p = self.package()
        next(s for s in p["sources"] if s["id"] == "S2")["accessed"] = "2026-10-09"
        self.assertIn("E_VERDICT_STALE", {e["code"] for e in self.audit(p, self.verdicts()).errors})

    def test_09_bad_agent_types_give_located_json_diagnostics(self):
        mutations = {
            "meta": lambda p: p.update(meta=None),
            "dates": lambda p: p["cv"]["sections"][0]["items"][0].update(dates=2026),
            "evidence": lambda p: p["cv"]["sections"][1]["items"][0]["bullets"][0].update(evidence=[{"id": "E1"}]),
            "need": lambda p: p["strategy"]["arguments"][0].update(need=1),
            "cv.name": lambda p: p["cv"].update(name=None),
        }
        for field, mutate in mutations.items():
            with self.subTest(field=field):
                p = self.package()
                mutate(p)
                r = self.run_script("audit_package.py", self.write("bad.json", p), "--root", ROOT)
                self.assertNotIn("Traceback", r.stderr)
                errors = json.loads(r.stdout)["errors"]
                self.assertTrue(any(e["code"] == "E_STRUCTURE" and field in e["msg"] for e in errors), errors)
        for field in ("verdict", "source", "excerpt", "fingerprint"):
            with self.subTest(verdict_field=field):
                v = self.verdicts()
                v["verdicts"][0][field] = {"text": "agent output"}
                r = self.run_script("audit_package.py", self.write("package.json", self.package()),
                                    "--root", ROOT, "--verdicts", self.write("bad-verdict.json", v))
                self.assertNotIn("Traceback", r.stderr)
                errors = json.loads(r.stdout)["errors"]
                self.assertTrue(any(e["code"] == "E_STRUCTURE" and field in e["msg"] for e in errors), errors)

    def test_10_json_bom_is_accepted_by_all_three_scripts(self):
        path = self.write("bom.json", self.package(), encoding="utf-8-sig")
        r = self.run_script("audit_package.py", path, "--root", ROOT)
        self.assertEqual(r.returncode, 0, r.stderr + r.stdout)
        r = self.run_script("build_docs.py", path, "--out", self.folder / "docs")
        self.assertEqual(r.returncode, 0, r.stderr)
        files = [f[k] for f in json.loads(r.stdout)["files"] for k in ("docx", "pdf")]
        manifest = self.folder / "docs/build.json"
        manifest.write_text(manifest.read_text(encoding="utf-8"), encoding="utf-8-sig")
        r = self.run_script("check_docs.py", *files, "--package", path)
        self.assertEqual(r.returncode, 0, r.stderr + r.stdout)

    def test_11_direct_candidate_url_is_remote_not_missing_local_file(self):
        for scheme, registered in (("https", False), ("HTTPS", False), ("HTTPS", True)):
            with self.subTest(scheme=scheme, registered=registered):
                p = self.package()
                url = scheme + "://portfolio.camille-testard.example/cv"
                if registered:
                    p["sources"].append({"id": "S9", "kind": "candidate", "url": url, "title": "CV"})
                p["evidence"][3]["source"] = "S9" if registered else url
                au = self.audit(p)
                self.assertNotIn("E_SOURCE_MISSING", {e["code"] for e in au.errors})
                self.assertIn("W_EVIDENCE_UNCHECKED", {e["code"] for e in au.warnings})
                self.assertFalse(au.verification()["complete"])

    def test_12_candidate_name_cannot_change_document_kind(self):
        p = self.package()
        p["cv"]["name"] = "Camille Letterman"
        p["letter"]["signature"] = p["cv"]["name"]
        result = build_docs.build(p, str(self.folder))
        for record in result["files"]:
            for suffix in ("docx", "pdf"):
                self.assertEqual(check_docs.kind_of(record[suffix]), record["kind"])
                checked = check_docs.check_file(record[suffix], "US", check_docs.expectations(p, record["kind"]), 2)
                self.assertEqual(checked["errors"], [])
        self.assertEqual(check_docs.kind_of("Camille-Testard_Cover-Letter_CV.docx"), "letter")
        self.assertEqual(check_docs.kind_of("Resume_Cover-Letter_Brindlewood.pdf"), "letter")
        self.assertEqual(check_docs.kind_of("Cover-Letter_Resume_Brindlewood.pdf"), "cv")

    def test_13_uppercase_extensions_extract_the_same_text(self):
        result = build_docs.build(self.package(), str(self.folder), only="cv")
        for suffix in ("docx", "pdf"):
            path = self.folder / ("RESUME." + suffix.upper())
            shutil.copyfile(result["files"][0][suffix], path)
            r = self.run_script("check_docs.py", "--text", path)
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertIn("Camille Testard", r.stdout)
            self.assertEqual(check_docs.check_file(str(path), "US", ["Camille Testard"], 2)["errors"], [])

    def test_14_literal_globs_expand_and_empty_globs_are_diagnosed(self):
        path = self.write("package.json", self.package())
        build_docs.build(self.package(), str(self.folder / "docs with spaces"))
        r = self.run_script("check_docs.py", self.folder / "docs with spaces/*.docx",
                            self.folder / "docs with spaces/*.pdf", "--package", path)
        self.assertEqual(r.returncode, 0, r.stderr + r.stdout)
        self.assertEqual(sum(x["kind"] != "manifest" for x in json.loads(r.stdout)["results"]), 4)
        r = self.run_script("check_docs.py", self.folder / "missing/*.docx")
        self.assertEqual(r.returncode, 1)
        self.assertNotIn("Traceback", r.stderr)
        self.assertFalse(json.loads(r.stdout)["ok"])

    def test_15_adaptation_requires_each_lever_once(self):
        p = self.package()
        p["strategy"]["adaptation"] = [copy.deepcopy(p["strategy"]["adaptation"][0]) for _ in range(3)]
        self.assertIn("E_ADAPTATION_MISSING", {e["code"] for e in self.audit(p).errors})
        self.assertEqual(self.audit(self.package()).errors, [])
        # Exercise the e2e validator's predicate on offline fixture outputs; never launch Claude.
        import run_e2e
        output = self.folder / "brindlewood"
        output.mkdir()
        (self.folder / "brindlewood.run.json").write_text('{"returncode": 0}', encoding="utf-8")
        (output / "dossier.md").write_text("FICTITIOUS offline validator input", encoding="utf-8")
        for package, expected in ((p, False), (self.package(), True)):
            (output / "package.json").write_text(json.dumps(package), encoding="utf-8")
            build_docs.build(package, str(output))
            with mock.patch.object(run_e2e, "OUT", str(self.folder)):
                checked = run_e2e.validate("brindlewood")
            adaptation = next(c for c in checked["checks"] if c["check"] == "adaptation recorded per lever")
            self.assertIs(adaptation["ok"], expected)

    def test_16_create_requires_explicit_language(self):
        p = self.package()
        p["meta"]["mode"] = "create"
        p["meta"].pop("language")
        p.pop("letter")
        p.pop("interview")
        self.assertIn("E_LANGUAGE_MISSING", {e["code"] for e in self.audit(p).errors})

    def test_17_statutory_company_profiles_do_not_require_headcount(self):
        for kind, text in (("non-profit", "Brindlewood is a registered non-profit association under its statute."),
                           ("public-sector", "Brindlewood is a public body established by statute.")):
            with self.subTest(kind=kind):
                p = self.package()
                path = self.folder / "statute.md"
                path.write_text("<!-- FICTITIOUS -->\n" + text, encoding="utf-8")
                p["sources"].append({"id": "S99", "kind": "official", "url": "https://brindlewood-freight.example/legal",
                    "title": "Legal status", "published": "unknown", "accessed": "2026-10-08",
                    "reachable": True, "copy_path": str(path)})
                p["company_claims"].append({"id": "C99", "status": "confirmed", "text": text, "sources": ["S99"]})
                p["company_profile"].update(type=kind, basis=["C99"])
                self.assertEqual(self.audit(p).errors, [])

    def test_18_sync_check_reports_orphans_without_deleting_them(self):
        clone = self.folder / "project"
        for folder in (".claude/agents", ".codex/agents"):
            shutil.copytree(ROOT / folder, clone / folder)
        (clone / "tools").mkdir()
        shutil.copyfile(ROOT / "tools/sync_codex_agents.py", clone / "tools/sync_codex_agents.py")
        (clone / ".claude/agents/candidate-evidence.md").unlink()
        orphan = clone / ".codex/agents/candidate-evidence.toml"
        before = orphan.read_bytes()
        r = subprocess.run([sys.executable, str(clone / "tools/sync_codex_agents.py"), "--check"],
                           capture_output=True, encoding="utf-8")
        self.assertEqual(r.returncode, 1)
        self.assertIn("candidate-evidence.toml", r.stdout)
        self.assertEqual(orphan.read_bytes(), before)

    def located(self, au, code, where):
        return [e for e in au.errors if e["code"] == code and where in e["msg"]]

    def test_19_cv_sections_need_content_and_their_titles_are_audited(self):
        p = self.package()
        p["cv"]["sections"].append({"title": "Ph.D. in Computer Science awarded 2035", "items": []})
        au = self.audit(p, self.verdicts())
        self.assertTrue(self.located(au, "E_CV_EMPTY_SECTION", "cv.sections[4]"), au.errors)
        p = self.package()  # items that print nothing leave the title alone on the page
        p["cv"]["sections"].append({"title": "Awards", "items": [{"label": "", "text": " ", "evidence": ["E1"]}]})
        self.assertTrue(self.located(self.audit(p), "E_CV_EMPTY_SECTION", "cv.sections[4]"))
        p = self.package()  # a printed title is a statement: its numbers are checked like a heading's
        p["cv"]["sections"][0]["title"] = "Ph.D. in Computer Science awarded 2035"
        self.assertTrue(self.located(self.audit(p), "E_METRIC_UNSUPPORTED", "cv.sections[0].title"))
        p["cv"]["sections"][0]["title"] = "Ph.D. in Computer Science"  # and its wording is judged by the auditor
        au = self.audit(p)
        self.assertEqual(au.errors, [])
        title = {t["target"]: t for t in au.targets()}["cv.sections[0].title"]
        self.assertEqual((title["text"], title["sources"]), ("Ph.D. in Computer Science", ["S5"]))
        au.check_verdicts(self.verdicts())  # the reference verdict judged "Education"
        self.assertTrue(self.located(au, "E_VERDICT_STALE", "cv.sections[0].title:"), au.errors)
        p = self.package()  # titles get the text checks of every printed CV line
        p["cv"]["sections"][1]["title"] = "Kubernetes Projects"
        self.assertTrue(self.located(self.audit(p), "E_GAP_IN_CV", "'Kubernetes'"))
        p = self.package()
        p["cv"]["sections"][3]["title"] = "Skills and fluent German"
        self.assertTrue({t["target"]: t for t in self.audit(p).targets()}["cv.sections[3].title"]["level"])

    def test_20_interview_question_is_part_of_the_audited_statement(self):
        p = self.package()
        p["interview"][0]["question"] = "How did you use your doctorate to lead the engineering department?"
        au = self.audit(p, self.verdicts())
        self.assertTrue(self.located(au, "E_VERDICT_STALE", "interview[0]:"), au.errors)
        text = {t["target"]: t for t in au.targets()}["interview[0]"]["text"]
        self.assertIn("doctorate", text)
        self.assertIn(p["interview"][0]["talking_points"], text)
        p["interview"][0]["question"] = ["How did you lead the department?"]  # now joined: must be text
        self.assertTrue(self.located(self.audit(p), "E_STRUCTURE", "interview[0].question"))

    def test_21_strategy_gaps_and_differentiation_are_audited_with_their_references(self):
        p = self.package()
        p["strategy"]["gaps"].append("Holds the Certified Kubernetes Administrator certification")
        p["strategy"]["differentiation"] = "Only applicant with a doctorate from MIT."
        au = self.audit(p, self.verdicts())
        self.assertTrue(self.located(au, "E_VERDICT_COVERAGE", "strategy.gaps[2]"), au.errors)
        self.assertTrue(self.located(au, "E_VERDICT_STALE", "strategy.differentiation:"), au.errors)
        targets = {t["target"]: t for t in self.audit(self.package()).targets()}
        self.assertEqual(targets["strategy.gaps[0]"]["sources"], ["S4", "S5", "S6"])  # candidate files + posting
        self.assertIn("S3", targets["strategy.differentiation"]["sources"])  # company facts it may compare
        v = self.verdicts()  # a gap verdict cannot quote a company page outside its references
        next(x for x in v["verdicts"] if x["target"] == "strategy.gaps[0]").update(
            source="S1", excerpt="Brindlewood Freight Labs")
        self.assertTrue(self.located(self.audit(self.package(), v), "E_VERDICT_SOURCE", "strategy.gaps[0]:"))
        p = self.package()  # the requirement a gap answers is part of its fingerprint
        next(r for r in p["job"]["requirements"] if r["id"] == "R5")["text"] = "Kubernetes certification (CKA)"
        self.assertTrue(self.located(self.audit(p, self.verdicts()), "E_VERDICT_STALE", "strategy.gaps[0]:"))
        p = self.package()
        p["strategy"]["gaps"].append("Kubernetes: certified in 2035")
        self.assertTrue(self.located(self.audit(p), "E_METRIC_UNSUPPORTED", "strategy.gaps[2]"))
        p = self.package()
        p["strategy"]["differentiation"] += " Brindlewood has 2035 carriers."
        self.assertTrue(self.located(self.audit(p), "E_METRIC_UNSUPPORTED", "strategy.differentiation"))

    def test_22_letter_dates_are_not_estimated_figures(self):
        # E4: "Supervisor estimated about 2 hours"; E1: a survey "from about 25 minutes to about 10 minutes"
        for date in ("October 2, 2026", "Oct. 2, 2026", "October 10, 2026", "2 October 2026", "Le 2 octobre 2026",
                     "1er octobre 2026", "2026-10-08", "10/02/2026"):
            with self.subTest(date=date):
                p = self.package()
                p["letter"]["date"] = date
                self.assertEqual(self.audit(p).errors, [])
        p = self.package()  # the rest of the header is still checked
        p["letter"]["subject"] = "Application: saved 2 hours of staff time per week"
        self.assertTrue(self.located(self.audit(p), "E_ESTIMATE_AS_MEASURE", "letter.header"))
        p = self.package()  # a date next to a bare estimate does not hide it
        p["letter"]["paragraphs"][2]["text"] += " On October 2, 2026, the script still saved 2 hours of staff time."
        self.assertTrue(self.located(self.audit(p), "E_ESTIMATE_AS_MEASURE", "letter.paragraphs[2]"))

    def test_23_generation_settings_are_validated_before_generation(self):
        bad = {("meta", "margin_in"): [[], None, "0.7", True, 0.2, 1.5, float("nan")],
               ("meta", "paper"): [["a4"], "A5"], ("meta", "font"): ["Comic Sans", ["Arial"]],
               ("meta", "market"): [None, ["US"]], ("meta", "fit"): ["false"],
               ("meta", "max_cv_pages"): ["two", 0, True], ("cv", "name_size"): [[], "17"]}
        for (block, key), values in bad.items():
            for value in values:
                with self.subTest(key=key, value=value):
                    p = self.package()
                    p[block][key] = value
                    where = "%s.%s" % (block, key)
                    self.assertTrue(self.located(self.audit(p), "E_STRUCTURE", where), self.audit(p).errors)
                    with self.assertRaises(SystemExit) as raised:
                        build_docs.build(p, str(self.folder / "never"))
                    self.assertIn(where, str(raised.exception.code))
                    self.assertFalse((self.folder / "never").exists())
        for key, value in (("margin_in", 0.5), ("margin_in", 1), ("margin_in", 1.0), ("paper", "a4"),
                           ("font", "Calibri"), ("fit", False), ("max_cv_pages", 1)):
            with self.subTest(valid=key, value=value):
                p = self.package()
                p["meta"][key] = value
                self.assertEqual(self.audit(p).errors, [])
        p = self.package()
        p["meta"]["margin_in"] = []
        r = self.run_script("build_docs.py", self.write("bad-margin.json", p), "--out", self.folder / "cli")
        self.assertNotEqual(r.returncode, 0)
        self.assertNotIn("Traceback", r.stderr)
        self.assertIn("meta.margin_in", r.stderr)

    def test_24_e2e_validator_reads_every_audit_round(self):
        import run_e2e
        output = self.folder / "brindlewood"
        output.mkdir()
        p = self.package()
        p["letter"]["closing"] = "Best regards,"
        (output / "package.json").write_text(json.dumps(p), encoding="utf-8")
        reference = self.verdicts()
        (output / "audit.json").write_text(json.dumps(reference), encoding="utf-8")
        before = {v["target"]: v["fingerprint"] for v in reference["verdicts"]}
        fresh = {t["target"]: t["fingerprint"] for t in self.audit(p).targets()}
        self.assertEqual([t for t, f in fresh.items() if before.get(t) != f], ["letter.header"])
        header = dict(next(v for v in reference["verdicts"] if v["target"] == "letter.header"),
                      fingerprint=fresh["letter.header"])
        for verdict, expected in (("supported", True), ("unsupported", False)):  # FICTITIOUS re-audit round
            with self.subTest(verdict=verdict):
                (output / "audit.round1.json").write_text(json.dumps({"verdicts": [dict(header, verdict=verdict)]}),
                                                          encoding="utf-8")
                with mock.patch.object(run_e2e, "OUT", str(self.folder)):
                    checked = run_e2e.validate("brindlewood")
                row = next(c for c in checked["checks"] if c["check"].startswith("application-auditor verdicts"))
                self.assertIs(row["ok"], expected, row["detail"])


if __name__ == "__main__":
    unittest.main()
