#!/usr/bin/env python3
"""Offline regression tests for the cv-ats-us skill (stdlib unittest, fictitious data only).

  python3 tests/run_tests.py            # all offline tests
  python3 tests/run_tests.py -v         # verbose
Live pipeline tests (real Claude Code run, costs tokens): tests/e2e/run_e2e.py
"""
import copy
import itertools
import json
import os
import re
import subprocess
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SKILL = os.path.join(ROOT, ".claude", "skills", "cv-ats-us")
AGENTS = os.path.join(ROOT, ".claude", "agents")
SCRIPTS = os.path.join(SKILL, "scripts")
PKGS = os.path.join(ROOT, "tests", "fixtures", "packages")
sys.path.insert(0, SCRIPTS)
import audit_package  # noqa: E402
import build_docs  # noqa: E402
import check_docs  # noqa: E402

AGENT_NAMES = ["company-researcher", "job-intelligence", "candidate-evidence", "recruitment-strategist",
               "application-auditor"]
WRITE_TOOLS = {"Write", "Edit", "NotebookEdit", "Bash", "PowerShell", "Agent"}
MODELS = {"inherit", "sonnet", "opus", "haiku", "fable"}
PACKAGES = ["brindlewood", "halvane", "tamberlin", "orvanta", "quarrelane"]
US_SAME_TITLE = ["brindlewood", "halvane", "tamberlin", "orvanta"]  # same candidate, "Junior Software Engineer"
COMPANY_TYPES = {"brindlewood": "startup", "halvane": "mid-size", "tamberlin": "sme", "orvanta": "multinational",
                 "quarrelane": "unknown"}


def frontmatter(path):
    text = open(path, encoding="utf-8").read()
    m = re.match(r"^---\n(.*?)\n---\n", text, re.S)
    assert m, "%s: frontmatter must start on line 1" % path
    fm = {}
    for line in m.group(1).splitlines():
        k, _, v = line.partition(":")
        fm[k.strip()] = v.strip().strip('"')
    return fm, text[m.end():]


def load(name):
    with open(os.path.join(PKGS, name + ".json"), encoding="utf-8") as fh:
        return json.load(fh)


def audit(pkg, other=None):
    au = audit_package.Audit(pkg).run()
    errors = list(au.errors)
    if other is not None:
        errors += audit_package.compare(pkg, other)["errors"]
    return {e["code"] for e in errors}, au


