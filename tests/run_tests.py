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
LEGACY = os.path.join(PKGS, "legacy", "brindlewood-v1.json")
VERDICTS = os.path.join(ROOT, "tests", "fixtures", "verdicts", "brindlewood.json")
sys.path.insert(0, SCRIPTS)
sys.path.insert(0, os.path.join(ROOT, "tests", "e2e"))
import audit_package  # noqa: E402
import build_docs  # noqa: E402
import check_docs  # noqa: E402
import run_e2e  # noqa: E402

AGENT_NAMES = ["company-researcher", "job-intelligence", "candidate-evidence", "recruitment-strategist",
               "application-auditor"]
WRITE_TOOLS = {"Write", "Edit", "NotebookEdit", "Bash", "PowerShell", "Agent"}
MODELS = {"inherit", "sonnet", "opus", "haiku", "fable"}
PACKAGES = ["brindlewood", "halvane", "tamberlin", "orvanta", "quarrelane"]
US_SAME_TITLE = ["brindlewood", "halvane", "tamberlin", "orvanta"]  # same candidate, "Junior Software Engineer"
COMPANY_TYPES = {"brindlewood": "startup", "halvane": "mid-size", "tamberlin": "sme", "orvanta": "multinational",
                 "quarrelane": "unknown"}


def read(path):
    with open(path, encoding="utf-8") as fh:
        return fh.read()


def frontmatter(path):
    text = read(path)
    m = re.match(r"^---\n(.*?)\n---\n", text, re.S)
    assert m, "%s: frontmatter must start on line 1" % path
    fm = {}
    for line in m.group(1).splitlines():
        k, _, v = line.partition(":")
        fm[k.strip()] = v.strip().strip('"')
    return fm, text[m.end():]


def load(name):
    path = name if name.endswith(".json") else os.path.join(PKGS, name + ".json")
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def audit(pkg, other=None):
    au = audit_package.Audit(pkg, ROOT).run()  # fixture source paths are relative to the repository
    errors = list(au.errors)
    if other is not None:
        errors += audit_package.compare(pkg, other)["errors"]
    return {e["code"] for e in errors}, au


def warn_codes(pkg):
    return {w["code"] for w in audit(pkg)[1].warnings}


SYMLINK_HELP = ("this checkout stores symlinks as small text files (git core.symlinks=false, the default on Windows "
                "without Developer Mode): the link target recorded in git is correct, but Codex cannot load the skill "
                "here. Enable Developer Mode, run `git config core.symlinks true`, then "
                "`git checkout -- SKILL.md .agents/skills/cv-ats-us` (or use WSL)")


