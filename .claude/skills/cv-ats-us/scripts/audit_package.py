#!/usr/bin/env python3
"""Deterministic truthfulness audit of an application package (see references/package-format.md).

Blocking errors: unsourced company facts, unsupported candidate claims, numbers absent from the
cited evidence, missing technologies slipped into the CV, invented recipients, hypotheses stated as
facts, ATS-score promises, placeholders, rebadged letters (--compare), a company type without a
sourced size/stage/structure fact, adaptations not traced to a verified need or justified by size alone,
company-size clichés.
It complements, never replaces, the application-auditor agent's reading.

Usage:
  python3 audit_package.py PACKAGE.json [--compare OTHER.json]
Exit code 1 if any error.
"""
import argparse
import difflib
import json
import re
import sys

STATUSES = {"confirmed", "hypothesis", "unavailable"}
STAGES = {"idea", "prototype", "delivered", "deployed", "used", "measured", "coursework", "experience",
          "self-reported"}
DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
HEDGES = re.compile(r"\b(may|might|could|likely|appears?|seems?|suggests?|if|perhaps|presumably|"
                    r"semble(?:nt)?|pourrai(?:t|ent)|probablement|sans doute|si|peut-être|vraisemblablement)\b",
                    re.I)
GENERIC_RECIPIENT = re.compile(r"hiring|recruit|team|committee|to whom|madame|monsieur|équipe|equipe|"
                               r"recrutement|comité|comite|ressources humaines", re.I)
ATS_PROMISE = re.compile(r"\d{1,3}\s*%\s*(ats|match|compatib)|ats[- ]?(score|proof|guaranteed|optimi[sz]ed to pass)|"
                         r"\bguarantee[sd]?\b|\bgaranti(e|t|s)?\b|pass(es)? (the |any )?ats", re.I)
PLACEHOLDER = re.compile(r"\bTODO\b|\bTBD\b|XXX|\{\{|\[(?:name|company|role|insert|à compléter|a completer)[^\]]*\]"
                         r"|lorem ipsum", re.I)
DISCLAIMER = re.compile(r"\((?:self[- ]reported|auto[- ]d[ée]clar\w*|d[ée]claratif|non mesur\w*|estimate[ds]?|"
                        r"estimation)[^)]*\)|no other measurement|(?:only|sole) measurement|present it as such|"
                        r"sans autre mesure|non d'une mesure|pas d'une mesure", re.I)
LETTER_CITATION = re.compile(r"https?://|\((?:company |engineering )?(?:blog|press release|website|source)[^)]*\)|"
                             r"\b(?:dated|consulté le|accessed) \d{4}-\d{2}-\d{2}", re.I)
FLATTERY = re.compile(r"dream (company|job)|world[- ]class|industry leader|leader incontesté|entreprise de rêve|"
                      r"i have always admired|j'ai toujours admiré|passionate about your company", re.I)
PROFILE_TYPES = {"startup", "sme", "mid-size", "large", "multinational", "public-sector", "non-profit", "unknown"}
LEVERS = {"positioning", "experience", "projects", "keywords", "letter", "register"}
# A company type must rest on what the company says about itself (size, stage, structure), not its customers.
SIZE_SIGNAL = re.compile(r"\b(?:employ\w*|staff|people|team of|headcount|founded|seed|series [a-e]|funding|raised|"
                         r"countries|subsidiar\w*|family[- ]owned|listed on|salarié\w*|collaborateurs|effectif|"
                         r"fondée?|levée|filiale|pays)\b", re.I)
SIZE_CLICHE = re.compile(r"fast[- ]paced (?:start[- ]?up|environment|company)|wear(?:ing)? (?:many|multiple|several|"
                         r"different) hats|start[- ]?up (?:mindset|spirit|culture|DNA|energy)|"
                         r"(?:global|world|industry|market) leader (?:like|such as) yours|"
                         r"(?:large|big) (?:corporation|company|organi[sz]ation|group) (?:like|such as) yours|"
                         r"company of your size|esprit start[- ]?up|culture start[- ]?up|grand groupe comme le vôtre|"
                         r"leader mondial comme le vôtre|(?:entreprise|structure) à taille humaine", re.I)
LETTER_MAX_WORDS = 300
NUM = re.compile(r"\d+(?:[.,]\d+)?")


def term_in(term, text):
    """Whole-word match; short terms (e.g. 'Go') are case-sensitive to avoid false hits."""
    flags = 0 if len(term) <= 3 else re.I
    return re.search(r"(?<![\w])%s(?![\w])" % re.escape(term), text, flags) is not None