class ConfigTests(unittest.TestCase):
    def test_skill_frontmatter(self):
        fm, body = frontmatter(os.path.join(SKILL, "SKILL.md"))
        self.assertEqual(fm["name"], "cv-ats-us")
        self.assertRegex(fm["name"], r"^[a-z0-9-]+$")
        self.assertLessEqual(len(fm["description"]) + len(fm.get("when_to_use", "")), 1536)
        self.assertLess(len(body.splitlines()), 500)
        self.assertFalse(set(re.split(r"[\s,]+", fm.get("allowed-tools", ""))) & WRITE_TOOLS,
                         "skill must not pre-approve write/exec tools")

    def test_agents_frontmatter_and_least_privilege(self):
        found = sorted(f[:-3] for f in os.listdir(AGENTS) if f.endswith(".md"))
        self.assertEqual(found, sorted(AGENT_NAMES))
        for name in AGENT_NAMES:
            fm, body = frontmatter(os.path.join(AGENTS, name + ".md"))
            self.assertEqual(fm["name"], name)
            self.assertGreater(len(fm["description"]), 80)
            self.assertEqual(fm["model"], "haiku", "policy: big orchestrator, Haiku 5.5 subagents")
            tools = {t.strip() for t in fm["tools"].split(",")}
            self.assertFalse(tools & WRITE_TOOLS, "%s must be read-only: %s" % (name, tools & WRITE_TOOLS))
            self.assertIn("Output", body)

    def test_codex_agents_generated_and_small_model(self):
        r = subprocess.run([sys.executable, os.path.join(ROOT, "tools", "sync_codex_agents.py"), "--check"],
                           capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, "run tools/sync_codex_agents.py: " + r.stdout)
        for name in AGENT_NAMES:
            with open(os.path.join(ROOT, ".codex", "agents", name + ".toml"), encoding="utf-8") as fh:
                toml = fh.read()
            self.assertIn('name = "%s"' % name, toml)
            self.assertIn('model = "gpt-6-luna"', toml)
            self.assertIn('sandbox_mode = "read-only"', toml)
            self.assertIn("developer_instructions = '''", toml)

    def test_codex_skill_is_a_symlink_not_a_copy(self):
        link = os.path.join(ROOT, ".agents", "skills", "cv-ats-us")
        self.assertTrue(os.path.islink(link))
        self.assertEqual(os.path.realpath(link), os.path.realpath(SKILL))

    def test_links_and_scripts_resolve(self):
        files = [os.path.join(SKILL, "SKILL.md")] + [os.path.join(SKILL, "references", f)
                                                     for f in os.listdir(os.path.join(SKILL, "references"))]
        for f in files:
            text = open(f, encoding="utf-8").read()
            for link in re.findall(r"\]\(([^)#\s]+)\)", text):
                if not link.startswith("http"):
                    self.assertTrue(os.path.exists(os.path.join(os.path.dirname(f), link)), "%s -> %s" % (f, link))
            for script in re.findall(r"\$\{CLAUDE_SKILL_DIR\}/(scripts/[\w.]+)", text):
                self.assertTrue(os.path.exists(os.path.join(SKILL, script)), script)
        for ref in ("university-guidelines", "ats-and-layout", "recruiting-framework", "project-evidence",
                    "cover-letter", "source-policy", "package-format", "company-context"):
            self.assertTrue(os.path.exists(os.path.join(SKILL, "references", ref + ".md")), ref)

    def test_no_competing_user_skill_and_outputs_ignored(self):
        for user_skill in ("~/.claude/skills/cv-ats-us", "~/.agents/skills/cv-ats-us"):
            user_skill = os.path.expanduser(user_skill)
            if os.path.exists(user_skill):  # allowed only as a link to this skill: a copy would shadow and drift
                self.assertEqual(os.path.realpath(user_skill), os.path.realpath(SKILL),
                                 "%s is a copy that shadows the project skill" % user_skill)
        self.assertEqual(os.path.realpath(os.path.join(ROOT, "SKILL.md")),
                         os.path.realpath(os.path.join(SKILL, "SKILL.md")), "root SKILL.md must link to the skill")
        for name in AGENT_NAMES:
            user_agent = os.path.expanduser("~/.claude/agents/%s.md" % name)
            if os.path.exists(user_agent):
                self.assertEqual(os.path.realpath(user_agent), os.path.realpath(os.path.join(AGENTS, name + ".md")),
                                 "user-level %s must link to the project agent, not copy it" % name)
            codex_agent = os.path.expanduser("~/.codex/agents/%s.toml" % name)
            if os.path.exists(codex_agent):
                self.assertEqual(os.path.realpath(codex_agent),
                                 os.path.realpath(os.path.join(ROOT, ".codex", "agents", name + ".toml")),
                                 "user-level Codex %s must link to the generated project agent" % name)
        self.assertIn("applications/", open(os.path.join(ROOT, ".gitignore")).read())

    def test_university_attribution_guard(self):
        text = open(os.path.join(SKILL, "references", "university-guidelines.md"), encoding="utf-8").read()
        self.assertIn("2026-10-08", text)
        for url in ("careerservices.fas.harvard.edu", "capd.mit.edu", "career.berkeley.edu", "ocs.yale.edu"):
            self.assertIn(url, text)


