#!/usr/bin/env python3
"""Live end-to-end tests: run the real /cv-ats-us skill headless on fictitious fixtures, then verify.

Costs API usage. Never applies anywhere; outputs go to applications/_e2e/ (git-ignored).
  python3 tests/e2e/run_e2e.py                      # run all scenarios (parallel) then validate
  python3 tests/e2e/run_e2e.py --only brindlewood   # one scenario
  python3 tests/e2e/run_e2e.py --validate-only      # re-check existing outputs
Options: --model (default: haiku), --budget USD per scenario (default 4), --timeout seconds (default 1800).
"""
import argparse
import datetime
import glob
import itertools
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from concurrent.futures import ThreadPoolExecutor

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SCRIPTS = os.path.join(ROOT, ".claude", "skills", "cv-ats-us", "scripts")
OUT = os.path.join(ROOT, "applications", "_e2e")
FIX = "tests/fixtures"
CAND = "%s/candidate/camille-testard-cv.md and %s/candidate/projects.md" % (FIX, FIX)
TEST_NOTE = ("Test context: candidate and company are FICTITIOUS. Fixture convention: each local company copy is "
             "a faithful, dated snapshot of a page that is live in this fictitious world, so record it with its URL, "
             "reachable: true, retrieved_via: user-provided snapshot and copy_path (the local file). Do not fetch the "
             ".example URLs and do no "
             "web search about this company. Send nothing to anyone. Write package.json, the documents and "
             "dossier.md in the output folder given.")
ASK = ("Tailor my CV to this posting and write a cover letter explaining why my projects are relevant to this "
       "company.")
SCENARIOS = {
    "brindlewood": "/cv-ats-us package US %s Posting (local copy, URL in its header): "
                   "%s/companies/brindlewood-freight/job-posting.md. Company pages: "
                   "%s/companies/brindlewood-freight/about.md, press-lanes-api.md, blog-routing-python.md, team.md (same "
                   "folder). My documents: %s. Output folder: applications/_e2e/brindlewood. %s"
                   % (ASK, FIX, FIX, CAND, TEST_NOTE),
    "halvane": "/cv-ats-us package US %s Posting (local copy, URL in its header): "
               "%s/companies/halvane-retail/job-posting.md. Company pages: %s/companies/halvane-retail/about.md, "
               "press-shelfsight.md, blog-accessibility.md, careers.md (same folder). My documents: %s. Output folder: "
               "applications/_e2e/halvane. %s" % (ASK, FIX, FIX, CAND, TEST_NOTE),
    "tamberlin": "/cv-ats-us package US %s Posting (local copy, URL in its header): "
                 "%s/companies/tamberlin-print/job-posting.md. Company pages: %s/companies/tamberlin-print/about.md, "
                 "news-order-portal.md (same folder). My documents: %s. Output folder: applications/_e2e/tamberlin. %s"
                 % (ASK, FIX, FIX, CAND, TEST_NOTE),
    "orvanta": "/cv-ats-us package US %s Posting (local copy, URL in its header): "
               "%s/companies/orvanta-group/job-posting.md. Company pages: %s/companies/orvanta-group/"
               "annual-report-2025.md, digital-unit.md, blog-one-pipeline.md (same folder). My documents: %s. Output "
               "folder: applications/_e2e/orvanta. %s" % (ASK, FIX, FIX, CAND, TEST_NOTE),
    "quarrelane": "/cv-ats-us package FR %s Posting: https://careers.quarrelane-fixture.invalid/jobs/4471 - if the "
                  "link does not respond, here is the copy I pasted: "
                  "%s/companies/quarrelane-analytics/job-posting-pasted.md. Careers page (local copy): "
                  "%s/companies/quarrelane-analytics/careers-snippet.md. My documents: %s. Output folder: "
                  "applications/_e2e/quarrelane. Test context: candidate and company are FICTITIOUS; you may try "
                  "one web search for \"Quarrelane Analytics\" (it may return nothing). Send nothing to anyone."
                  % (ASK, FIX, FIX, CAND),
}
TOOLS = ["Read", "Write", "Edit", "Glob", "Grep", "WebFetch", "WebSearch", "Agent", "Skill",
         "Bash(python3 *)", "Bash(python *)", "Bash(py *)", "Bash(mkdir *)", "Bash(ls *)"]  # python/py: Windows