def link_state(path, target):
    """'link' for a real symlink, 'text' when git wrote the link as a text file holding its target."""
    if os.path.islink(path):
        return "link"
    if os.path.isfile(path):
        with open(path, encoding="utf-8") as fh:
            if fh.read().strip() == target:
                return "text"
    return "other"


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

    def test_portable_build_for_web_apps(self):
        """claude.ai/ChatGPT/Gemini copy: builds, passes its own upload checks, scripts run outside the repo."""
        out = tempfile.mkdtemp(prefix="cvats-portable-")
        r = subprocess.run([sys.executable, os.path.join(ROOT, "tools", "build_portable.py"), "--out", out],
                           capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        skill = os.path.join(out, "cv-ats-us")
        self.assertEqual(sorted(os.listdir(os.path.join(skill, "roles"))), sorted(n + ".md" for n in AGENT_NAMES))
        self.assertEqual(os.listdir(os.path.join(out, "gemini")), ["SKILL.md"])
        docs = os.path.join(out, "docs")
        r = subprocess.run([sys.executable, os.path.join(skill, "scripts", "build_docs.py"),
                            os.path.join(PKGS, "halvane.json"), "--out", docs], capture_output=True, text=True, cwd=out)
        self.assertEqual(r.returncode, 0, r.stderr)

    def test_codex_skill_is_a_symlink_not_a_copy(self):
        link = os.path.join(ROOT, ".agents", "skills", "cv-ats-us")
        state = link_state(link, "../../.claude/skills/cv-ats-us")
        if state == "text":
            self.skipTest(SYMLINK_HELP)
        self.assertEqual(state, "link", "%s must be a symlink to the Claude skill, not a copy" % link)
        self.assertEqual(os.path.realpath(link), os.path.realpath(SKILL))

    def test_root_skill_md_links_to_the_skill(self):
        root_md = os.path.join(ROOT, "SKILL.md")
        state = link_state(root_md, ".claude/skills/cv-ats-us/SKILL.md")
        if state == "text":
            self.skipTest(SYMLINK_HELP)
        self.assertEqual(os.path.realpath(root_md), os.path.realpath(os.path.join(SKILL, "SKILL.md")),
                         "root SKILL.md must link to the skill")

    def test_skill_never_points_to_test_fixtures(self):
        """The model must build each package from its own sources, never from a reference package."""
        for d, _, fs in os.walk(SKILL):
            for f in fs:
                if f.endswith(".md"):
                    with open(os.path.join(d, f), encoding="utf-8") as fh:
                        self.assertNotIn("tests/fixtures", fh.read(), f)

    def test_windows_python_fallback(self):
        with open(os.path.join(SKILL, "SKILL.md"), encoding="utf-8") as fh:
            self.assertIn("py -3", fh.read())
        self.assertTrue({"Bash(python *)", "Bash(py *)"} <= set(run_e2e.TOOLS))

    def test_links_and_scripts_resolve(self):
        files = [os.path.join(SKILL, "SKILL.md")] + [os.path.join(SKILL, "references", f)
                                                     for f in os.listdir(os.path.join(SKILL, "references"))]
        for f in files:
            text = read(f)
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
        self.assertIn("applications/", read(os.path.join(ROOT, ".gitignore")))

    def test_university_attribution_guard(self):
        text = read(os.path.join(SKILL, "references", "university-guidelines.md"))
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
            text = re.sub(r'"fingerprint": "[0-9a-f]+"', "", text)  # hashes, not phone numbers
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
        docs = [os.path.join(out, f) for f in os.listdir(out) if f.endswith((".docx", ".pdf"))]
        self.assertEqual(len(docs), 4)
        r = subprocess.run([sys.executable, os.path.join(SCRIPTS, "check_docs.py"), "--package", pkg] + docs,
                           capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stdout)
        r = subprocess.run([sys.executable, os.path.join(SCRIPTS, "audit_package.py"), pkg, "--root", ROOT],
                           capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stdout)


class AuditTests(unittest.TestCase):
    def assertFlags(self, pkg, code, other=None):
        codes, _ = audit(pkg, other)
        self.assertIn(code, codes)

    def test_golden_packages_pass(self):
        for name in PACKAGES:
            pkg = load(name)
            self.assertEqual(pkg["meta"]["schema"], audit_package.SCHEMA, name)
            codes, au = audit(pkg)
            self.assertEqual(codes, set(), "%s: %s" % (name, au.errors))
            self.assertLessEqual({w["code"] for w in au.warnings}, {"W_SELF_REPORTED_HIGH"}, name)

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


def requirement(pkg, rid):
    return [r for r in pkg["job"]["requirements"] if r["id"] == rid][0]


def evidence(pkg, eid):
    return [e for e in pkg["evidence"] if e["id"] == eid][0]


def cv_item(pkg, needle):
    """The CV text item (Skills, Languages...) whose text contains needle."""
    return [i for s in pkg["cv"]["sections"] for i in s["items"] if needle in i.get("text", "")][0]


class RegressionTests(unittest.TestCase):
    """Defects reproduced during the review: each mutation passed the audit before the fix."""

    def test_gap_term_blocked_even_when_requirement_partly_matched(self):
        b = load("brindlewood")
        requirement(b, "R5")["match"] = ["E1"]  # documented shape: partial match + missing part
        cv_item(b, "Docker")["text"] += ", Kubernetes"
        self.assertIn("E_GAP_IN_CV", audit(b)[0])

    def test_cv_heading_dates_and_degree_need_evidence(self):
        b = load("brindlewood")
        b["cv"]["sections"][0]["items"][0]["dates"] = "Aug 2019 - May 2026"
        self.assertIn("E_CV_ITEM_UNSUPPORTED", audit(b)[0])
        b = load("brindlewood")
        b["cv"]["sections"][0]["items"].append({"heading": "MIT", "subheading": "M.S. Computer Science",
                                                "dates": "2027", "bullets": []})
        self.assertIn("E_CV_UNSUPPORTED", audit(b)[0])
        b = load("brindlewood")
        b["cv"]["sections"][1]["items"][0]["heading"] = "RouteWise - delivery route planner (capstone, team of 5)"
        self.assertIn("E_CV_ITEM_UNSUPPORTED", audit(b)[0])

    def test_evidence_numbers_anchored_in_the_candidate_documents(self):
        b = load("brindlewood")  # invented in the card AND the CV: the CV check alone cannot see it
        evidence(b, "E1")["metrics"].append("Planning time fell by 60%")
        b["cv"]["sections"][1]["items"][0]["bullets"][2]["text"] += ", a 60% reduction"
        self.assertIn("E_EVIDENCE_NUMBER_UNSOURCED", audit(b)[0])
        b = load("brindlewood")
        evidence(b, "E1")["excerpts"].append("used by 40 volunteer coordinators")
        self.assertIn("E_EVIDENCE_EXCERPT_NOT_FOUND", audit(b)[0])
        legacy = load(LEGACY)  # older package without excerpts: the whole document is the anchor
        evidence(legacy, "E1")["metrics"].append("Planning time fell by 60%")
        self.assertIn("E_EVIDENCE_NUMBER_UNSOURCED", audit(legacy)[0])

    def test_contract_source_id_is_not_a_citable_number(self):
        q = load("quarrelane")
        corpus = audit_package.Audit(q, ROOT).contract_corpus()
        self.assertIn("Lyon", corpus)
        self.assertNotIn("S2", corpus)

    def test_open_posting_needs_reachable_source(self):
        q = load("quarrelane")
        q["job"]["posting_status"] = "open"  # warnings kept: the old check was satisfied
        self.assertIn("E_POSTING_STATUS", audit(q)[0])

    def test_interview_points_numbers_and_references(self):
        h = load("halvane")
        h["interview"][0]["talking_points"] += " It reached 95% precision."
        self.assertIn("E_METRIC_UNSUPPORTED", audit(h)[0])
        h = load("halvane")
        h["interview"][0]["evidence"] = ["E99"]
        self.assertIn("E_BAD_REF", audit(h)[0])

    def test_named_recipient_needs_a_source_in_any_language(self):
        for name, sal, rec in (("quarrelane", "Madame Claire Dupont,", "Madame Claire Dupont"),
                               ("quarrelane", "Monsieur Martin,", "Service recrutement"),
                               ("brindlewood", "Dear Hiring Manager Sarah Lee,", "Hiring Manager"),
                               ("brindlewood", "Dear Mr. Teamsworth,", "Mr. Teamsworth")):
            pkg = load(name)
            pkg["letter"]["salutation"], pkg["letter"]["recipient"][0] = sal, rec
            self.assertIn("E_RECIPIENT_UNSOURCED", audit(pkg)[0], sal)
        for name, sal in (("quarrelane", "Madame, Monsieur,"), ("brindlewood", "To whom it may concern,")):
            pkg = load(name)
            pkg["letter"]["salutation"] = sal
            self.assertNotIn("E_RECIPIENT_UNSOURCED", audit(pkg)[0], sal)

    def test_pdf_refused_rather_than_printing_question_marks(self):
        b = load("brindlewood")
        b["cv"]["sections"][0]["items"][0]["subheading"] = "B.S. Computer Science, Wrocław campus"
        out = tempfile.mkdtemp(prefix="cvats-font-")
        rec = build_docs.build(b, out, only="cv")["files"][0]
        self.assertIsNone(rec["pdf"])
        self.assertIn("ł", rec["pdf_error"])
        self.assertFalse([f for f in os.listdir(out) if f.endswith(".pdf")])
        self.assertIn("Wrocław", check_docs.docx_text(rec["docx"]))
        path = os.path.join(out, "pkg.json")
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(b, fh, ensure_ascii=False)
        r = subprocess.run([sys.executable, os.path.join(SCRIPTS, "build_docs.py"), path, "--out", out],
                           capture_output=True, text=True, encoding="utf-8")
        self.assertEqual(r.returncode, 1, r.stdout)

    def test_extraction_check_covers_headline_subheading_and_letter_header(self):
        b = load("brindlewood")
        exp = check_docs.expectations(b, "cv")
        self.assertIn(b["cv"]["headline"], exp)
        self.assertIn(b["cv"]["sections"][0]["items"][0]["subheading"], exp)
        exp = check_docs.expectations(b, "letter")
        for k in ("date", "subject", "salutation", "closing"):
            if b["letter"].get(k):
                self.assertIn(b["letter"][k], exp, k)
        self.assertIn(b["letter"]["recipient"][0], exp)

    def test_build_manifest_rejects_stale_or_foreign_documents(self):
        h = load("halvane")
        out = tempfile.mkdtemp(prefix="cvats-manifest-")
        files = [f[k] for f in build_docs.build(h, out)["files"] for k in ("docx", "pdf")]
        errors = lambda pkg, fs: [e for r in check_docs.check_manifest(fs, pkg) for e in r["errors"]]
        self.assertEqual(errors(h, files), [])
        changed = copy.deepcopy(h)  # package edited after the build, documents not rebuilt
        changed["letter"]["paragraphs"][0]["text"] += " Thank you."
        self.assertTrue([e for e in errors(changed, files) if "package changed" in e])
        old = os.path.join(out, "Camille-Testard_Resume_Old-Attempt.pdf")  # left by an earlier attempt
        with open(files[1], "rb") as src, open(old, "wb") as dst:
            dst.write(src.read())
        self.assertTrue([e for e in errors(h, files + [old]) if "not produced" in e])
        with open(files[0], "ab") as fh:  # edited after the build
            fh.write(b"\0")
        self.assertTrue([e for e in errors(h, files) if "changed after" in e])
        bare = tempfile.mkdtemp(prefix="cvats-nomanifest-")  # no build.json: error now, warning for old folders
        other = os.path.join(bare, os.path.basename(files[1]))
        with open(files[1], "rb") as src, open(other, "wb") as dst:
            dst.write(src.read())
        self.assertTrue(errors(h, [other]))
        legacy = load(LEGACY)
        res = check_docs.check_manifest([other], legacy)
        self.assertEqual([e for r in res for e in r["errors"]], [])
        self.assertTrue([w for r in res for w in r["warnings"]])

    def test_e2e_failed_run_never_validates_previous_outputs(self):
        """A run that delegates then stops without writing must fail even if a previous run left valid files."""
        tmp = tempfile.mkdtemp(prefix="cvats-e2e-stale-")
        saved_out, saved_run = run_e2e.OUT, run_e2e.subprocess.run
        name = "brindlewood"
        try:
            run_e2e.OUT = tmp
            prev = os.path.join(tmp, name)
            os.makedirs(prev)
            pkg = load(name)
            with open(os.path.join(prev, "package.json"), "w", encoding="utf-8") as fh:
                json.dump(pkg, fh, ensure_ascii=False)
            build_docs.build(pkg, prev)
            transcript = "\n".join(json.dumps({"type": "assistant", "message": {"content": [
                {"type": "tool_use", "name": "Agent", "input": {"subagent_type": a}}]}}) for a in AGENT_NAMES)
            run_e2e.subprocess.run = lambda cmd, **kw: subprocess.CompletedProcess(cmd, 1, transcript, "budget")
            run_e2e.run_claude(name, "haiku", 0.01, 10)
        finally:
            run_e2e.subprocess.run = saved_run
        try:
            res = run_e2e.validate(name)
        finally:
            run_e2e.OUT = saved_out
        failed = [c["check"] for c in res["checks"] if not c["ok"]]
        self.assertFalse(res["ok"])
        self.assertIn("package.json written", failed)
        self.assertTrue([c for c in failed if c.startswith("run recorded")])

    def test_e2e_strategist_note_must_arrive_before_the_first_write(self):
        """Calling the strategist is not enough: its final note must be back before anything is written."""
        tmp = tempfile.mkdtemp(prefix="cvats-e2e-order-")
        saved = run_e2e.OUT
        use = lambda i, n, inp: json.dumps({"type": "assistant", "message": {"content": [
            {"type": "tool_use", "id": i, "name": n, "input": inp}]}})
        result = lambda i, text, err=False: json.dumps({"type": "user", "message": {"content": [
            {"type": "tool_result", "tool_use_id": i, "content": text, "is_error": err}]}})
        notice = lambda text: json.dumps({"type": "user", "message": {"content": [{"type": "text", "text": text}]}})
        strat, bg = {"subagent_type": "recruitment-strategist"}, {"subagent_type": "recruitment-strategist",
                                                                  "run_in_background": True}
        write = use("w", "Write", {"file_path": "applications/_e2e/x/package.json"})
        note = "## strategy\nValue proposition: junior backend developer..."
        cases = {
            "write before the call": ([write, use("s", "Agent", strat), result("s", note)], False),
            "background call, no result": ([use("s", "Agent", bg), result("s", "Async agent launched successfully."),
                                            write], False),
            "failed call": ([use("s", "Agent", strat), result("s", "Agent failed: max turns reached", True), write],
                            False),
            "late result": ([use("s", "Agent", bg), result("s", "Async agent launched successfully."), write,
                             notice("<task-notification>" + note)], False),
            "correct run": ([use("m", "Bash", {"command": "mkdir -p applications/_e2e/x"}), use("s", "Agent", strat),
                             result("s", note), write], True),
            "background result before writing": ([use("s", "Agent", bg), result("s", "Async agent launched."),
                                                  notice("<task-notification>" + note), write], True)}
        try:
            run_e2e.OUT = tmp
            for label, (order, expected) in cases.items():
                with open(os.path.join(tmp, "x.transcript.jsonl"), "w", encoding="utf-8") as fh:
                    fh.write("\n".join(order))
                self.assertIs(run_e2e.strategy_before_writing("x"), expected, label)
        finally:
            run_e2e.OUT = saved


class StrategyTests(unittest.TestCase):
    def test_value_proposition_numbers_are_checked(self):
        b = load("brindlewood")
        b["strategy"]["value_proposition"] += " with 5 years of Kubernetes"
        self.assertIn("E_METRIC_UNSUPPORTED", audit(b)[0])

    def test_value_proposition_goes_to_the_auditor(self):
        """'3' exists elsewhere in the evidence (team of 3), so '3 years of Kubernetes' passes the number check:
        only the semantic audit can reject it, so the pitch is a verification target."""
        b = load("brindlewood")
        b["strategy"]["value_proposition"] += " with 3 years of Kubernetes"
        codes, au = audit(b)
        self.assertNotIn("E_METRIC_UNSUPPORTED", codes)
        self.assertIn("strategy.value_proposition", {t["target"] for t in au.targets()})

    def test_argument_needs_and_placement(self):
        b = load("brindlewood")
        b["strategy"]["arguments"][0]["need"] = "C2, R99"
        self.assertIn("E_BAD_REF", audit(b)[0])
        b = load("brindlewood")  # the Kubernetes gap argument may not reach the CV
        b["strategy"]["arguments"][2]["placement"] = "both"
        self.assertIn("E_ARGUMENT_PLACEMENT", audit(b)[0])
        b = load("brindlewood")
        b["strategy"]["arguments"][0]["confidence"] = "very high"
        self.assertIn("E_STRATEGY_ENUM", audit(b)[0])

    def test_every_required_requirement_is_assessed(self):
        b = load("brindlewood")
        requirement(b, "R5")["gap_terms"] = []
        self.assertIn("E_REQUIREMENT_UNASSESSED", audit(b)[0])

    def test_strategy_is_mandatory_for_new_outputs_only(self):
        b = load("brindlewood")
        b["strategy"]["arguments"] = []
        self.assertIn("E_STRATEGY_MISSING", audit(b)[0])
        legacy = load(LEGACY)
        legacy["strategy"]["arguments"] = []
        self.assertNotIn("E_STRATEGY_MISSING", audit(legacy)[0])
        self.assertIn("W_STRATEGY", warn_codes(legacy))


class ModeLanguageTests(unittest.TestCase):
    def test_create_mode_needs_no_company_posting_or_letter(self):
        c = load("brindlewood")
        for k in ("letter", "job", "strategy", "company_profile", "interview", "questions"):
            c.pop(k)
        c["company_claims"] = []
        c["sources"] = [s for s in c["sources"] if s["kind"] == "candidate"]
        c["meta"].update(mode="create", company="")
        codes, au = audit(c)
        self.assertEqual(codes, set(), au.errors)
        res = build_docs.build(c, tempfile.mkdtemp(prefix="cvats-create-"))
        self.assertEqual([f["kind"] for f in res["files"]], ["cv"])

    def test_cover_letter_mode_needs_no_cv_sections(self):
        l = load("brindlewood")
        l["cv"]["sections"] = []
        l.pop("interview")
        l["meta"]["mode"] = "cover-letter"
        codes, au = audit(l)
        self.assertEqual(codes, set(), au.errors)
        res = build_docs.build(l, tempfile.mkdtemp(prefix="cvats-letter-"))
        self.assertEqual([f["kind"] for f in res["files"]], ["letter"])

    def test_mode_rules(self):
        p = load("brindlewood")
        p.pop("letter")
        self.assertIn("E_STRUCTURE", audit(p)[0])  # package mode needs the letter
        p = load("brindlewood")
        p["meta"]["mode"] = "everything"
        self.assertIn("E_MODE", audit(p)[0])
        p = load("brindlewood")
        p["meta"].pop("mode")
        self.assertIn("E_MODE", audit(p)[0])

    def test_market_and_language_are_separate(self):
        h = load("brindlewood")  # a posting in English for the French market: A4, English conventions
        h["meta"]["market"] = "FR"
        self.assertEqual(audit(h)[0], set())
        res = build_docs.build(h, tempfile.mkdtemp(prefix="cvats-frEN-"), only="cv")
        self.assertEqual(res["paper"], "a4")
        text = check_docs.docx_text(res["files"][0]["docx"])
        self.assertIn("Data and tools: ", text)
        self.assertNotIn(" : ", text)
        q = load("quarrelane")  # French letter for an English posting: allowed only with a recorded reason
        self.assertNotIn("W_LANGUAGE_MISMATCH", warn_codes(q))
        q["meta"].pop("language_basis")
        self.assertIn("W_LANGUAGE_MISMATCH", warn_codes(q))


class ContractTests(unittest.TestCase):
    """Employment contract checked before writing; contribution sized to it."""

    def internship(self):
        q = load("quarrelane")
        q["job"]["contract"].update(type="internship", duration_months=6)
        return q

    def test_incompatible_contract_blocks_until_the_candidate_decides(self):
        q = load("quarrelane")
        q["strategy"]["contract_fit"][1].update(posting="2026-09", candidate="available from January 2027",
                                                status="incompatible")
        self.assertIn("E_CONTRACT_INCOMPATIBLE", audit(q)[0])
        q["meta"]["contract_override"] = "Candidate asked to apply anyway and to propose January 2027 (2026-10-12)."
        self.assertNotIn("E_CONTRACT_INCOMPATIBLE", audit(q)[0])

    def test_compatible_needs_candidate_evidence_and_known_ids(self):
        q = load("quarrelane")
        q["strategy"]["contract_fit"][2]["basis"] = ["S2"]
        self.assertIn("E_CONTRACT_FIT_UNSUPPORTED", audit(q)[0])
        q = load("quarrelane")
        q["strategy"]["contract_fit"][2]["basis"] = ["S2", "E42"]
        self.assertIn("E_BAD_REF", audit(q)[0])

    def test_contract_required_for_new_outputs_only(self):
        q = load("quarrelane")
        q["job"].pop("contract")
        q["strategy"].pop("contract_fit")
        self.assertTrue({"E_CONTRACT_MISSING", "E_CONTRACT_FIT_MISSING"} <= audit(q)[0])
        self.assertTrue({"W_CONTRACT_MISSING", "W_CONTRACT_FIT_MISSING"} <= warn_codes(load(LEGACY)))

    def test_unknown_contract_row_needs_a_question(self):
        b = load("brindlewood")
        b["questions"] = [q for q in b["questions"] if "K2" not in q["need"]]
        self.assertIn("W_NO_QUESTION", warn_codes(b))

    def test_contribution_horizon_fits_the_contract(self):
        for sentence, bad in ((" Au cours des 12 prochains mois, je pourrais fiabiliser ces imports.", True),
                              (" Au cours des deux prochaines années, je pourrais reprendre vos pipelines.", True),
                              (" Pendant ces 6 mois, je pourrais fiabiliser un import.", False)):
            q = self.internship()
            q["letter"]["paragraphs"][-1]["text"] += sentence
            codes = audit(q)[0]
            self.assertEqual("E_CONTRIBUTION_HORIZON" in codes, bad, sentence)
            if not bad:
                self.assertNotIn("E_METRIC_UNSUPPORTED", codes, sentence)  # the contract's own numbers are citable
        q = self.internship()
        q["strategy"]["contribution"]["horizon_months"] = 12
        self.assertIn("E_CONTRIBUTION_HORIZON", audit(q)[0])

    def test_contribution_paragraph_required_for_new_letters(self):
        q = load("quarrelane")
        q["letter"]["paragraphs"][-1]["contribution"] = False
        self.assertIn("E_CONTRIBUTION_MISSING", audit(q)[0])


class LevelTests(unittest.TestCase):
    """Levels are anchored and compared only where it is exact (CEFR); meaning goes to the auditor."""

    def test_language_level_must_cite_leveled_evidence(self):
        q = load("quarrelane")
        cv_item(q, "anglais")["evidence"] = ["E1"]
        self.assertIn("E_LEVEL_UNSUPPORTED", audit(q)[0])
        legacy = load(LEGACY)  # older package: warning only
        self.assertIn("W_LEVEL_UNSUPPORTED", warn_codes(legacy))
        self.assertNotIn("E_LEVEL_UNSUPPORTED", audit(legacy)[0])

    def test_recorded_level_must_be_in_the_source(self):
        b = load("brindlewood")
        evidence(b, "E7")["levels"].append({"subject": "English", "level": "bilingual"})
        self.assertIn("E_LEVEL_UNANCHORED", audit(b)[0])

    def test_cefr_level_never_above_the_recorded_one(self):
        src = os.path.join(tempfile.mkdtemp(prefix="cvats-cefr-"), "languages.md")
        with open(src, "w", encoding="utf-8") as fh:
            fh.write("Languages: German (B2).\n")
        b = load("brindlewood")
        b["sources"].append({"id": "S9", "kind": "candidate", "url": src, "title": "Language certificate"})
        b["evidence"].append({"id": "E9", "title": "German", "stage": "self-reported", "tools": [], "facts": ["German (B2)"],
                              "metrics": [], "source": "S9", "excerpts": ["German (B2)"],
                              "levels": [{"subject": "German", "level": "B2"}]})
        line = cv_item(b, "French (native)")
        line["evidence"] = line["evidence"] + ["E9"]
        line["text"] += " German (C1)."
        self.assertIn("E_LEVEL_UNSUPPORTED", audit(b)[0])
        line["text"] = line["text"].replace("German (C1)", "German (B2)")
        self.assertNotIn("E_LEVEL_UNSUPPORTED", audit(b)[0])

    def test_reworded_level_becomes_an_auditor_target(self):
        q = load("quarrelane")
        cv_item(q, "anglais")["text"] = cv_item(q, "anglais")["text"].replace("courant", "bilingue")
        codes, au = audit(q)
        self.assertNotIn("E_LEVEL_UNSUPPORTED", codes)  # evidence is leveled: no word list decides the meaning
        targets = {t["target"]: t for t in au.targets()}
        level_targets = [t for t in targets.values() if t["level"] and "bilingue" in t["text"]]
        self.assertEqual(len(level_targets), 1)
        t = level_targets[0]
        verdicts = {"verdicts": [{"target": x, "verdict": "supported", "source": targets[x]["sources"][0],
                                  "excerpt": "Python", "fingerprint": targets[x].get("fingerprint")}
                                 for x in targets]}
        au.check_verdicts(verdicts)
        self.assertIn("E_VERDICT_LEVEL", {e["code"] for e in au.errors})
        verdicts["verdicts"] = [dict(v, verdict="partial", note="source says fluent") if v["target"] == t["target"]
                                else v for v in verdicts["verdicts"]]
        au.errors = []
        au.check_verdicts(verdicts)
        self.assertIn("E_VERDICT_REJECTED", {e["code"] for e in au.errors})

    def test_level_words_outside_a_language_are_not_levels(self):
        q = load("quarrelane")
        q["letter"]["paragraphs"][2]["text"] += " Je pourrais m'y mettre dans le courant du premier mois."
        self.assertNotIn("letter.paragraphs[2]", audit(q)[1].level_lines)
        b = load("brindlewood")
        b["cv"]["sections"][1]["items"][0]["bullets"][0]["text"] += " (native app; programming languages: Python)"
        self.assertNotIn("cv.Projects[0].bullets[0]", audit(b)[1].level_lines)

    def test_required_level_not_met_caps_confidence(self):
        q = load("quarrelane")
        requirement(q, "R4")["level_match"] = "below"
        q["strategy"]["arguments"][0]["need"] = "R1, R2, R4"
        self.assertIn("E_CONFIDENCE_INFLATED", audit(q)[0])
        q = load("quarrelane")
        requirement(q, "R4").pop("level_match")
        self.assertIn("E_LEVEL_UNASSESSED", audit(q)[0])

    def test_self_reported_high_confidence_is_flagged(self):
        self.assertIn("W_SELF_REPORTED_HIGH", warn_codes(load("orvanta")))


class QuestionTests(unittest.TestCase):
    def test_questions_reference_known_needs(self):
        b = load("brindlewood")
        b["questions"][0]["need"] = ["R99"]
        self.assertIn("E_BAD_REF", audit(b)[0])

    def test_blocking_question_must_be_answered_before_writing(self):
        b = load("brindlewood")
        b["questions"][1]["blocking"] = True
        self.assertIn("E_BLOCKING_QUESTION_OPEN", audit(b)[0])
        b["questions"][1]["answer"] = "Full-time, from January 2027, hybrid from Indianapolis is possible."
        self.assertNotIn("E_BLOCKING_QUESTION_OPEN", audit(b)[0])

    def test_low_confidence_arguments_get_a_question(self):
        b = load("brindlewood")
        b["questions"] = []
        self.assertIn("W_NO_QUESTION", warn_codes(b))
        b = load("brindlewood")
        b["questions"] = b["questions"] * 3
        self.assertIn("W_QUESTIONS", warn_codes(b))


class DifferentiationTests(unittest.TestCase):
    def test_opening_cites_a_company_fact_or_requirement(self):
        b = load("brindlewood")
        b["letter"]["paragraphs"][0]["claims"] = []
        self.assertIn("E_OPENING_GENERIC", audit(b)[0])
        b["letter"]["paragraphs"][0]["requirements"] = ["R3"]
        self.assertNotIn("E_OPENING_GENERIC", audit(b)[0])

    def test_same_cv_top_for_two_companies_is_flagged(self):
        b, h = load("brindlewood"), load("halvane")
        fake = copy.deepcopy(h)
        fake["cv"] = copy.deepcopy(b["cv"])
        self.assertIn("W_SAME_CV_LEAD", {w["code"] for w in audit_package.compare(b, fake)["warnings"]})
        for x, y in itertools.combinations(US_SAME_TITLE, 2):
            self.assertNotIn("W_SAME_CV_LEAD", {w["code"] for w in audit_package.compare(load(x), load(y))["warnings"]})

    def test_hiring_context_is_traced_to_needs(self):
        b = load("brindlewood")
        b["strategy"].pop("hiring_context")
        self.assertIn("E_HIRING_CONTEXT_MISSING", audit(b)[0])
        b = load("brindlewood")
        b["strategy"]["hiring_context"]["basis"] = list(b["company_profile"]["basis"])
        self.assertIn("E_SIZE_ONLY", audit(b)[0])
        b = load("brindlewood")
        b["strategy"]["hiring_context"]["basis"] = ["C99"]
        self.assertIn("E_ADAPTATION_UNSUPPORTED", audit(b)[0])


class VerdictTests(unittest.TestCase):
    """Deterministic proof that the semantic audit covered every statement and quoted real sources."""

    def verdicts(self):
        with open(VERDICTS, encoding="utf-8") as fh:
            return json.load(fh)

    def check(self, verdicts, pkg=None):
        au = audit(pkg or load("brindlewood"))[1]
        au.check_verdicts(verdicts)
        return {e["code"] for e in au.errors}

    def test_reference_verdicts_pass(self):
        self.assertEqual(self.check(self.verdicts()), set())

    def test_missing_rejected_misquoted_or_misattributed_verdicts(self):
        v = self.verdicts()
        v["verdicts"] = v["verdicts"][1:]
        self.assertIn("E_VERDICT_COVERAGE", self.check(v))
        v = self.verdicts()
        v["verdicts"][3]["verdict"] = "partial"
        self.assertIn("E_VERDICT_REJECTED", self.check(v))
        v = self.verdicts()
        v["verdicts"][3]["excerpt"] = "deployed to production for 40 users"
        self.assertIn("E_VERDICT_EXCERPT", self.check(v))
        v = self.verdicts()
        claim = [x for x in v["verdicts"] if x["target"] == "claim:C2"][0]
        claim["source"] = "S6"
        self.assertIn("E_VERDICT_SOURCE", self.check(v))
        v = self.verdicts()
        for x in v["verdicts"]:
            x.pop("level_checked", None)
        self.assertIn("E_VERDICT_LEVEL", self.check(v))

    def test_cli_targets_file_and_verdicts(self):
        out = os.path.join(tempfile.mkdtemp(prefix="cvats-targets-"), "targets.json")
        pkg = os.path.join(PKGS, "brindlewood.json")
        r = subprocess.run([sys.executable, os.path.join(SCRIPTS, "audit_package.py"), pkg, "--root", ROOT,
                            "--targets", out], capture_output=True, text=True, encoding="utf-8")
        self.assertEqual(r.returncode, 0, r.stdout)
        with open(out, encoding="utf-8") as fh:
            self.assertEqual(len(json.load(fh)["targets"]), len(self.verdicts()["verdicts"]))
        r = subprocess.run([sys.executable, os.path.join(SCRIPTS, "audit_package.py"), pkg, "--root", ROOT,
                            "--verdicts", VERDICTS], capture_output=True, text=True, encoding="utf-8")
        self.assertEqual(r.returncode, 0, r.stdout)


class LegacyTests(unittest.TestCase):
    """Older folders (no meta.schema) still audit: new contract rules are warnings, truth rules stay errors."""

    def test_legacy_package_passes_with_warnings(self):
        codes, au = audit(load(LEGACY))
        self.assertEqual(codes, set(), au.errors)
        self.assertTrue({"W_EVIDENCE_NO_EXCERPT", "W_CONTRACT_MISSING", "W_HIRING_CONTEXT_MISSING"}
                        <= {w["code"] for w in au.warnings})

    def test_truth_rules_still_apply_to_legacy_packages(self):
        legacy = load(LEGACY)
        legacy["cv"]["sections"][0]["items"][0]["dates"] = "Aug 2019 - May 2026"
        self.assertIn("E_CV_ITEM_UNSUPPORTED", audit(legacy)[0])
        legacy = load(LEGACY)
        requirement(legacy, "R5")["match"] = ["E1"]
        cv_item(legacy, "Docker")["text"] += ", Kubernetes"
        self.assertIn("E_GAP_IN_CV", audit(legacy)[0])


class HexPdf(build_docs.Pdf):
    """A valid PDF whose text is written as hex strings: viewers show it, the stdlib extractor reads nothing."""

    def text(self, x, y, line, size):
        parts = ["BT", "%.2f %.2f Td" % (x, y), "/F1 %.1f Tf" % size]
        parts += ["<%s> Tj" % t.encode("cp1252", "replace").hex() for t, _ in line]
        self.ops.append(" ".join(parts + ["ET"]))


def hex_pdf(pkg, folder):
    doc = HexPdf("letter", 50.0)
    doc.render(build_docs.cv_blocks(pkg))
    path = os.path.join(folder, "cv-hex.pdf")
    with open(path, "wb") as fh:
        fh.write(doc.to_bytes("CV"))
    return path


def reference_verdicts():
    with open(VERDICTS, encoding="utf-8") as fh:
        return json.load(fh)


def verdicts_for(au, overrides=None, base=None):
    """One supported verdict per current target (reference quote when one exists), with overrides per target."""
    known = {v["target"]: v for v in (base or {}).get("verdicts", [])}
    out = []
    for t in au.targets():
        v = dict(known.get(t["target"]) or {"source": (t["sources"] or ["S0"])[0], "excerpt": "placeholder"})
        v.update(target=t["target"], verdict="supported", level_checked=True, fingerprint=t.get("fingerprint"))
        v.update((overrides or {}).get(t["target"], {}))
        out.append(v)
    return {"verdicts": out}


def target_errors(au, verdicts, target):
    au.errors = []
    au.check_verdicts(verdicts)
    return {e["code"] for e in au.errors if e["msg"].startswith(target + ":")}


RESOLVED = "Resolved device and account issues for library staff and patrons."


class SecondReviewTests(unittest.TestCase):
    """Defects confirmed by the second review. Each test failed on the code before its fix."""

    # 1. stale verdicts
    def test_verdicts_go_stale_when_the_degree_becomes_a_phd(self):
        b = load("brindlewood")
        b["cv"]["sections"][0]["items"][0]["subheading"] = "Ph.D. Computer Science"
        codes, au = audit(b)
        self.assertEqual(codes, set(), "the scripts alone cannot see a changed degree")
        au.check_verdicts(reference_verdicts())
        self.assertIn("E_VERDICT_STALE", {e["code"] for e in au.errors})

    def test_verdicts_go_stale_when_3_years_of_kubernetes_is_added(self):
        b = load("brindlewood")
        b["strategy"]["value_proposition"] += " with 3 years of Kubernetes"
        codes, au = audit(b)
        self.assertEqual(codes, set(), "'3' exists elsewhere in the evidence: the number check passes")
        au.check_verdicts(reference_verdicts())
        self.assertIn("E_VERDICT_STALE", {e["code"] for e in au.errors})

    def test_verdicts_go_stale_when_a_cited_evidence_card_changes(self):
        b = load("brindlewood")
        evidence(b, "E5")["facts"][1] = "Designed and graded SQL assignments"
        au = audit(b)[1]
        au.check_verdicts(reference_verdicts())
        self.assertIn("E_VERDICT_STALE", {e["code"] for e in au.errors})

    # 2. source states: missing file, unreadable file, wrong quotation
    def with_source(self, url, excerpts, copy_path=None):
        b = load("brindlewood")
        src = {"id": "S9", "kind": "candidate", "url": url, "title": "CV"}
        if copy_path:
            src["copy_path"] = copy_path
        b["sources"].append(src)
        b["evidence"].append({"id": "E9", "title": "IT support", "stage": "experience", "tools": [],
                              "facts": [RESOLVED.rstrip(".")], "metrics": [], "source": "S9", "excerpts": excerpts})
        bullet = [x for s in b["cv"]["sections"] for i in s["items"] for x in i.get("bullets", [])
                  if x["text"].startswith("Resolved device")][0]
        bullet["evidence"] = ["E9"]
        return b

    def bullet_target(self, au):
        return [t["target"] for t in au.targets() if t["text"].startswith("Resolved device")][0]

    def test_missing_local_source_is_an_error(self):
        codes, au = audit(self.with_source("inputs/no-such-cv.md", [RESOLVED]))
        self.assertIn("E_SOURCE_MISSING", codes)

    def test_unreadable_pdf_is_unchecked_never_miscited(self):
        pdf = hex_pdf(load("brindlewood"), tempfile.mkdtemp(prefix="cvats-hexpdf-"))
        self.assertEqual(check_docs.pdf_info(pdf)["text"].strip(), "")
        codes, au = audit(self.with_source(pdf, [RESOLVED]))
        self.assertNotIn("E_EVIDENCE_EXCERPT_NOT_FOUND", codes)
        self.assertIn("W_EVIDENCE_UNCHECKED", {w["code"] for w in au.warnings})
        target = self.bullet_target(au)
        errs = target_errors(au, verdicts_for(au, {target: {"source": "S9", "excerpt": RESOLVED}},
                                              reference_verdicts()), target)
        self.assertNotIn("E_VERDICT_EXCERPT", errs)
        self.assertIn("W_VERDICT_UNCHECKED", {w["code"] for w in au.warnings})
        self.assertFalse(au.verification()["complete"])

    def test_readable_source_with_a_wrong_quote_is_an_error(self):
        pdf = build_docs.build(load("brindlewood"), tempfile.mkdtemp(prefix="cvats-pdfsrc-"), only="cv")["files"][0]["pdf"]
        codes, _ = audit(self.with_source(pdf, ["Led a team of 12 engineers"]))
        self.assertIn("E_EVIDENCE_EXCERPT_NOT_FOUND", codes)

    def test_text_copy_checks_an_unreadable_pdf(self):
        folder = tempfile.mkdtemp(prefix="cvats-copy-")
        pdf = hex_pdf(load("brindlewood"), folder)
        md = os.path.join(folder, "cv.md")
        with open(md, "w", encoding="utf-8") as fh:
            fh.write("## Experience\n- " + RESOLVED + "\n")
        codes, au = audit(self.with_source(pdf, [RESOLVED], copy_path=md))
        self.assertEqual(codes, set(), au.errors)
        self.assertNotIn("W_EVIDENCE_UNCHECKED", {w["code"] for w in au.warnings})
        codes, _ = audit(self.with_source(pdf, ["Led a team of 12 engineers"], copy_path=md))
        self.assertIn("E_EVIDENCE_EXCERPT_NOT_FOUND", codes)

    # 3. references propagated to the sources a verdict may quote
    def test_brindlewood_paragraph_citing_r5_may_quote_the_posting(self):
        b = load("brindlewood")
        target = "letter.paragraphs[3]"
        self.assertEqual(b["letter"]["paragraphs"][3]["requirements"], ["R5"])
        au = audit(b)[1]
        self.assertIn(b["job"]["source"], {t["target"]: t for t in au.targets()}[target]["sources"])
        errs = target_errors(au, verdicts_for(au, {target: {
            "source": "S4", "excerpt": "experience deploying services on Kubernetes"}}, reference_verdicts()), target)
        self.assertFalse(errs & {"E_VERDICT_SOURCE", "E_VERDICT_EXCERPT"}, errs)

    def test_tamberlin_interview_point_on_the_2027_plan_may_quote_the_news(self):
        t = load("tamberlin")
        au = audit(t)[1]
        target = "interview[0]"
        errs = target_errors(au, verdicts_for(au, {target: {
            "source": "S2", "excerpt": "we plan to connect both channels to our production schedule by mid-2027"}}),
            target)
        self.assertFalse(errs & {"E_VERDICT_SOURCE", "E_VERDICT_EXCERPT"}, errs)

    def test_target_without_references_cannot_quote_any_source(self):
        b = load("brindlewood")
        b["interview"][0]["evidence"] = []
        au = audit(b)[1]
        errs = target_errors(au, verdicts_for(au, {"interview[0]": {
            "source": "S6", "excerpt": "I wrote pytest tests for the API endpoints."}}, reference_verdicts()),
            "interview[0]")
        self.assertIn("E_VERDICT_SOURCE", errs)

    # 5. empty or partial contract comparison
    def test_empty_contract_fit_is_refused(self):
        b = load("brindlewood")
        b["strategy"]["contract_fit"] = []
        self.assertIn("E_CONTRACT_FIT_INCOMPLETE", audit(b)[0])

    def test_missing_comparisons_and_invented_compatibility_are_refused(self):
        b = load("brindlewood")
        b["strategy"]["contract_fit"] = [k for k in b["strategy"]["contract_fit"] if k["field"] != "location"]
        self.assertIn("E_CONTRACT_FIT_INCOMPLETE", audit(b)[0])
        b = load("brindlewood")  # the posting states no start date: compatibility cannot be known
        b["strategy"]["contract_fit"][1]["status"] = "compatible"
        self.assertIn("E_CONTRACT_FIT_UNSUPPORTED", audit(b)[0])
        q = load("quarrelane")  # a stated duration needs its own comparison
        q["job"]["contract"].update(type="internship", duration_months=6)
        self.assertIn("E_CONTRACT_FIT_INCOMPLETE", audit(q)[0])

    # 6. every adaptation rests on a verified need
    def test_adaptation_resting_only_on_a_hypothesis_is_refused(self):
        b = load("brindlewood")
        b["strategy"]["adaptation"][0]["basis"] = ["C5"]
        self.assertIn("E_ADAPTATION_UNVERIFIED", audit(b)[0])
        b = load("brindlewood")
        b["strategy"]["hiring_context"]["basis"] = ["C5"]
        self.assertIn("E_ADAPTATION_UNVERIFIED", audit(b)[0])
        b = load("brindlewood")  # a hypothesis may complete a confirmed fact
        b["strategy"]["adaptation"][0]["basis"] = ["C5", "C2"]
        self.assertNotIn("E_ADAPTATION_UNVERIFIED", audit(b)[0])

    # pending adjustment: attributed estimates
    def estimate_bullet(self, b):
        return [x for s in b["cv"]["sections"] for i in s["items"] for x in i.get("bullets", [])
                if "2 hours" in x["text"]][0]

    def test_attributed_estimate_is_allowed(self):
        b = load("brindlewood")
        self.estimate_bullet(b)["text"] = ("Wrote a Python script that automated the weekly public-computer "
                                           "reservation report, saving about 2 hours of staff time per week "
                                           "(estimated by my supervisor)")
        codes = audit(b)[0]
        self.assertFalse(codes & {"E_DISCLAIMER", "E_ESTIMATE_AS_MEASURE"}, codes)

    def test_estimate_is_not_turned_into_a_measure(self):
        b = load("brindlewood")
        self.estimate_bullet(b)["text"] = ("Wrote a Python script that automated the weekly public-computer "
                                           "reservation report, saving 2 hours of staff time per week")
        self.assertIn("E_ESTIMATE_AS_MEASURE", audit(b)[0])
        b = load("brindlewood")
        b["cv"]["sections"][1]["items"][0]["bullets"][2]["text"] = (
            "Cut planning time per shift from 25 to 10 minutes for 4 volunteer coordinators over 3 weeks")
        self.assertIn("E_ESTIMATE_AS_MEASURE", audit(b)[0])

    def test_verdicts_go_stale_when_a_source_document_changes(self):
        """A verdict is bound to the text actually read from its sources, not only to their names and paths."""
        folder = tempfile.mkdtemp(prefix="cvats-srcchange-")
        copy_path = os.path.join(folder, "projects.md")
        with open(copy_path, "w", encoding="utf-8") as fh:
            fh.write(read(os.path.join(ROOT, "tests", "fixtures", "candidate", "projects.md")))
        b = load("brindlewood")
        [s for s in b["sources"] if s["id"] == "S6"][0]["copy_path"] = copy_path
        au = audit(b)[1]
        verdicts = verdicts_for(au, base=reference_verdicts())
        au.check_verdicts(verdicts)
        self.assertEqual(au.errors, [], "fresh verdicts pass")
        with open(copy_path, "a", encoding="utf-8") as fh:  # every quoted excerpt is still in the file
            fh.write("\n- Note: the RouteWise pilot was stopped after one week.\n")
        codes, au = audit(b)
        self.assertEqual(codes, set())
        au.check_verdicts(verdicts)
        self.assertIn("E_VERDICT_STALE", {e["code"] for e in au.errors})

    def test_contract_duration_is_not_mistaken_for_a_candidate_estimate(self):
        """'10' is both the contract duration and the survey figure (25 -> 10 minutes) of the cited evidence E1."""
        for name, para, sentence in (("quarrelane", 1, " Ce stage de 10 mois me permettrait d'aller plus loin."),
                                     ("brindlewood", 1, " A 10-month internship would let me go further.")):
            p = load(name)
            p["job"]["contract"].update(type="internship", duration_months=10)
            self.assertIn("E1", p["letter"]["paragraphs"][para]["evidence"])
            p["letter"]["paragraphs"][para]["text"] += sentence
            self.assertNotIn("E_ESTIMATE_AS_MEASURE", audit(p)[0], name)
            p["letter"]["paragraphs"][para]["text"] += " Planning time fell to 10 minutes."  # still a bare estimate
            self.assertIn("E_ESTIMATE_AS_MEASURE", audit(p)[0], name)

    # pending adjustment: contribution from the posting and its context, not from the contract type
    def test_contribution_resting_only_on_the_contract_is_refused(self):
        b = load("brindlewood")
        b["strategy"]["contribution"]["basis"] = ["K1"]
        self.assertIn("E_ADAPTATION_UNVERIFIED", audit(b)[0])


class BrindlewoodTrialTests(unittest.TestCase):
    """Defects seen in the Brindlewood trial run (agent outputs off contract, Windows console, partial re-audits)."""

    def test_argument_need_may_be_a_list_of_ids(self):
        b = load("brindlewood")
        b["strategy"]["arguments"][0]["need"] = ["C2", "C4", "R1", "R2", "R3"]  # questions already use lists
        self.assertNotIn("E_BAD_REF", audit(b)[0])
        b["strategy"]["arguments"][0]["need"] = ["R1", "R99"]
        self.assertIn("E_BAD_REF", audit(b)[0])

    def test_evidence_fields_must_be_strings(self):
        b = load("brindlewood")
        evidence(b, "E4")["metrics"] = [{"value": "about 2 hours of staff time per week", "nature": "estimate"}]
        self.assertIn("E_STRUCTURE", audit(b)[0])

    def test_source_kind_must_be_in_the_contract(self):
        b = load("brindlewood")
        b["sources"][0]["kind"] = "blog"
        self.assertIn("E_STRUCTURE", audit(b)[0])

    def test_estimate_repeated_in_facts_stays_an_estimate(self):
        """facts are the agent's paraphrase: repeating '2 hours' there must not turn the estimate into a fact."""
        b = load("brindlewood")
        evidence(b, "E4")["facts"].append("Saved about 2 hours of staff time per week")
        bullet = [x for s in b["cv"]["sections"] for i in s["items"] for x in i.get("bullets", [])
                  if "2 hours" in x["text"]][0]
        bullet["text"] = "Automated the weekly reservation report with a Python script, saving 2 hours of staff time per week"
        self.assertIn("E_ESTIMATE_AS_MEASURE", audit(b)[0])

    def test_extracted_text_is_utf8_whatever_the_console(self):
        import zipfile
        folder = tempfile.mkdtemp(prefix="cvats-utf8-")
        path = os.path.join(folder, "cv.docx")
        body = ('<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body>'
                '<w:p><w:r><w:t>Python • SQL – Kraków</w:t></w:r></w:p></w:body></w:document>')
        with zipfile.ZipFile(path, "w") as z:
            z.writestr("word/document.xml", body)
        env = dict(os.environ, PYTHONIOENCODING="cp1252")  # a redirected Windows console
        r = subprocess.run([sys.executable, os.path.join(SCRIPTS, "check_docs.py"), "--text", path],
                           capture_output=True, env=env)
        self.assertEqual(r.returncode, 0, r.stderr.decode("utf-8", "replace"))
        self.assertIn("Python • SQL – Kraków", r.stdout.decode("utf-8"))

    def test_verdicts_from_several_rounds_combine(self):
        """A re-audit judges only the changed targets; its file overrides the earlier verdicts of those targets."""
        import contextlib
        import io
        b = load("brindlewood")
        b["strategy"]["value_proposition"] += " Tested with pytest."
        folder = tempfile.mkdtemp(prefix="cvats-rounds-")
        pkg = os.path.join(folder, "package.json")
        with open(pkg, "w", encoding="utf-8") as fh:
            json.dump(b, fh)
        fresh = verdicts_for(audit(b)[1], base=reference_verdicts())
        vp = [v for v in fresh["verdicts"] if v["target"] == "strategy.value_proposition"][0]
        first = {"verdicts": [dict(v, fingerprint="0" * 16) if v is vp else v for v in fresh["verdicts"]]}
        files = []
        for name, data in (("round1.json", first), ("round2.json", {"verdicts": [vp]})):
            files.append(os.path.join(folder, name))
            with open(files[-1], "w", encoding="utf-8") as fh:
                json.dump(data, fh)
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            rc = audit_package.main([pkg, "--root", ROOT, "--verdicts", files[0]])
        self.assertEqual(rc, 1, "the first round alone is stale for the value proposition")
        with contextlib.redirect_stdout(out):
            rc = audit_package.main([pkg, "--root", ROOT, "--verdicts"] + files)
        self.assertEqual(rc, 0, out.getvalue()[-600:])

    def test_file_names_keep_every_letter_of_the_name(self):
        self.assertEqual(build_docs.slug("Łucja Testard"), "Lucja-Testard")
        self.assertEqual(build_docs.slug("Søren Weiß"), "Soren-Weiss")
        self.assertEqual(build_docs.slug("Анна Петрова"), "Анна-Петрова")  # no ASCII form: kept as written
        self.assertEqual(build_docs.slug("Zoé Martin"), "Zoe-Martin")

    def test_scripts_print_utf8_whatever_the_console(self):
        b = load("brindlewood")
        b["cv"]["name"] = "Łucja Testard"  # no PDF possible: the report must still reach the caller
        b["letter"]["paragraphs"][0]["text"] += " Łódź"
        folder = tempfile.mkdtemp(prefix="cvats-cp1252-")
        pkg = os.path.join(folder, "package.json")
        with open(pkg, "w", encoding="utf-8") as fh:
            json.dump(b, fh, ensure_ascii=False)
        env = dict(os.environ, PYTHONIOENCODING="cp1252")  # a redirected Windows console
        for args in (["audit_package.py", pkg, "--root", ROOT, "--targets"], ["build_docs.py", pkg, "--out", folder]):
            r = subprocess.run([sys.executable, os.path.join(SCRIPTS, args[0])] + args[1:], capture_output=True,
                               env=env)
            self.assertNotIn(b"UnicodeEncodeError", r.stderr, args[0])
            self.assertIn("Ł", json.dumps(json.loads(r.stdout.decode("utf-8")), ensure_ascii=False), args[0])

    def test_verdict_files_may_come_in_any_order(self):
        """With a shell glob, audit.round9.json sorts after audit.round24.json: the current verdict must still win."""
        import contextlib
        import io
        b = load("brindlewood")
        b["strategy"]["value_proposition"] += " Tested with pytest."
        folder = tempfile.mkdtemp(prefix="cvats-order-")
        pkg = os.path.join(folder, "package.json")
        with open(pkg, "w", encoding="utf-8") as fh:
            json.dump(b, fh)
        fresh = verdicts_for(audit(b)[1], base=reference_verdicts())
        vp = [v for v in fresh["verdicts"] if v["target"] == "strategy.value_proposition"][0]
        older = {"verdicts": [dict(v, fingerprint="0" * 16) if v is vp else v for v in fresh["verdicts"]]}
        files = []
        for name, data in (("audit.round24.json", {"verdicts": [vp]}), ("audit.round9.json", older)):
            files.append(os.path.join(folder, name))
            with open(files[-1], "w", encoding="utf-8") as fh:
                json.dump(data, fh)
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            rc = audit_package.main([pkg, "--root", ROOT, "--verdicts"] + files)
        self.assertEqual(rc, 0, out.getvalue()[-600:])

    def test_levels_must_be_objects(self):
        b = load("brindlewood")
        [e for e in b["evidence"] if e.get("levels")][0]["levels"] = ["English: fluent"]
        self.assertIn("E_STRUCTURE", audit(b)[0])

    def test_evidence_lists_must_be_lists(self):
        """A string iterates as characters: one excerpt given as text must not pass as a list of strings."""
        b = load("brindlewood")
        evidence(b, "E4")["excerpts"] = " ".join(evidence(b, "E4")["excerpts"])
        self.assertIn("E_STRUCTURE", audit(b)[0])

    def test_id_lists_given_as_text_are_named(self):
        b = load("brindlewood")
        b["questions"][0]["need"] = "R5, C10"
        codes, au = audit(b)
        self.assertIn("E_STRUCTURE", codes)
        self.assertTrue(any("questions[0].need" in e["msg"] for e in au.errors), au.errors)
        b = load("brindlewood")  # an argument's need is text by contract
        self.assertIsInstance(b["strategy"]["arguments"][0]["need"], str)
        self.assertNotIn("E_STRUCTURE", audit(b)[0])

    def test_lists_of_text_instead_of_objects_are_named(self):
        """An agent's list of strings (or null) must give a readable E_STRUCTURE, not a Python traceback."""
        def bullets(p):
            for s in p["cv"]["sections"]:
                for i in s["items"]:
                    if i.get("bullets"):
                        i["bullets"] = [x["text"] for x in i["bullets"]]
        cases = {
            "sources": lambda p: p.__setitem__("sources", [s["url"] for s in p["sources"]]),
            "company_claims": lambda p: p["company_claims"][0].pop("id"),
            "evidence": lambda p: p["evidence"].append("E99 something"),
            "job.requirements": lambda p: p["job"]["requirements"].append("Kubernetes"),
            "letter.paragraphs": lambda p: p["letter"].__setitem__(
                "paragraphs", [x["text"] for x in p["letter"]["paragraphs"]]),
            ".bullets": bullets,
            "interview": lambda p: p.__setitem__("interview", [q["talking_points"] for q in p["interview"]]),
            "strategy.arguments": lambda p: p["strategy"].__setitem__("arguments", None),
            "strategy.contract_fit": lambda p: p["strategy"]["contract_fit"].append("K9 location unknown"),
            "questions": lambda p: p.__setitem__("questions", [q["ask"] for q in p["questions"]]),
        }
        for path, mutate in cases.items():
            with self.subTest(path):
                b = load("brindlewood")
                mutate(b)
                codes, au = audit(b)
                self.assertIn("E_STRUCTURE", codes)
                self.assertTrue(any(path in e["msg"] for e in au.errors), au.errors)
        b = load("brindlewood")
        b["strategy"]["arguments"].append("R5 gap")
        self.assertIn("E_STRUCTURE", audit(b)[0])

    def test_value_proposition_may_quote_the_needs_its_arguments_cite(self):
        b = load("brindlewood")
        self.assertEqual(b["strategy"]["arguments"][0]["need"], "C2, C4, R1-R3")  # posting S4 via R1-R3 and C4
        au = audit(b)[1]
        target = "strategy.value_proposition"
        errs = target_errors(au, verdicts_for(au, {target: {
            "source": "S4", "excerpt": "experience deploying services on Kubernetes"}}, reference_verdicts()), target)
        self.assertFalse(errs & {"E_VERDICT_SOURCE", "E_VERDICT_EXCERPT"}, errs)
        errs = target_errors(au, verdicts_for(au, {target: {  # the about page backs no argued need
            "source": "S1", "excerpt": "The company is based in Indianapolis, Indiana."}}, reference_verdicts()), target)
        self.assertIn("E_VERDICT_SOURCE", errs)

    def test_fixtures_add_no_food_to_the_pantry(self):
        """No candidate file says "food"; the reference packages must not add it to the Northbridge Community Pantry."""
        folder = os.path.join(ROOT, "tests", "fixtures", "candidate")
        for f in os.listdir(folder):
            self.assertNotIn("food", read(os.path.join(folder, f)).lower(), f)
        for path in [os.path.join(PKGS, n + ".json") for n in PACKAGES] + [LEGACY]:
            p = load(path)
            text = " ".join(p["letter"]["paragraphs"][i]["text"] for i in range(len(p["letter"]["paragraphs"])))
            text += " " + " ".join(x["text"] for s in p["cv"]["sections"] for i in s["items"]
                                   for x in i.get("bullets", []))
            self.assertNotIn("food", text.lower(), os.path.basename(path))


from test_review_regressions import ReviewRegressionTests


if __name__ == "__main__":
    unittest.main()