def nums(text):
    text = re.sub(r"(?<=\d)[,   ](?=\d{3}\b)", "", text)
    return set(NUM.findall(text))


class Audit:
    def __init__(self, pkg):
        self.p, self.errors, self.warnings = pkg, [], []

    def err(self, code, msg):
        self.errors.append({"code": code, "msg": msg})

    def warn(self, code, msg):
        self.warnings.append({"code": code, "msg": msg})

    def run(self):
        p = self.p
        for key in ("meta", "sources", "company_claims", "evidence", "cv"):
            if key not in p:
                self.err("E_STRUCTURE", "missing top-level key '%s'" % key)
        if self.errors:
            return self
        self.src = {s["id"]: s for s in p["sources"]}
        self.claims = {c["id"]: c for c in p["company_claims"]}
        self.ev = {e["id"]: e for e in p["evidence"]}
        for coll, name in ((p["sources"], "source"), (p["company_claims"], "claim"), (p["evidence"], "evidence")):
            ids = [x.get("id") for x in coll]
            if len(ids) != len(set(ids)):
                self.err("E_STRUCTURE", "duplicate %s ids" % name)
        self.check_sources_and_claims()
        self.check_profile()
        self.check_evidence()
        self.check_cv()
        self.check_letter()
        self.check_job()
        self.check_text_hygiene()
        self.check_strategy()
        return self

    # -- company side
    def check_sources_and_claims(self):
        for s in self.p["sources"]:
            if s.get("kind") in ("candidate",):
                continue
            if not s.get("accessed") or not DATE.match(str(s.get("accessed"))):
                self.warn("W_SOURCE_DATE", "source %s lacks accessed date YYYY-MM-DD" % s.get("id"))
            if "published" not in s:
                self.warn("W_SOURCE_DATE", "source %s lacks published date (use 'unknown')" % s.get("id"))
        seen = {}
        for s in self.p["sources"]:
            if str(s.get("url", "")).startswith("http") and "reachable" in s:
                seen.setdefault(s["url"], set()).add(bool(s["reachable"]))
        for url, states in seen.items():
            if len(states) > 1:
                self.err("E_SOURCE_CONTRADICTION", "%s recorded both reachable and unreachable: a pasted copy of a "
                                                   "dead URL keeps reachable=false" % url)
        confirmed = 0
        for c in self.p["company_claims"]:
            st = c.get("status")
            if st not in STATUSES:
                self.err("E_CLAIM_STATUS", "claim %s has invalid status %r" % (c.get("id"), st))
                continue
            if st != "confirmed":
                continue
            confirmed += 1
            refs = c.get("sources") or []
            if not refs:
                self.err("E_CLAIM_UNSOURCED", "confirmed claim %s has no source" % c["id"])
            for r in refs:
                s = self.src.get(r)
                if not s:
                    self.err("E_BAD_REF", "claim %s cites unknown source %s" % (c["id"], r))
                elif not re.match(r"https?://", str(s.get("url", ""))) or not s.get("title"):
                    self.err("E_CLAIM_UNSOURCED", "claim %s: source %s lacks URL or title" % (c["id"], r))
                elif s.get("reachable") is False:
                    self.err("E_CLAIM_UNREACHABLE", "claim %s relies on unreachable source %s" % (c["id"], r))
                elif s.get("kind") == "candidate":
                    self.err("E_CLAIM_UNSOURCED", "claim %s relies on a candidate document" % c["id"])
                elif not DATE.match(str(s.get("accessed", ""))):
                    self.err("E_CLAIM_UNSOURCED", "claim %s: source %s lacks accessed date" % (c["id"], r))
        self.confirmed = confirmed
        level = self.p["meta"].get("research_level", "standard")
        if confirmed < 3 and level != "limited":
            self.err("E_RESEARCH_LEVEL", "only %d confirmed company facts: set meta.research_level='limited' "
                                         "and personalise cautiously" % confirmed)

    def check_profile(self):
        prof = self.p.get("company_profile")
        self.profile_basis = set()
        if prof is None:
            if self.p.get("job", {}).get("requirements"):
                self.warn("W_PROFILE_MISSING", "no company_profile: record type ('unknown' if undocumented), "
                                               "basis, hiring unit and hiring triggers")
            return
        t = prof.get("type")
        if t not in PROFILE_TYPES:
            self.err("E_PROFILE_TYPE", "company_profile.type %r not in %s" % (t, sorted(PROFILE_TYPES)))
        basis = list(prof.get("basis") or [])
        self.profile_basis = set(basis)
        for c in basis + list(prof.get("hiring_triggers") or []):
            if c not in self.claims:
                self.err("E_BAD_REF", "company_profile cites unknown claim %s" % c)
            elif self.claims[c].get("status") == "unavailable":
                self.err("E_CLAIM_UNAVAILABLE_USED", "company_profile relies on unavailable claim %s" % c)
        if t in PROFILE_TYPES and t != "unknown":
            if not [c for c in basis if self.claims.get(c, {}).get("status") == "confirmed"
                    and SIZE_SIGNAL.search(self.claims[c].get("text", ""))]:
                self.err("E_PROFILE_UNSOURCED", "company_profile.type '%s' needs a confirmed claim stating the company's "
                                                "own size, stage or structure (customer size is not company size); "
                                                "otherwise use 'unknown'" % t)
        unit, L = prof.get("unit"), self.p.get("letter")
        if t in ("large", "multinational") and unit and L:
            body = " ".join(x.get("text", "") for x in L.get("paragraphs", [])).lower()
            parts = [x.strip().lower() for x in re.split(r"\s+[—–-]\s+|,|\(|\)", unit) if len(x.strip()) > 3]
            if not any(x in body for x in parts):
                self.warn("W_UNIT_ABSENT", "letter never names the hiring unit/team (%s): write to the unit, "
                                           "not the group" % unit)

    # -- candidate side
    def check_evidence(self):
        for e in self.p["evidence"]:
            if not e.get("source"):
                self.err("E_EVIDENCE_UNSOURCED", "evidence %s has no source" % e.get("id"))
            if e.get("stage") not in STAGES:
                self.warn("W_STAGE", "evidence %s stage %r not in %s" % (e.get("id"), e.get("stage"), sorted(STAGES)))

    def corpus(self, ev_ids=(), claim_ids=()):
        parts = []
        for i in ev_ids:
            e = self.ev.get(i, {})
            parts += [e.get("title", ""), e.get("dates", "")] + list(e.get("facts", [])) + list(e.get("metrics", []))
            parts += list(e.get("tools", []))
        for i in claim_ids:
            parts.append(self.claims.get(i, {}).get("text", ""))
        return " ".join(parts)

    def check_numbers(self, where, text, ev_ids, claim_ids=()):
        extra = nums(text) - nums(self.corpus(ev_ids, claim_ids))
        if extra:
            self.err("E_METRIC_UNSUPPORTED", "%s: number(s) %s not found in cited evidence %s"
                     % (where, sorted(extra), list(ev_ids)))

    def cv_lines(self):
        cv = self.p["cv"]
        for si, sec in enumerate(cv.get("sections", [])):
            for ii, it in enumerate(sec.get("items", [])):
                if it.get("heading"):
                    for bi, b in enumerate(it.get("bullets", [])):
                        yield "cv.%s[%d].bullets[%d]" % (sec.get("title"), ii, bi), b.get("text", ""), b.get("evidence")
                else:
                    yield "cv.%s[%d]" % (sec.get("title"), ii), it.get("text", ""), it.get("evidence")

    def check_cv(self):
        cv = self.p["cv"]
        all_ev = list(self.ev)
        if cv.get("headline"):
            self.check_numbers("cv.headline", cv["headline"], all_ev)
        for where, text, refs in self.cv_lines():
            if not refs:
                self.err("E_CV_UNSUPPORTED", "%s has no evidence reference" % where)
                continue
            bad = [r for r in refs if r not in self.ev]
            if bad:
                self.err("E_BAD_REF", "%s cites unknown evidence %s" % (where, bad))
            self.check_numbers(where, text, refs)

    def cv_text(self):
        cv = self.p["cv"]
        parts = [cv.get("headline", "")]
        for sec in cv.get("sections", []):
            for it in sec.get("items", []):
                parts += [it.get("heading", ""), it.get("subheading", ""), it.get("text", ""), it.get("label", "")]
                parts += [b.get("text", "") for b in it.get("bullets", [])]
        return "\n".join(parts)

    def gap_terms(self):
        terms = []
        for r in self.p.get("job", {}).get("requirements", []):
            if not r.get("match"):
                terms += r.get("gap_terms", [])
            for m in r.get("match") or []:
                if m not in self.ev:
                    self.err("E_BAD_REF", "requirement %s matches unknown evidence %s" % (r.get("id"), m))
        return terms

    def check_letter(self):
        L = self.p.get("letter")
        gaps = self.gap_terms()
        cvt = self.cv_text()
        for t in gaps:
            if term_in(t, cvt):
                self.err("E_GAP_IN_CV", "missing skill '%s' appears in the CV" % t)
        if not L:
            return
        if not GENERIC_RECIPIENT.search(L.get("salutation", "") + " " + " ".join(L.get("recipient", [])[:1])):
            if L.get("recipient_source") not in self.src:
                self.err("E_RECIPIENT_UNSOURCED", "named recipient without recipient_source: %r" % L.get("salutation"))
        cited_confirmed, has_ev, words = 0, False, 0
        for i, para in enumerate(L.get("paragraphs", [])):
            text = para.get("text", "")
            words += len(re.findall(r"\b[\w'’-]+\b", text))
            ev, cl = para.get("evidence", []) or [], para.get("claims", []) or []
            has_ev = has_ev or bool(ev)
            for c in cl:
                claim = self.claims.get(c)
                if not claim:
                    self.err("E_BAD_REF", "letter paragraph %d cites unknown claim %s" % (i, c))
                elif claim.get("status") == "unavailable":
                    self.err("E_CLAIM_UNAVAILABLE_USED", "letter paragraph %d relies on unavailable claim %s" % (i, c))
                elif claim.get("status") == "hypothesis" and not HEDGES.search(text):
                    self.err("E_HYPOTHESIS_AS_FACT", "paragraph %d uses hypothesis %s without hedging" % (i, c))
                elif claim.get("status") == "confirmed":
                    cited_confirmed += 1
            for r in ev:
                if r not in self.ev:
                    self.err("E_BAD_REF", "letter paragraph %d cites unknown evidence %s" % (i, r))
            self.check_numbers("letter.paragraphs[%d]" % i, text, ev or list(self.ev), cl)
            for t in gaps:
                if term_in(t, text) and not para.get("addresses_gap"):
                    self.err("E_GAP_IN_LETTER", "paragraph %d mentions missing skill '%s' without addresses_gap" % (i, t))
        if not cited_confirmed and self.p["meta"].get("research_level") != "limited":
            self.err("E_LETTER_GENERIC", "letter cites no confirmed company fact")
        if not has_ev:
            self.err("E_LETTER_NO_EVIDENCE", "letter cites no candidate evidence")
        lo, hi, hard_lo, hard_hi = 220, 300, 150, LETTER_MAX_WORDS  # every language: under 300 words
        if not hard_lo <= words <= hard_hi:
            self.err("E_LETTER_LENGTH", "letter body has %d words (limit %d-%d)" % (words, hard_lo, hard_hi))
        elif not lo <= words <= hi:
            self.warn("W_LETTER_LENGTH", "letter body has %d words (target %d-%d)" % (words, lo, hi))
        company = self.p["meta"].get("company", "")
        body = " ".join(x.get("text", "") for x in L.get("paragraphs", []))
        if company and company.lower() not in body.lower():
            self.warn("W_COMPANY_ABSENT", "company name not in letter body")
        self.letter_words = words
        if self.p["meta"].get("language") == "fr" and not re.match(r"\s*Objet\s*:", L.get("subject") or ""):
            self.err("E_FR_SUBJECT", "French letters need a subject line starting with \"Objet :\" (got %r)"
                     % L.get("subject"))

    def check_job(self):
        job = self.p.get("job", {})
        st = job.get("posting_status", "unverified")
        if st in ("closed", "expired", "unverified") and not self.p["meta"].get("warnings"):
            self.err("E_POSTING_STATUS", "posting status '%s' must be surfaced in meta.warnings" % st)

    def check_text_hygiene(self):
        L = self.p.get("letter") or {}
        text = self.cv_text() + "\n" + "\n".join(p.get("text", "") for p in L.get("paragraphs", []))
        text += "\n" + L.get("subject", "") + "\n" + L.get("salutation", "")
        for rx, code in ((ATS_PROMISE, "E_ATS_PROMISE"), (PLACEHOLDER, "E_PLACEHOLDER")):
            m = rx.search(text)
            if m:
                self.err(code, "forbidden text: %r" % m.group(0))
        m = DISCLAIMER.search(text)
        if m:
            self.err("E_DISCLAIMER", "attribute unmeasured figures in the sentence (\"they said in a survey\"), "
                                     "no bracketed or extra disclaimer: %r" % m.group(0))
        m = LETTER_CITATION.search("\n".join(p.get("text", "") for p in L.get("paragraphs", [])))
        if m:
            self.err("E_CITATION_IN_LETTER", "sources belong in dossier.md, not in the letter: %r" % m.group(0))
        m = SIZE_CLICHE.search(text)
        if m:
            self.err("E_SIZE_CLICHE", "company-size cliché: state the sourced fact instead: %r" % m.group(0))
        m = FLATTERY.search(text)
        if m:
            self.warn("W_FLATTERY", "generic flattery: %r" % m.group(0))

    def check_strategy(self):
        args = self.p.get("strategy", {}).get("arguments", [])
        if not args:
            self.warn("W_STRATEGY", "no strategy.arguments: analysis must precede writing")
        elif len(args) > 3:
            self.warn("W_STRATEGY", "more than 3 core arguments")
        for a in args:
            for r in a.get("evidence", []):
                if r not in self.ev:
                    self.err("E_BAD_REF", "strategy argument cites unknown evidence %s" % r)
        adapt = self.p.get("strategy", {}).get("adaptation") or []
        reqs = {r.get("id") for r in self.p.get("job", {}).get("requirements", [])}
        if reqs and not adapt:
            self.err("E_ADAPTATION_MISSING", "strategy.adaptation is empty: record each lever's choice and the "
                                             "verified need (claim or requirement ids) behind it")
        for i, a in enumerate(adapt):
            basis = list(a.get("basis") or [])
            where = "adaptation %d (%s)" % (i, a.get("lever"))
            if a.get("lever") not in LEVERS:
                self.warn("W_LEVER", "%s: lever not in %s" % (where, sorted(LEVERS)))
            bad = [b for b in basis if b not in self.claims and b not in reqs]
            dead = [b for b in basis if self.claims.get(b, {}).get("status") == "unavailable"]
            if not basis or bad or dead:
                self.err("E_ADAPTATION_UNSUPPORTED", "%s: basis %s must cite existing claims or requirements, none "
                                                     "unavailable" % (where, basis))
            elif set(basis) <= self.profile_basis:
                self.err("E_SIZE_ONLY", "%s rests only on company size/stage %s: cite the verified need it serves"
                         % (where, basis))