def make_sandbox(name):
    """Throwaway project with the skill, agents and inputs only: the reference packages (expected answers)
    in tests/fixtures/packages are left out, so a run cannot copy them."""
    box = tempfile.mkdtemp(prefix="cvats-e2e-%s-" % name)
    shutil.copytree(os.path.join(ROOT, ".claude"), os.path.join(box, ".claude"))
    shutil.copy(os.path.join(ROOT, "AGENTS.md"), box)
    for sub in ("candidate", "companies"):
        shutil.copytree(os.path.join(ROOT, FIX, sub), os.path.join(box, FIX, sub))
    return box


def run_claude(name, model, budget, timeout):
    """One live run. Earlier outputs of this scenario are deleted first, so a run that writes nothing can never be
    validated with the files of a previous run; the exit status is recorded in <name>.run.json."""
    os.makedirs(OUT, exist_ok=True)
    shutil.rmtree(os.path.join(OUT, name), ignore_errors=True)
    for suffix in (".transcript.jsonl", ".run.json"):
        if os.path.exists(os.path.join(OUT, name + suffix)):
            os.remove(os.path.join(OUT, name + suffix))
    box = make_sandbox(name)
    cmd = ["claude", "-p", SCENARIOS[name], "--model", model, "--permission-mode", "acceptEdits",
           "--allowedTools"] + TOOLS + ["--max-budget-usd", str(budget), "--no-session-persistence",
                                        "--output-format", "stream-json", "--verbose"]
    record = {"model": model, "started": datetime.datetime.now().isoformat(timespec="seconds"), "timed_out": False}
    try:
        r = subprocess.run(cmd, cwd=box, capture_output=True, text=True, timeout=timeout)
        out, record["returncode"] = r.stdout, r.returncode
    except subprocess.TimeoutExpired as e:
        out = (e.stdout or b"").decode() if isinstance(e.stdout, bytes) else (e.stdout or "")
        record.update(returncode=None, timed_out=True)
    produced = os.path.join(box, "applications", "_e2e", name)
    if os.path.isdir(produced):
        shutil.copytree(produced, os.path.join(OUT, name))
    shutil.rmtree(box, ignore_errors=True)
    with open(os.path.join(OUT, name + ".transcript.jsonl"), "w", encoding="utf-8") as f:
        f.write(out)
    with open(os.path.join(OUT, name + ".run.json"), "w", encoding="utf-8") as f:
        json.dump(record, f, indent=2)
    return name


def script(name, *args):
    r = subprocess.run([sys.executable, os.path.join(SCRIPTS, name)] + list(args), capture_output=True, text=True)
    try:
        return r.returncode, json.loads(r.stdout)
    except ValueError:
        return r.returncode, {"raw": r.stdout[-2000:], "stderr": r.stderr[-2000:]}


def allowed_numbers(*patterns):
    nums = set()
    for pat in patterns:
        for p in glob.glob(os.path.join(ROOT, pat), recursive=True):
            nums |= set(re.findall(r"\d+", open(p, encoding="utf-8").read()))
    today = datetime.date.today()
    return nums | {str(today.year), str(today.day), "%02d" % today.day, str(today.month), "1", "2"}


# Expected company_profile.type: from each company's own size/stage facts; Quarrelane's SMEs are its customers.
COMPANY_TYPES = {"brindlewood": {"startup"}, "halvane": {"mid-size"}, "tamberlin": {"sme"},
                 "orvanta": {"multinational", "large"}, "quarrelane": {"unknown"}}
US_SAME_TITLE = ["brindlewood", "halvane", "tamberlin", "orvanta"]

AGENTS = ["company-researcher", "job-intelligence", "candidate-evidence", "recruitment-strategist",
          "application-auditor"]


def events(name):
    """Top-level transcript events in order (None if no transcript): ("use", id, tool, input),
    ("result", tool_use_id, text, is_error) and ("text", text) for other messages (e.g. background-agent notices)."""
    path = os.path.join(OUT, name + ".transcript.jsonl")
    if not os.path.exists(path):
        return None
    out = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            try:
                m = json.loads(line)
            except ValueError:
                continue
            if m.get("parent_tool_use_id") or m.get("type") not in ("assistant", "user"):
                continue
            content = (m.get("message") or {}).get("content", [])
            for c in [{"type": "text", "text": content}] if isinstance(content, str) else content:
                if c.get("type") == "tool_use":
                    out.append(("use", c.get("id"), c.get("name"), c.get("input") or {}))
                elif c.get("type") == "tool_result":
                    body = c.get("content")
                    text = body if isinstance(body, str) else " ".join(
                        x.get("text", "") for x in body or [] if isinstance(x, dict))
                    out.append(("result", c.get("tool_use_id"), text, bool(c.get("is_error"))))
                elif c.get("type") == "text" and m.get("type") == "user":
                    out.append(("text", c.get("text", "")))
    return out