class PrivacyTests(unittest.TestCase):
    def scan_files(self):
        for base in ("tests", ".claude", "README.md"):
            path = os.path.join(ROOT, base)
            walk = [(path, [], [""])] if os.path.isfile(path) else os.walk(path)
            for d, _, fs in walk:
                for f in fs:
                    p = os.path.join(d, f)
                    if p.endswith((".md", ".json")):  # data and docs; code is not personal data
                        with open(p, encoding="utf-8") as fh:
                            yield p, fh.read()

    def test_fixtures_are_fictitious(self):
        for p, text in self.scan_files():
            for email in re.findall(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+", text):
                self.assertTrue(email.endswith(("example.com", ".example")), "%s: %s" % (p, email))
            for phone in re.findall(r"\+?\d[\d ().-]{8,}\d", text):
                digits = re.sub(r"\D", "", phone)
                if len(digits) >= 10 and not re.match(r"20\d{6}", digits):
                    self.assertIn("555", digits, "%s: non-fictitious phone %s" % (p, phone))
            self.assertNotRegex(text, r"sk-ant-[\w-]{10,}|AKIA[0-9A-Z]{16}|ghp_[\w]{20,}")

    def test_fixture_urls_never_resolve(self):
        for name in PACKAGES:
            for s in load(name)["sources"]:
                if s["url"].startswith("http"):
                    self.assertRegex(s["url"], r"^https://[^/]+\.(example|invalid)(/|$)", s["url"])


class DocumentTests(unittest.TestCase):
    """(f) structured CV/letter, DOCX + PDF built and text extractable."""

    def build_and_check(self, name):
        pkg = load(name)
        out = tempfile.mkdtemp(prefix="cvats-")
        res = build_docs.build(pkg, out)
        files = [f[k] for f in res["files"] for k in ("docx", "pdf")]
        self.assertEqual(len(files), 4)
        market = pkg["meta"]["market"]
        for f in files:
            r = check_docs.check_file(f, market, check_docs.expectations(pkg, check_docs.kind_of(f)), 2)
            self.assertEqual(r["errors"], [], "%s: %s" % (f, r["errors"]))
            self.assertIn(r["paper"], check_docs.MARKET_PAPER[market])
            if f.endswith(".pdf"):
                self.assertEqual(r["pages"], 1)
        return pkg, res, files

    def test_f_us_documents(self):
        for name in US_SAME_TITLE:
            _, res, _ = self.build_and_check(name)
            self.assertEqual(res["paper"], "letter")

    def test_f_fr_documents_a4_and_accents(self):
        pkg, res, files = self.build_and_check("quarrelane")
        self.assertEqual(res["paper"], "a4")
        pdf_text = check_docs.pdf_info([f for f in files if "CV" in f and f.endswith(".pdf")][0])["text"]
        self.assertIn("EXPÉRIENCE", pdf_text)
        self.assertIn("COMPÉTENCES", pdf_text)

    def test_f_docx_has_no_layout_hazards(self):
        _, _, files = self.build_and_check("brindlewood")
        import zipfile
        for f in files:
            if f.endswith(".docx"):
                xml = zipfile.ZipFile(f).read("word/document.xml").decode()
                for bad in ("<w:tbl", "<w:drawing", "<w:txbxContent", "<w:vanish", "headerReference"):
                    self.assertNotIn(bad, xml)

    def test_f_reading_order_heading_before_dates(self):
        _, _, files = self.build_and_check("quarrelane")
        text = check_docs.pdf_info([f for f in files if "CV" in f and f.endswith(".pdf")][0])["text"]
        flat = re.sub(r"\s+", " ", text)
        self.assertIn("équipe de 3) janv. 2026", flat)

    def test_f_cv_fills_one_page(self):
        for name in PACKAGES:
            res = build_docs.build(load(name), tempfile.mkdtemp(prefix="cvats-fit-"), only="cv")
            fit = res["files"][0]["fit"]
            self.assertEqual(fit["pages"], 1, name)
            self.assertGreaterEqual(fit["fill"], 0.9, "%s: %s" % (name, fit))
            self.assertTrue(10 <= fit["body_pt"] <= 12, fit)

    def test_f_underfilled_cv_warns_and_full_cv_does_not(self):
        out = tempfile.mkdtemp(prefix="cvats-under-")
        self.assertNotIn("warning", build_docs.build(load("brindlewood"), out, only="cv")["files"][0]["fit"])
        thin = load("brindlewood")
        thin["cv"]["sections"] = [s for s in thin["cv"]["sections"] if s["title"] != "Projects"]
        fit = build_docs.build(thin, out, only="cv")["files"][0]["fit"]
        self.assertLess(fit["fill"], build_docs.MIN_FILL)
        self.assertIn("evidence-backed content", fit["warning"])

    def test_f_letter_fills_one_page(self):
        for name in PACKAGES:
            res = build_docs.build(load(name), tempfile.mkdtemp(prefix="cvats-lfit-"), only="letter")
            fit = res["files"][0]["fit"]
            self.assertEqual(fit["pages"], 1, name)
            self.assertGreaterEqual(fit["fill"], 0.85, "%s: %s" % (name, fit))

    def test_f_fit_can_be_disabled(self):
        pkg = load("brindlewood")
        pkg["meta"]["fit"] = False
        res = build_docs.build(pkg, tempfile.mkdtemp(prefix="cvats-nofit-"), only="cv")
        self.assertNotIn("fit", res["files"][0])
        import zipfile
        xml = zipfile.ZipFile(res["files"][0]["docx"]).read("word/document.xml").decode()
        self.assertIn('<w:sz w:val="22"/>', xml)

    def test_f_french_colon_has_nonbreaking_space(self):
        _, _, files = self.build_and_check("quarrelane")
        docx = [f for f in files if "CV" in f and f.endswith(".docx")][0]
        text = check_docs.docx_text(docx)
        self.assertIn("Outils : ", text)
        self.assertNotIn("Outils: ", text)
        us = check_docs.docx_text([f for f in self.build_and_check("brindlewood")[2] if f.endswith(".docx")
                                   and "Resume" in f][0])
        self.assertIn("Data and tools: ", us)

    def test_f_label_repeating_section_title_is_dropped(self):
        pkg = load("brindlewood")
        skills = [s for s in pkg["cv"]["sections"] if s["title"] == "Skills"][0]
        skills["items"][0]["label"] = "Skills"
        res = build_docs.build(pkg, tempfile.mkdtemp(prefix="cvats-label-"), only="cv")
        text = check_docs.docx_text(res["files"][0]["docx"])
        self.assertNotIn("Skills: ", text)
        self.assertIn("Python, SQL, JavaScript", text)
        self.assertIn("Data and tools: ", text)  # other labels kept

    def test_f_docx_dates_break_like_pdf_when_heading_is_long(self):
        _, _, files = self.build_and_check("quarrelane")
        import zipfile
        xml = zipfile.ZipFile([f for f in files if "CV" in f and f.endswith(".docx")][0]).read("word/document.xml")
        para = re.search(rb"<w:p>(?:(?!</w:p>).)*RouteWise(?:(?!</w:p>).)*</w:p>", xml).group(0)
        self.assertIn(b"<w:br/><w:tab/>", para)

    def test_cli_entrypoints(self):
        out = tempfile.mkdtemp(prefix="cvats-cli-")
        pkg = os.path.join(PKGS, "halvane.json")
        r = subprocess.run([sys.executable, os.path.join(SCRIPTS, "build_docs.py"), pkg, "--out", out],
                           capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stderr)
        r = subprocess.run([sys.executable, os.path.join(SCRIPTS, "check_docs.py"), "--package", pkg] +
                           [os.path.join(out, f) for f in os.listdir(out)], capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stdout)
        r = subprocess.run([sys.executable, os.path.join(SCRIPTS, "audit_package.py"), pkg],
                           capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stdout)


class AuditTests(unittest.TestCase):
    def assertFlags(self, pkg, code, other=None):
        codes, _ = audit(pkg, other)
        self.assertIn(code, codes)

    def test_golden_packages_pass(self):
        for name in PACKAGES:
            codes, au = audit(load(name))
            self.assertEqual(codes, set(), "%s: %s" % (name, au.errors))

    # (a) same candidate, two companies
    def test_a_two_companies_are_differentiated(self):
        b, h = load("brindlewood"), load("halvane")
        cmp_ = audit_package.compare(b, h)
        self.assertEqual(cmp_["errors"], [])
        self.assertLess(cmp_["letter_similarity"], 0.5)
        lead = lambda p: p["strategy"]["arguments"][0]["evidence"]
        self.assertNotEqual(lead(b), lead(h))
        first_project = lambda p: [s for s in p["cv"]["sections"] if s["title"] == "Projects"][0]["items"][0]["heading"]
        self.assertNotEqual(first_project(b), first_project(h))

    def test_a_rebadged_letter_is_rejected(self):
        b, h = load("brindlewood"), load("halvane")
        fake = copy.deepcopy(b)
        fake["meta"].update(company=h["meta"]["company"], role=h["meta"]["role"])
        for p in fake["letter"]["paragraphs"]:
            p["text"] = p["text"].replace("Brindlewood Freight Labs", h["meta"]["company"]).replace("Brindlewood", "Halvane")
        self.assertFlags(b, "E_REBADGED", other=fake)

    # (b) poorly documented company
    def test_b_limited_research_requires_flag(self):
        q = load("quarrelane")
        self.assertEqual(q["meta"]["research_level"], "limited")
        q["meta"]["research_level"] = "standard"
        self.assertFlags(q, "E_RESEARCH_LEVEL")

    def test_b_unavailable_claim_cannot_be_used(self):
        q = load("quarrelane")
        q["letter"]["paragraphs"][0]["claims"].append("C3")
        self.assertFlags(q, "E_CLAIM_UNAVAILABLE_USED")

    def test_b_hypothesis_must_be_hedged(self):
        b = load("brindlewood")
        b["letter"]["paragraphs"][4]["text"] = ("The Routing team is now focused on helping more carriers adopt "
                                                 "the Lanes API, and I will contribute tested endpoints.")
        self.assertFlags(b, "E_HYPOTHESIS_AS_FACT")

    # (c) required technology missing
    def test_c_missing_technology_never_in_cv(self):
        b = load("brindlewood")
        b["cv"]["sections"][-1]["items"][1]["text"] += ", Kubernetes"
        self.assertFlags(b, "E_GAP_IN_CV")
        q = load("quarrelane")
        q["cv"]["sections"][-1]["items"][0]["text"] += ", pandas"
        self.assertFlags(q, "E_GAP_IN_CV")

    def test_c_gap_in_letter_only_when_addressed(self):
        b = load("brindlewood")
        b["letter"]["paragraphs"][3]["addresses_gap"] = False
        self.assertFlags(b, "E_GAP_IN_LETTER")

    # (d) project without metrics
    def test_d_no_invented_metric_on_unmeasured_project(self):
        h = load("halvane")
        proj = [s for s in h["cv"]["sections"] if s["title"] == "Projects"][0]
        shelf = [i for i in proj["items"] if i["heading"].startswith("ShelfScan")][0]
        shelf["bullets"][0]["text"] += ", reaching 92% accuracy"
        self.assertFlags(h, "E_METRIC_UNSUPPORTED")
        h = load("halvane")
        h["letter"]["paragraphs"][2]["text"] += " It detected 87% of empty facings."
        self.assertFlags(h, "E_METRIC_UNSUPPORTED")

    # (e) unreachable site
    def test_e_unreachable_source_cannot_confirm(self):
        q = load("quarrelane")
        self.assertIs([s for s in q["sources"] if s["id"] == "S1"][0]["reachable"], False)
        q["company_claims"][0]["sources"] = ["S1"]
        self.assertFlags(q, "E_CLAIM_UNREACHABLE")

    def test_e_pasted_copy_cannot_revive_dead_url(self):
        q = load("quarrelane")
        q["sources"].append({"id": "S9", "kind": "user-provided", "url": q["sources"][0]["url"], "title": "copy",
                             "published": "unknown", "accessed": "2026-10-08", "reachable": True})
        self.assertFlags(q, "E_SOURCE_CONTRADICTION")

    def test_e_unverified_posting_must_be_flagged(self):
        q = load("quarrelane")
        q["meta"]["warnings"] = []
        self.assertFlags(q, "E_POSTING_STATUS")

    def test_letter_under_300_words(self):
        for name in PACKAGES:
            _, au = audit(load(name))
            self.assertLessEqual(au.letter_words, 300, name)
        b = load("brindlewood")
        words = sum(len(re.findall(r"\b[\w'’-]+\b", p["text"])) for p in b["letter"]["paragraphs"])
        b["letter"]["paragraphs"][2]["text"] += " Extra" * (301 - words)
        self.assertFlags(b, "E_LETTER_LENGTH")
        b["letter"]["paragraphs"][2]["text"] = b["letter"]["paragraphs"][2]["text"][:-len(" Extra")]
        codes, _ = audit(b)
        self.assertNotIn("E_LETTER_LENGTH", codes)

    def test_unmeasured_figures_without_disclaimers(self):
        b = load("brindlewood")
        b["cv"]["sections"][1]["items"][0]["bullets"][2]["text"] += " (self-reported; no other measurement)"
        self.assertFlags(b, "E_DISCLAIMER")
        b = load("brindlewood")
        b["letter"]["paragraphs"][1]["text"] += " It is their own estimate and the only measurement, so I present it as such."
        self.assertFlags(b, "E_DISCLAIMER")
        q = load("quarrelane")
        q["cv"]["sections"][1]["items"][0]["bullets"][2]["text"] += " (non mesuré)"
        self.assertFlags(q, "E_DISCLAIMER")

    def test_no_source_citations_inside_letter(self):
        h = load("halvane")
        h["letter"]["paragraphs"][1]["text"] += " (company blog, dated 2026-04-15)"
        self.assertFlags(h, "E_CITATION_IN_LETTER")
        h = load("halvane")
        h["letter"]["paragraphs"][1]["text"] += " See https://halvane-retail.example/blog."
        self.assertFlags(h, "E_CITATION_IN_LETTER")

    def test_french_letter_needs_objet(self):
        q = load("quarrelane")
        q["letter"]["subject"] = "Candidature au poste de développeur Python junior"
        self.assertFlags(q, "E_FR_SUBJECT")
        codes, _ = audit(load("brindlewood"))  # English letters are not concerned
        self.assertNotIn("E_FR_SUBJECT", codes)

    # generic guardrails
    def test_unsourced_confirmed_claim(self):
        b = load("brindlewood")
        b["company_claims"][1]["sources"] = []
        self.assertFlags(b, "E_CLAIM_UNSOURCED")

    def test_cv_line_without_evidence(self):
        b = load("brindlewood")
        b["cv"]["sections"][1]["items"][0]["bullets"][0]["evidence"] = []
        self.assertFlags(b, "E_CV_UNSUPPORTED")

    def test_invented_recruiter_name(self):
        b = load("brindlewood")
        b["letter"]["salutation"] = "Dear Ms. Alvarez,"
        b["letter"]["recipient"] = ["Dana Alvarez", "Brindlewood Freight Labs"]
        self.assertFlags(b, "E_RECIPIENT_UNSOURCED")

    def test_no_ats_score_or_placeholder(self):
        b = load("brindlewood")
        b["cv"]["headline"] += " | ATS score optimized"
        self.assertFlags(b, "E_ATS_PROMISE")
        b = load("brindlewood")
        b["letter"]["paragraphs"][0]["text"] += " [Company name] is great."
        self.assertFlags(b, "E_PLACEHOLDER")


class CompanyContextTests(unittest.TestCase):
    """Same candidate, same title, five company contexts: adaptation follows verified needs, never size alone."""

    def assertFlags(self, pkg, code):
        self.assertIn(code, audit(pkg)[0])

    def test_company_type_rests_on_a_confirmed_fact(self):
        for name, expected in COMPANY_TYPES.items():
            pkg = load(name)
            self.assertEqual(pkg["company_profile"]["type"], expected, name)
            claims = {c["id"]: c for c in pkg["company_claims"]}
            for c in pkg["company_profile"]["basis"]:
                self.assertEqual(claims[c]["status"], "confirmed", name)
        self.assertEqual(load("quarrelane")["company_profile"]["basis"], [])

    def test_customer_size_is_not_company_size(self):
        q = load("quarrelane")  # C1: dashboards *for* SMEs
        q["company_profile"].update(type="sme", basis=["C1"])
        self.assertFlags(q, "E_PROFILE_UNSOURCED")
        h = load("halvane")  # C1: software for mid-size grocery chains
        h["company_profile"]["basis"] = ["C1"]
        self.assertFlags(h, "E_PROFILE_UNSOURCED")
        b = load("brindlewood")  # a hypothesis cannot set the type
        b["company_profile"]["basis"] = ["C5"]
        self.assertFlags(b, "E_PROFILE_UNSOURCED")

    def test_size_alone_cannot_justify_an_adaptation(self):
        for name in US_SAME_TITLE:
            pkg = load(name)
            pkg["strategy"]["adaptation"][0]["basis"] = list(pkg["company_profile"]["basis"])
            self.assertFlags(pkg, "E_SIZE_ONLY")

    def test_adaptation_required_and_traced(self):
        b = load("brindlewood")
        b["strategy"]["adaptation"] = []
        self.assertFlags(b, "E_ADAPTATION_MISSING")
        b = load("brindlewood")
        b["strategy"]["adaptation"][1]["basis"] = ["C99"]
        self.assertFlags(b, "E_ADAPTATION_UNSUPPORTED")
        q = load("quarrelane")
        q["strategy"]["adaptation"][0]["basis"].append("C3")  # unavailable claim
        self.assertFlags(q, "E_ADAPTATION_UNSUPPORTED")

    def test_size_cliches_rejected(self):
        for name, sentence in (("brindlewood", "I thrive in a fast-paced startup and like to wear many hats."),
                               ("orvanta", "I would be proud to join a global leader like yours."),
                               ("tamberlin", "I am drawn to a company of your size."),
                               ("halvane", "A large company like yours offers structure."),
                               ("quarrelane", "J'apprécie votre esprit start-up.")):
            pkg = load(name)
            pkg["letter"]["paragraphs"][0]["text"] += " " + sentence
            self.assertFlags(pkg, "E_SIZE_CLICHE")

    def test_group_letter_names_the_hiring_unit(self):
        warns = lambda p: {w["code"] for w in audit(p)[1].warnings}
        o = load("orvanta")
        self.assertNotIn("W_UNIT_ABSENT", warns(o))
        o["company_profile"]["unit"] = "Orvanta Thermal Controls"
        self.assertIn("W_UNIT_ABSENT", warns(o))

    def test_same_title_four_company_types_are_differentiated(self):
        pkgs = {n: load(n) for n in US_SAME_TITLE}
        args = lambda p: [tuple(a["evidence"]) for a in p["strategy"]["arguments"]]
        bullets = lambda p: {b["text"] for s in p["cv"]["sections"] for i in s["items"] for b in i.get("bullets", [])}
        for a, b in itertools.combinations(US_SAME_TITLE, 2):
            cmp_ = audit_package.compare(pkgs[a], pkgs[b])
            self.assertEqual(cmp_["errors"], [], (a, b))
            self.assertLess(cmp_["letter_similarity"], 0.5, (a, b))
            self.assertNotIn("W_SAME_ADAPTATION", {w["code"] for w in cmp_["warnings"]}, (a, b))
            self.assertNotEqual(args(pkgs[a]), args(pkgs[b]), (a, b))
            self.assertNotEqual(pkgs[a]["cv"]["headline"], pkgs[b]["cv"]["headline"], (a, b))
            self.assertNotEqual(bullets(pkgs[a]), bullets(pkgs[b]), (a, b))

    def test_adaptation_is_visible_in_the_cv(self):
        def lead(p):  # first entry after Education
            for s in p["cv"]["sections"]:
                if s["title"] not in ("Education", "Formation") and s["items"][0].get("heading"):
                    return s["items"][0]["heading"]
        expected = {"brindlewood": "RouteWise", "halvane": "AltCheck", "tamberlin": "IT Support",
                    "orvanta": "RouteWise"}
        for name, start in expected.items():
            self.assertTrue(lead(load(name)).startswith(start), (name, lead(load(name))))
        cv_text = lambda n: audit(load(n))[1].cv_text()
        self.assertNotIn("ShelfScan", cv_text("tamberlin"))  # projects lever: left out where no need is served
        self.assertNotIn("ShelfScan", cv_text("brindlewood"))
        self.assertIn("ShelfScan", cv_text("halvane"))  # ShelfSight pilot (C2) makes it relevant


if __name__ == "__main__":
    unittest.main()