def letter_words(pkg):
    L = pkg.get("letter") or {}
    text = " ".join(p.get("text", "") for p in L.get("paragraphs", [])).lower()
    for k in ("company", "role"):
        v = pkg.get("meta", {}).get(k, "")
        if v:
            text = text.replace(v.lower(), " ")
    return re.findall(r"[\w']+", text)


def compare(a, b):
    """Differentiation test for the same candidate applying to two companies."""
    errors, warnings = [], []
    wa, wb = letter_words(a), letter_words(b)
    for v in (b["meta"].get("company", ""), b["meta"].get("role", "")):
        wa = [w for w in wa if w not in v.lower().split()]
    for v in (a["meta"].get("company", ""), a["meta"].get("role", "")):
        wb = [w for w in wb if w not in v.lower().split()]
    ratio = difflib.SequenceMatcher(None, wa, wb, autojunk=False).ratio() if wa and wb else 0.0
    if ratio >= 0.75:
        errors.append({"code": "E_REBADGED", "msg": "letters are %.0f%% identical once names are removed" % (ratio * 100)})
    ea = [tuple(x.get("evidence", [])) for x in a.get("strategy", {}).get("arguments", [])]
    eb = [tuple(x.get("evidence", [])) for x in b.get("strategy", {}).get("arguments", [])]
    if ea and ea == eb:
        warnings.append({"code": "W_SAME_ARGUMENTS", "msg": "identical evidence order in both strategies"})
    choices = [sorted(x.get("choice", "") for x in p.get("strategy", {}).get("adaptation", [])) for p in (a, b)]
    if choices[0] and choices[0] == choices[1]:
        warnings.append({"code": "W_SAME_ADAPTATION", "msg": "identical adaptation choices in both strategies"})
    return {"letter_similarity": round(ratio, 3), "errors": errors, "warnings": warnings}


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("package")
    ap.add_argument("--compare")
    a = ap.parse_args(argv)
    pkg = json.load(open(a.package, encoding="utf-8"))
    au = Audit(pkg).run()
    out = {"package": a.package, "errors": au.errors, "warnings": au.warnings,
           "stats": {"confirmed_company_facts": getattr(au, "confirmed", 0),
                     "company_type": (pkg.get("company_profile") or {}).get("type", "missing"),
                     "letter_words": getattr(au, "letter_words", 0)}}
    if a.compare:
        cmp_ = compare(pkg, json.load(open(a.compare, encoding="utf-8")))
        out["compare"] = cmp_
        out["errors"] = out["errors"] + cmp_["errors"]
        out["warnings"] = out["warnings"] + cmp_["warnings"]
    out["ok"] = not out["errors"]
    print(json.dumps(out, indent=2, ensure_ascii=False))
    return 0 if out["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