def tool_calls(name):
    """(tool name, input) of each top-level tool call, in order (None if no transcript)."""
    ev = events(name)
    return None if ev is None else [(e[2], e[3]) for e in ev if e[0] == "use"]


def delegations(name):
    """subagent_type of each top-level Agent call in the stream-json transcript (None if no transcript)."""
    calls = tool_calls(name)
    return None if calls is None else [i.get("subagent_type") for n, i in calls if n in ("Agent", "Task")]


STRATEGY_NOTE = "## strategy"  # first line of the recruitment-strategist output contract


def strategy_before_writing(name):
    """True if the recruitment-strategist's final note was back before the first write into the output folder
    (None: no transcript). A call, a background launch acknowledgement or a failed call is not the note.
    SKILL.md: write nothing, not even package.json, until the strategy note is back."""
    evs = events(name)
    if evs is None:
        return None
    calls, ready = set(), False
    for e in evs:
        if e[0] == "use" and e[2] in ("Agent", "Task") and e[3].get("subagent_type") == "recruitment-strategist":
            calls.add(e[1])
        elif e[0] == "result" and e[1] in calls and not e[3] and STRATEGY_NOTE in e[2]:
            ready = True
        elif e[0] == "text" and calls and STRATEGY_NOTE in e[1]:  # background agent's completion notice
            ready = True
        elif e[0] == "use":
            n, i = e[2], e[3]
            target = str(i.get("file_path", "")) + " " + str(i.get("command", "") if n == "Bash" else "")
            if n in ("Write", "Edit", "NotebookEdit", "Bash") and "applications" in target.replace("\\", "/") and (
                    n != "Bash" or "build_docs" in target or ">" in target):
                return ready
    return ready


def validate(name):
    d = os.path.join(OUT, name)
    checks = []

    def ok(label, cond, detail=""):
        checks.append({"check": label, "ok": bool(cond), "detail": detail})

    run_path = os.path.join(OUT, name + ".run.json")
    run = None
    if os.path.exists(run_path):
        with open(run_path, encoding="utf-8") as f:
            run = json.load(f)
    ok("run recorded and exited 0 (outputs belong to this run)", run and run.get("returncode") == 0, run)
    path = os.path.join(OUT, name + ".transcript.jsonl")
    if os.path.exists(path):  # the run must never see the expected answers (main session or subagents)
        with open(path, encoding="utf-8") as f:
            peeks = [l for l in f if '"tool_use"' in l and "fixtures/packages" in l]
        ok("never opened the reference packages", not peeks, "%d tool calls touched them" % len(peeks))
    calls = delegations(name)
    if calls is not None:
        ok("all 5 agents delegated, strategist before auditor", set(AGENTS) <= set(calls) and
           calls.index("recruitment-strategist") < calls.index("application-auditor"), calls)
        ok("strategist called before the first write", strategy_before_writing(name))

    pkg_path = os.path.join(d, "package.json")
    ok("package.json written", os.path.exists(pkg_path))
    if not os.path.exists(pkg_path):
        return {"scenario": name, "ok": False, "checks": checks}
    with open(pkg_path, encoding="utf-8") as f:
        pkg = json.load(f)
    ok("package uses the current contract (meta.schema 2)", pkg.get("meta", {}).get("schema") == 2, pkg.get("meta"))
    rc, au = script("audit_package.py", pkg_path, "--root", ROOT)  # fixture paths are relative to the project
    ok("audit_package passes", rc == 0, [e["code"] + ": " + e["msg"] for e in au.get("errors", [])])
    verdicts = os.path.join(d, "audit.json")  # first audit, then the re-audits of changed targets (SKILL.md step 6)
    rounds = sorted(glob.glob(os.path.join(d, "audit.round*.json")))
    rc, av = (script("audit_package.py", pkg_path, "--root", ROOT, "--verdicts", verdicts, *rounds)
              if os.path.exists(verdicts) else (1, {}))
    ok("application-auditor verdicts cover every target and quote their sources", rc == 0,
       [e["code"] + ": " + e["msg"] for e in av.get("errors", [])] or "audit.json missing")
    docs = sorted(glob.glob(os.path.join(d, "*.docx")) + glob.glob(os.path.join(d, "*.pdf")))
    ok("DOCX + PDF for CV and letter", len(docs) >= 4, [os.path.basename(x) for x in docs])
    if docs:
        rc, cd = script("check_docs.py", *docs, "--package", pkg_path)
        ok("check_docs passes", rc == 0, [(os.path.basename(r["file"]), r["errors"]) for r in cd.get("results", [])])
    ok("dossier.md written", os.path.exists(os.path.join(d, "dossier.md")))
    prof = pkg.get("company_profile") or {}
    ok("company type from the company's own facts", prof.get("type") in COMPANY_TYPES[name], prof)
    levers = [a.get("lever") for a in pkg.get("strategy", {}).get("adaptation") or []]
    ok("adaptation recorded per lever", len(levers) == 6 and set(levers) ==
       {"positioning", "experience", "projects", "keywords", "letter", "register"}, levers)
    sys.path.insert(0, SCRIPTS)
    import check_docs
    cv_pdf = [x for x in docs if x.endswith(".pdf") and re.search(r"(Resume|CV)", os.path.basename(x))]
    lt_pdf = [x for x in docs if x.endswith(".pdf") and re.search(r"(Letter|Lettre)", os.path.basename(x))]
    cv_text = check_docs.pdf_info(cv_pdf[0])["text"] if cv_pdf else ""
    lt_text = check_docs.pdf_info(lt_pdf[0])["text"] if lt_pdf else ""
    # Independent of the model's own bookkeeping: every number must exist in the fixture inputs.
    allowed = allowed_numbers(FIX + "/candidate/*.md", FIX + "/companies/%s*/*.md" % name[:5])
    stray = sorted(set(re.findall(r"\d+", cv_text + "\n" + lt_text)) - allowed)
    ok("no number absent from inputs (d: no invented metrics)", not stray, stray)
    ok("ShelfScan never given a metric", not re.search(r"ShelfScan[^\n]*\d+\s*%", cv_text + lt_text))
    if name == "brindlewood":
        ok("(c) Kubernetes not claimed in CV", "kubernetes" not in cv_text.lower())
        ok("(c) Go not listed as a skill", not re.search(r"\bGo\b|Golang", cv_text))
    if name == "orvanta":
        ok("(c) code review / Azure not claimed in CV", not re.search(r"code review|azure", cv_text, re.I))
        ok("letter names the unit's product", "fieldlink" in lt_text.lower())
    if name == "tamberlin":
        ok("(c) Power Automate not claimed in CV", "power automate" not in cv_text.lower())
    if name == "quarrelane":
        meta = pkg.get("meta", {})
        ok("(b) research_level limited", meta.get("research_level") == "limited")
        bad = [s for s in pkg.get("sources", []) if ".invalid" in str(s.get("url", ""))]
        ok("(e) unreachable URL recorded", bad and all(s.get("reachable") is False for s in bad), bad)
        ok("(e) posting not presented as open", pkg.get("job", {}).get("posting_status") != "open")
        ok("(e) warning raised", bool(meta.get("warnings")))
        ok("(c) pandas not claimed in CV", "pandas" not in cv_text.lower())
        ok("FR market: A4", cv_pdf and check_docs.pdf_info(cv_pdf[0])["box"][2] < 600)
    return {"scenario": name, "ok": all(c["ok"] for c in checks), "checks": checks}


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--only", action="append", choices=sorted(SCENARIOS))
    ap.add_argument("--model", default="haiku")
    ap.add_argument("--budget", type=float, default=4.0)
    ap.add_argument("--timeout", type=int, default=1800)
    ap.add_argument("--validate-only", action="store_true")
    a = ap.parse_args()
    names = a.only or sorted(SCENARIOS)
    if not a.validate_only:
        with ThreadPoolExecutor(len(names)) as ex:
            list(ex.map(lambda n: run_claude(n, a.model, a.budget, a.timeout), names))
    results = [validate(n) for n in names]
    for x, y in itertools.combinations([n for n in US_SAME_TITLE if n in names], 2):
        a, b = (os.path.join(OUT, n, "package.json") for n in (x, y))
        if os.path.exists(a) and os.path.exists(b):
            rc, cmp_ = script("audit_package.py", a, "--compare", b)
            sim = cmp_.get("compare", {}).get("letter_similarity")
            results.append({"scenario": "(a) differentiation %s vs %s" % (x, y),
                            "ok": not cmp_.get("compare", {}).get("errors") and sim is not None,
                            "checks": [{"check": "letter similarity < 0.75", "detail": sim}]})
    print(json.dumps(results, indent=2, ensure_ascii=False))
    return 0 if all(r["ok"] for r in results) else 1


if __name__ == "__main__":
    sys.exit(main())
