#!/usr/bin/env python3
"""Deterministic truthfulness audit of an application package (see references/package-format.md).

Two kinds of rules:
- truth rules, errors for every package (old or new): unsourced company facts, unsupported candidate claims,
  numbers or years absent from the cited evidence, evidence numbers absent from the candidate's own documents,
  missing skills slipped into the CV, invented recipients, hypotheses stated as facts, an "open" posting
  without a reachable source, ATS-score promises, placeholders, rebadged letters (--compare);
- contract rules for new outputs (meta.schema >= 2): mode, evidence excerpts, employment-contract fit, hiring
  context, contribution, questions, level assessment. Older packages get them as warnings (W_...).
It complements, never replaces, the application-auditor agent: --targets lists what the agent must verify and
--verdicts checks that its verdicts cover every target and quote their sources verbatim.

Usage:
  python3 audit_package.py PACKAGE.json [--compare OTHER.json] [--root DIR]
  python3 audit_package.py PACKAGE.json --targets             # verification targets for application-auditor
  python3 audit_package.py PACKAGE.json --verdicts AUDIT.json # check the auditor's verdicts
Relative source paths resolve against --root (default: current directory). Exit code 1 if any error.
"""
import argparse
import datetime
import difflib
import hashlib
import json
import math
import os
import re
import sys
import unicodedata

import build_docs  # same folder: generation settings are validated by the code that uses them

SCHEMA = 2
MODES = {"create", "tailor", "cover-letter", "package"}
LETTER_MODES = {"cover-letter", "package"}
STATUSES = {"confirmed", "hypothesis", "unavailable"}
STAGES = {"idea", "prototype", "delivered", "deployed", "used", "measured", "coursework", "experience",
          "self-reported"}
CONTRACT_TYPES = {"cdi", "cdd", "internship", "alternance", "apprenticeship", "full-time", "part-time",
                  "fixed-term", "freelance", "unknown"}
FIT_STATUSES = {"compatible", "incompatible", "unknown"}
SOURCE_KINDS = {"official", "press-release", "engineering-blog", "job-posting", "press", "user-provided", "candidate"}
LEVEL_MATCH = {"meets", "below", "unknown"}
CONFIDENCE = {"high", "medium", "low"}
PLACEMENT = {"cv", "letter", "both", "interview"}
VERDICTS = {"supported", "partial", "unsupported"}
POSTING_STATUSES = {"open", "closed", "expired", "unverified"}
DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
HEDGES = re.compile(r"\b(may|might|could|likely|appears?|seems?|suggests?|if|perhaps|presumably|"
                    r"semble(?:nt)?|pourrai(?:t|ent)|probablement|sans doute|si|peut-être|vraisemblablement)\b",
                    re.I)
GENERIC_WORDS = {"dear", "hiring", "recruiting", "recruitment", "team", "manager", "managers", "committee", "search",
                 "selection", "talent", "acquisition", "hr", "people", "members", "sir", "madam", "to", "whom", "it",
                 "may", "concern", "hello", "cher", "chère", "bonjour", "équipe", "equipe", "recrutement", "service",
                 "de", "du", "la", "le", "des", "ressources", "humaines", "comité", "comite", "madame", "monsieur",
                 "mesdames", "messieurs", "and", "et", "the", "of"}
CIVILITY = re.compile(r"\b(?:(?:Mr|Mrs|Ms|Miss|Mx|Dr|Prof|Mme|Mlle)\.?|M\.|Madame|Monsieur)\s+"
                      r"(?!(?:Madame|Monsieur)\b)[A-ZÀ-ÖØ-Þ]")
ATS_PROMISE = re.compile(r"\d{1,3}\s*%\s*(ats|match|compatib)|ats[- ]?(score|proof|guaranteed|optimi[sz]ed to pass)|"
                         r"\bguarantee[sd]?\b|\bgaranti(e|t|s)?\b|pass(es)? (the |any )?ats", re.I)
PLACEHOLDER = re.compile(r"\bTODO\b|\bTBD\b|XXX|\{\{|\[(?:name|company|role|insert|à compléter|a completer)[^\]]*\]"
                         r"|lorem ipsum", re.I)
DISCLAIMER = re.compile(r"\((?:self[- ]reported|auto[- ]d[ée]clar\w*|d[ée]claratif|non mesur\w*)[^)]*\)|"
                        r"no other measurement|(?:only|sole) measurement|present it as such|"
                        r"sans autre mesure|non d'une mesure|pas d'une mesure", re.I)
# Who produced a figure: an estimate or a survey stays attributed ("my supervisor estimated", "(estimated by …)").
ATTRIBUTED = re.compile(r"estimat|estim[ée]|survey|sondage|enquête|reported|déclar|\bsaid\b|\bsays?\b|selon|"
                        r"d'après|according to", re.I)
LETTER = re.compile(r"[^\W\d_]")
# contract_fit.field -> job.contract key ('None': compared, but not a contract key)
FIT_FIELDS = {"type": "type", "duration": "duration_months", "rhythm": "rhythm", "start": "start",
              "location": "location", "remote": "remote", "language": None, "authorization": None}
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
STATUTORY_SIGNAL = {
    "non-profit": re.compile(r"\b(?:non[- ]?profit|charit\w*|association|à but non lucratif)\b", re.I),
    "public-sector": re.compile(r"\b(?:public (?:body|agency|authority|institution)|government agency|"
                                r"organisme public|établissement public|collectivité)\b", re.I),
}
SIZE_CLICHE = re.compile(r"fast[- ]paced (?:start[- ]?up|environment|company)|wear(?:ing)? (?:many|multiple|several|"
                         r"different) hats|start[- ]?up (?:mindset|spirit|culture|DNA|energy)|"
                         r"(?:global|world|industry|market) leader (?:like|such as) yours|"
                         r"(?:large|big) (?:corporation|company|organi[sz]ation|group) (?:like|such as) yours|"
                         r"company of your size|esprit start[- ]?up|culture start[- ]?up|grand groupe comme le vôtre|"
                         r"leader mondial comme le vôtre|(?:entreprise|structure) à taille humaine", re.I)
# Level statements. These lists only DETECT a line that states a level; they never decide that two levels are
# equivalent. Language levels must be anchored in leveled evidence; meaning is judged by application-auditor.
LANGUAGE_LEVEL = re.compile(r"\b(?:native|fluent|bilingual|langue maternelle|natif|native|courant|bilingue)\b", re.I)
LANGUAGE_NAME = re.compile(r"\b(?:english|french|spanish|german|italian|portuguese|arabic|chinese|mandarin|japanese|"
                           r"russian|dutch|anglais|français|francais|espagnol|allemand|italien|portugais|arabe|"
                           r"chinois|japonais|russe|néerlandais)\b", re.I)
SKILL_LEVEL = re.compile(r"\b(?:expert|experte|expertise|advanced|proficient|proficiency|intermediate|beginner|"
                         r"conversational|working knowledge|maîtrise|avancé|intermédiaire|débutant|notions)\b", re.I)
CEFR = re.compile(r"(?<![\w])([ABC][12])(?![\w])")
NEED_IDS = re.compile(r"\b([CRK])(\d+)(?:\s*-\s*\1?(\d+))?\b")
NUMBER_WORDS = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9,
                "ten": 10, "eleven": 11, "twelve": 12, "un": 1, "une": 1, "deux": 2, "trois": 3, "quatre": 4,
                "cinq": 5, "six": 6, "sept": 7, "huit": 8, "neuf": 9, "dix": 10, "onze": 11, "douze": 12}
HORIZON = re.compile(r"\b(\d+|%s)\s+(?:[\w’'-]+\s+)?(weeks?|semaines?|months?|mois|years?|ans?|années?)\b"
                     % "|".join(NUMBER_WORDS), re.I)
# Calendar dates ("October 2, 2026", "Le 2 octobre 2026", "2026-10-02", "02/10/2026"): their day and month are
# not figures, so a letter date never reads as the "2 hours" of an estimate. Removed before figures are compared.
MONTH = (r"(?:jan(?:uary|vier|v)?|feb(?:ruary)?|f[ée]v(?:rier|r)?|mar(?:ch|s)?|apr(?:il)?|avr(?:il)?|may|mai|"
         r"june?|juin|july?|juil(?:let)?|aug(?:ust)?|ao[uû]t|sep(?:t(?:ember|embre)?)?|oct(?:ober|obre)?|"
         r"nov(?:ember|embre)?|d[ée]c(?:ember|embre)?)")
DATE_TEXT = re.compile(r"\b\d{4}-\d{1,2}-\d{1,2}\b|\b\d{1,2}[/.]\d{1,2}[/.]\d{4}\b|"
                       r"\b%s\.?\s+\d{1,2}(?:st|nd|rd|th)?\b(?:,?\s+\d{4}\b)?|"
                       r"\b\d{1,2}(?:st|nd|rd|th|er)?\s+(?:of\s+)?%s\b\.?(?:,?\s+\d{4}\b)?" % (MONTH, MONTH), re.I)
LETTER_MAX_WORDS = 300
NUM = re.compile(r"\d+(?:[.,]\d+)?")
YEAR = re.compile(r"\b(?:19|20)\d{2}\b")


def term_in(term, text):
    """Whole-word match; short terms (e.g. 'Go') are case-sensitive to avoid false hits."""
    flags = 0 if len(term) <= 3 else re.I
    return re.search(r"(?<![\w])%s(?![\w])" % re.escape(term), text, flags) is not None


def nums(text):
    text = re.sub(r"(?<=\d)[,   ](?=\d{3}\b)", "", text)
    return set(NUM.findall(text))


def years(text):
    return set(YEAR.findall(text or ""))


def norm(s):
    """Comparable text: same dashes, quotes and spacing, no markdown emphasis, case-folded."""
    s = unicodedata.normalize("NFKC", str(s))
    s = re.sub(r"[‐‑‒–—―−]", "-", s)
    s = re.sub(r"[‘’‚′]", "'", re.sub(r"[“”„″]", '"', s))
    s = re.sub(r"[*_`#>]", "", s)
    return re.sub(r"\s+", " ", s).strip().casefold()


def valid_date(value):
    if not isinstance(value, str) or not DATE.fullmatch(value):
        return False
    try:
        datetime.date.fromisoformat(value)
        return True
    except ValueError:
        return False


OBJECT_LISTS = ("sources", "company_claims", "evidence", "job.requirements", "strategy.arguments", "strategy.adaptation",
                "strategy.contract_fit", "questions", "letter.paragraphs", "interview", "cv.sections")
WITH_ID = {"sources", "company_claims", "evidence"}


def misshapen(p):
    """Lists whose items must be objects: an agent's list of strings (or a null) would crash the checks. A missing
    key is allowed; a present one must be a list of objects."""
    lists = []
    for path in OBJECT_LISTS:
        x = p
        for k in path.split("."):
            x = x.get(k, KeyError) if isinstance(x, dict) else KeyError
        if x is not KeyError:
            lists.append((path, x))
    secs = p["cv"].get("sections") if isinstance(p.get("cv"), dict) else None
    for i, s in enumerate(secs if isinstance(secs, list) else []):
        if isinstance(s, dict) and "items" in s:
            lists.append(("cv.sections[%d].items" % i, s["items"]))
            for j, it in enumerate(s["items"] if isinstance(s["items"], list) else []):
                if isinstance(it, dict) and "bullets" in it:
                    lists.append(("cv.sections[%d].items[%d].bullets" % (i, j), it["bullets"]))
    for path, v in lists:
        if not isinstance(v, list) or not all(isinstance(x, dict) and (path not in WITH_ID or "id" in x) for x in v):
            yield path + (" must be a list of objects with an id" if path in WITH_ID else " must be a list of objects")


ID_LISTS = {"sources", "need", "evidence", "claims", "requirements", "basis", "match", "gap_terms", "hiring_triggers"}
TEXT_FIELDS = {"id", "title", "text", "heading", "subheading", "label", "location", "dates", "source", "kind",
               "stage", "type", "name", "headline", "salutation", "closing", "signature", "date", "subject", "language",
               "mode", "status", "lever", "choice", "problem", "risk", "scope", "item", "posting", "candidate",
               "ask", "why", "note", "level", "level_required", "level_match", "confidence", "placement", "field",
               "contract_override", "font", "paper", "unit", "research_level", "retrieved_via", "copy_path", "url",
               "company", "role", "start", "rhythm", "remote", "question", "talking_points",
               "accessed", "published", "value_proposition", "differentiation", "recipient_source", "posting_status"}
TEXT_LISTS = {"facts", "metrics", "excerpts", "tools", "contact", "recipient", "warnings", "gaps", "language_basis"}
NULLABLE_TEXT = {"dates", "location", "source", "level_required", "level_match", "unit", "recipient_source",
                 "contract_override", "note", "copy_path", "start", "rhythm", "remote"}


def structure_errors(p):
    """Validate types before checks use joins, regexes or hashable references. Keep paths in diagnostics."""
    if not isinstance(p, dict):
        yield "package must be an object"
        return
    for key in ("meta", "cv", "job", "strategy", "letter", "company_profile"):
        if key in p and not isinstance(p[key], dict):
            yield "%s must be an object" % key
    meta = p.get("meta")
    if isinstance(meta, dict) and "schema" in meta:
        if type(meta["schema"]) is not int or meta["schema"] not in (1, SCHEMA):
            yield "meta.schema must be a supported integer (1 or %d); omit it only for older packages" % SCHEMA
    cv = p.get("cv")
    if isinstance(cv, dict) and (not isinstance(cv.get("name"), str) or not cv["name"].strip()):
        yield "cv.name must be non-empty text"
    yield from build_docs.settings_errors(meta, cv)  # a bad margin or paper must stop the audit, not build_docs.py

    def visit(x, path=""):
        if isinstance(x, dict):
            for key, value in x.items():
                where = "%s.%s" % (path, key) if path else key
                if key in TEXT_FIELDS and not isinstance(value, str) and not (value is None and key in NULLABLE_TEXT):
                    yield "%s must be text" % where
                argument_need = re.fullmatch(r"strategy\.arguments\[\d+\]\.need", where)
                reference_list = key in ID_LISTS and where not in OBJECT_LISTS
                if key in TEXT_LISTS or reference_list:
                    if argument_need and isinstance(value, str):
                        pass
                    elif not isinstance(value, list) or not all(isinstance(v, str) for v in value):
                        yield "%s must be a list of strings%s" % (where, " or text" if argument_need else "")
                if where in ("job.contract", "strategy.hiring_context", "strategy.contribution"):
                    if not isinstance(value, dict):
                        yield "%s must be an object" % where
                if key in ("duration_months", "horizon_months") and value is not None:
                    if type(value) not in (int, float) or (type(value) is float and not math.isfinite(value)) or value <= 0:
                        yield "%s must be a positive number or null" % where
                yield from visit(value, where)
        elif isinstance(x, list):
            for i, value in enumerate(x):
                yield from visit(value, "%s[%d]" % (path, i))

    yield from visit(p)


def verdict_structure_errors(data):
    rows = data.get("verdicts") if isinstance(data, dict) else None
    if not isinstance(rows, list):
        return ["verdicts must be a list of objects"]
    errors = []
    for i, v in enumerate(rows):
        if not isinstance(v, dict) or not isinstance(v.get("target"), str):
            errors.append("verdicts[%d] must be an object with a text target" % i)
            continue
        for field in ("fingerprint", "verdict", "source", "excerpt", "note"):
            if field in v and not isinstance(v[field], str):
                errors.append("verdicts[%d].%s must be text" % (i, field))
    return errors


def text_id_lists(x, path=""):
    """Id-list fields given as text ("R5, C10"), which would be read character by character. An argument's
    `need` is text by contract."""
    if isinstance(x, dict):
        for k, v in x.items():
            p = "%s.%s" % (path, k) if path else k
            if k in ID_LISTS and isinstance(v, str) and not re.fullmatch(r"strategy\.arguments\[\d+\]\.need", p):
                yield p, v
            yield from text_id_lists(v, p)
    elif isinstance(x, list):
        for i, v in enumerate(x):
            yield from text_id_lists(v, "%s[%d]" % (path, i))


def need_ids(text):
    ids = set()
    if isinstance(text, list):  # questions give ids as a list; arguments as text
        text = " ".join(map(str, text))
    for kind, lo, hi in NEED_IDS.findall(text or ""):
        ids |= {"%s%d" % (kind, i) for i in range(int(lo), int(hi or lo) + 1)}
    return ids


DURATION = re.compile(HORIZON.pattern.replace(r"\s+", r"[\s-]+", 1), re.I)  # also "a 10-month internship"


def horizon_months(text, rx=HORIZON):
    """Durations stated in a text, in months ('the next two years' -> 24)."""
    out = []
    for n, unit in rx.findall(text or ""):
        n = int(n) if n.isdigit() else NUMBER_WORDS[n.lower()]
        u = unit.lower()
        out.append(n / 4.3 if u.startswith(("week", "semaine")) else n * 12 if u.startswith(("year", "an", "ann"))
                   else n)
    return out


def read_text(path):
    """(text, complete) of an existing local document (.md/.txt, .docx, .pdf). text is None if nothing can be read;
    complete is False when the PDF reader had to skip text it cannot decode (a missing quote is then unverifiable,
    not disproved). Reuses check_docs.py's extractors, including macOS PDFKit when available."""
    try:
        low = path.lower()
        if low.endswith((".docx", ".pdf")):
            import check_docs  # same folder
            if low.endswith(".docx"):
                return check_docs.docx_text(path), True
            info = check_docs.pdf_info(path)
            text, complete = info["text"], not info.get("skipped_text")
            if not complete or not LETTER.search(text or ""):
                other = check_docs.independent_text(path)
                if other and LETTER.search(other[1]):
                    return other[1], True
            return text, complete
        with open(path, encoding="utf-8") as f:
            return f.read(), True
    except Exception:  # bad zip, undecodable bytes: unreadable, reported as unchecked, never as verified
        return None, False


class Audit:
    def __init__(self, pkg, root=None):
        self.initial_structure = list(structure_errors(pkg))
        self.p = dict(pkg) if isinstance(pkg, dict) else {}
        self.p.setdefault("meta", {})
        for k in ("sources", "company_claims", "evidence"):
            self.p.setdefault(k, [])
        self.given = set(pkg) if isinstance(pkg, dict) else set()
        self.root = root or os.getcwd()
        self.errors, self.warnings = [], []
        meta = self.p["meta"] if isinstance(self.p["meta"], dict) else {}
        schema = meta.get("schema", 1)
        self.strict = type(schema) is int and schema >= SCHEMA
        self.mode = meta.get("mode", "package")
        self.targeted = self.mode != "create"
        self._states = {}
        self.unchecked = []  # statements or cards that could not be checked: never reported as verified

    def err(self, code, msg):
        self.errors.append({"code": code, "msg": msg})

    def warn(self, code, msg):
        self.warnings.append({"code": code, "msg": msg})

    def req(self, code, msg):
        """Contract rule: error for new outputs (schema >= 2), warning for older packages."""
        if self.strict:
            self.err(code, msg)
        else:
            self.warn(code.replace("E_", "W_", 1), msg + " (older package: warning only)")

    def run(self):
        p = self.p
        for msg in self.initial_structure:
            self.err("E_STRUCTURE", msg)
        if self.errors:
            return self
        if self.mode not in MODES:
            self.err("E_MODE", "meta.mode %r not in %s" % (self.mode, sorted(MODES)))
            return self
        if self.strict and "mode" not in p["meta"]:
            self.err("E_MODE", "schema %d packages state meta.mode" % SCHEMA)
        if self.strict:
            need = {"meta", "evidence", "cv"}
            if self.targeted:
                need |= {"sources", "company_claims", "job", "strategy"}
            if self.mode in LETTER_MODES:
                need.add("letter")
        else:  # rules of the original contract
            need = {"meta", "sources", "company_claims", "evidence", "cv"}
        for key in sorted(need - self.given):
            self.err("E_STRUCTURE", "missing top-level key '%s' (mode %s)" % (key, self.mode))
        for msg in misshapen(p):
            self.err("E_STRUCTURE", msg)
        if self.errors:
            return self
        self.src = {s["id"]: s for s in p["sources"]}
        self.claims = {c["id"]: c for c in p["company_claims"]}
        self.ev = {e["id"]: e for e in p["evidence"]}
        self.reqs = {r.get("id"): r for r in (p.get("job") or {}).get("requirements", [])}
        self.fit = {k.get("id"): k for k in (p.get("strategy") or {}).get("contract_fit") or []}
        for coll, name in ((p["sources"], "source"), (p["company_claims"], "claim"), (p["evidence"], "evidence")):
            ids = [x.get("id") for x in coll]
            if len(ids) != len(set(ids)):
                self.err("E_STRUCTURE", "duplicate %s ids" % name)
        for e in p["evidence"]:
            for k in ("facts", "metrics", "excerpts", "tools"):
                v = e.get(k) or []  # a string would pass as a list of one-character strings
                if not isinstance(v, list) or not all(isinstance(x, str) for x in v):
                    self.err("E_STRUCTURE", "evidence %s: %s must be a list of strings" % (e.get("id"), k))
            lv = e.get("levels") or []
            if not isinstance(lv, list) or not all(isinstance(x, dict) and x.get("subject") and x.get("level")
                                                   for x in lv):
                self.err("E_STRUCTURE", 'evidence %s: levels must be a list of {"subject", "level"}' % e.get("id"))
        for where, v in text_id_lists(p):
            self.err("E_STRUCTURE", "%s must be a list of ids, not text: %r" % (where, v))
        for s in p["sources"]:
            if s.get("kind") not in SOURCE_KINDS:
                self.err("E_STRUCTURE", "source %s: kind %r not in %s" % (s.get("id"), s.get("kind"),
                                                                         sorted(SOURCE_KINDS)))
        if self.errors:
            return self
        self.check_sources_and_claims()
        self.check_profile()
        self.check_evidence()
        self.check_cv()
        self.check_letter()
        self.check_levels()
        self.check_estimates()
        self.check_text_hygiene()
        self.check_interview()
        self.check_language()
        if self.targeted:
            self.check_job()
            self.check_strategy()
            self.check_contract()
            self.check_questions()
        return self

    # -- local copies of sources
    def source_state(self, sid):
        """(state, text, where) of a source. 'ok': fully read; 'partial': read, but the PDF reader skipped some text;
        'unreadable': the file exists, no text could be extracted; 'missing': a declared local file does not exist;
        'remote': a live page without local copy; 'unknown': no such source. A copy_path (snapshot, or a .docx/.md
        export of an unreadable PDF CV) is read instead of the url."""
        if sid in self._states:
            return self._states[sid]
        s, path, state = self.src.get(sid), None, ("unknown", None, sid)
        if s:
            url = str(s.get("url", ""))
            path = s.get("copy_path") or (url if url and not re.match(r"https?://", url, re.I) else None)
            if not path:
                state = ("remote", None, url)
        elif sid and re.match(r"https?://", sid, re.I):
            state = ("remote", None, sid)
        elif sid and not re.match(r"^S\d+$", sid):
            path = sid  # an evidence card may cite a file path directly
        if path:
            full = path if os.path.isabs(path) else os.path.join(self.root, path)
            if not os.path.isfile(full):
                state = ("missing", None, path)
            else:
                text, complete = read_text(full)
                if not text or not LETTER.search(text):
                    state = ("unreadable", None, path)
                else:
                    state = ("ok" if complete else "partial", text, path)
        self._states[sid] = state
        return state

    def source_text(self, sid):
        """Text of a readable local source, else None."""
        return self.source_state(sid)[1]

    def source_digest(self, sid):
        """State and hash of the text actually read for a source (its copy_path when present): editing the
        document changes every fingerprint that cites it."""
        state, text, where = self.source_state(sid)
        digest = hashlib.sha256(text.encode("utf-8")).hexdigest()[:16] if text else "-"
        raw = "-"
        # Complete plaintext already has a portable full-text hash; binary/partial sources also need their bytes.
        if state in ("partial", "unreadable") or (state == "ok" and where.lower().endswith((".pdf", ".docx"))):
            path = where if os.path.isabs(where) else os.path.join(self.root, where)
            try:
                h = hashlib.sha256()
                with open(path, "rb") as f:
                    for block in iter(lambda: f.read(65536), b""):
                        h.update(block)
                raw = h.hexdigest()[:16]
            except OSError:
                raw = "missing"
        return "%s:%s:%s" % (state, digest, raw)

    def verification(self):
        return {"complete": not self.unchecked, "unchecked": self.unchecked}

    # -- company side
    def check_sources_and_claims(self):
        for s in self.p["sources"]:
            if s.get("kind") in ("candidate",):
                continue
            if not valid_date(s.get("accessed")):
                self.err("E_SOURCE_DATE", "source %s: accessed must be a real date YYYY-MM-DD" % s.get("id"))
            if "published" not in s:
                self.warn("W_SOURCE_DATE", "source %s lacks published date (use 'unknown')" % s.get("id"))
            elif s["published"] != "unknown" and not valid_date(s["published"]):
                self.err("E_SOURCE_DATE", "source %s: published must be a real date YYYY-MM-DD or 'unknown'" % s.get("id"))
            elif valid_date(s["published"]) and valid_date(s.get("accessed")) and s["published"] > s["accessed"]:
                self.err("E_SOURCE_DATE", "source %s: published is after accessed" % s.get("id"))
            if "reachable" in s and type(s["reachable"]) is not bool:
                self.err("E_STRUCTURE", "source %s: reachable must be a boolean" % s.get("id"))
        seen = {}
        for s in self.p["sources"]:
            if str(s.get("url", "")).lower().startswith("http") and "reachable" in s:
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
                elif not re.match(r"https?://", str(s.get("url", "")), re.I) or not s.get("title"):
                    self.err("E_CLAIM_UNSOURCED", "claim %s: source %s lacks URL or title" % (c["id"], r))
                elif s.get("reachable") is not True:
                    self.err("E_CLAIM_UNREACHABLE", "claim %s: source %s is not recorded reachable: true" % (c["id"], r))
                elif s.get("kind") == "candidate":
                    self.err("E_CLAIM_UNSOURCED", "claim %s relies on a candidate document" % c["id"])
                elif not valid_date(s.get("accessed")):
                    self.err("E_CLAIM_UNSOURCED", "claim %s: source %s lacks accessed date" % (c["id"], r))
        self.confirmed = confirmed
        level = self.p["meta"].get("research_level", "standard")
        if self.targeted and confirmed < 3 and level != "limited":
            self.err("E_RESEARCH_LEVEL", "only %d confirmed company facts: set meta.research_level='limited' "
                                         "and personalise cautiously" % confirmed)

    def check_profile(self):
        prof = self.p.get("company_profile")
        self.profile_basis = set()
        if prof is None:
            if self.targeted and (self.p.get("job") or {}).get("requirements"):
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
            signal = STATUTORY_SIGNAL.get(t, SIZE_SIGNAL)
            if not [c for c in basis if self.claims.get(c, {}).get("status") == "confirmed"
                    and signal.search(self.claims[c].get("text", ""))]:
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
        """Evidence must be anchored in the candidate's own documents: verbatim excerpts, and every number or year
        of the card inside them. Without excerpts (older packages) the whole document is the (weaker) anchor."""
        for e in self.p["evidence"]:
            eid = e.get("id")
            if not e.get("source"):
                self.err("E_EVIDENCE_UNSOURCED", "evidence %s has no source" % eid)
                continue
            if e.get("stage") not in STAGES:
                self.warn("W_STAGE", "evidence %s stage %r not in %s" % (eid, e.get("stage"), sorted(STAGES)))
            sid = str(e["source"]).split("#")[0]
            if re.match(r"^S\d+$", sid) and sid not in self.src:
                self.err("E_BAD_REF", "evidence %s cites unknown source %s" % (eid, sid))
                continue
            state, text, where = self.source_state(sid)
            given_excerpts = e.get("excerpts") or []
            if any(not norm(x) for x in given_excerpts):
                self.err("E_EVIDENCE_EXCERPT_NOT_FOUND", "evidence %s: excerpts must contain meaningful source text" % eid)
            excerpts = [x for x in given_excerpts if norm(x)]
            if state == "missing":
                self.err("E_SOURCE_MISSING", "evidence %s: local source %s does not exist" % (eid, where))
                continue
            unchecked = {"remote": "%s is not a local file" % where,
                         "unreadable": "no text could be extracted from %s: record a .docx/.md export as copy_path"
                                        % where,
                          "partial": "%s is only partly readable: record a .docx/.md export as copy_path" % where}.get(state)
            if excerpts:
                missing = [x for x in excerpts if norm(x) not in norm(text)] if text else []
                if state == "partial" and missing:  # the reader skipped text: not found is not disproved
                    unchecked = "%s is only partly readable; %d excerpt(s) not found" % (where, len(missing))
                elif missing:
                    self.err("E_EVIDENCE_EXCERPT_NOT_FOUND", "evidence %s: excerpt not found verbatim in %s: %r"
                             % (eid, sid, missing[0][:80]))
                anchor = " ".join(excerpts)  # the card's numbers must be in its own quotes, readable or not
            else:
                self.req("E_EVIDENCE_NO_EXCERPT", "evidence %s has no verbatim excerpts from %s" % (eid, sid))
                anchor = text if state == "ok" else None
                if anchor is None and not unchecked:
                    unchecked = "%s is only partly readable" % where
            if unchecked:
                self.warn("W_EVIDENCE_UNCHECKED", "evidence %s NOT verified against its source: %s" % (eid, unchecked))
                self.unchecked.append("evidence %s: %s" % (eid, unchecked))
            if anchor is None:
                continue
            stated = " ".join(list(e.get("facts", [])) + list(e.get("metrics", [])) + [e.get("title", "")])
            extra = (nums(stated) - nums(anchor)) | (years(e.get("dates", "")) - years(anchor))
            if extra:
                self.err("E_EVIDENCE_NUMBER_UNSOURCED", "evidence %s: %s absent from %s in %s" % (
                    eid, sorted(extra), "its excerpts" if excerpts else "the source document", sid))
            for lv in e.get("levels") or []:
                if not lv.get("level") or norm(lv["level"]) not in norm(anchor):
                    self.err("E_LEVEL_UNANCHORED", "evidence %s: level %r for %s not found in %s"
                             % (eid, lv.get("level"), lv.get("subject"), "its excerpts" if excerpts else sid))

    def corpus(self, ev_ids=(), claim_ids=(), req_ids=()):
        parts = []
        for i in ev_ids:
            e = self.ev.get(i, {})
            parts += [e.get("title", ""), e.get("dates", "") or ""] + list(e.get("facts", [])) + list(e.get("metrics", []))
            parts += list(e.get("tools", []))
        for i in claim_ids:
            parts.append(self.claims.get(i, {}).get("text", ""))
        for i in req_ids:
            parts.append(self.reqs.get(i, {}).get("text", ""))
        return " ".join(parts)

    def check_numbers(self, where, text, ev_ids, claim_ids=(), req_ids=(), extra_corpus=""):
        extra = nums(text) - nums(self.corpus(ev_ids, claim_ids, req_ids) + " " + extra_corpus)
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
                    label = it.get("label")
                    text = (label + ": " if label else "") + it.get("text", "")
                    yield "cv.%s[%d]" % (sec.get("title"), ii), text, it.get("evidence")

    @staticmethod
    def section_refs(sec):
        """Evidence cited anywhere in a CV section: what its printed title may rest on."""
        refs = []
        for it in sec.get("items", []):
            for r in list(it.get("evidence") or []) + [r for b in it.get("bullets", []) for r in b.get("evidence") or []]:
                if r not in refs:
                    refs.append(r)
        return refs

    def cv_items(self):
        """Heading items (organisation, title, degree, dates) with the evidence cited by the item or its bullets."""
        for sec in self.p["cv"].get("sections", []):
            for ii, it in enumerate(sec.get("items", [])):
                if it.get("heading"):
                    refs = list(it.get("evidence") or [])
                    refs += [r for b in it.get("bullets", []) for r in (b.get("evidence") or []) if r not in refs]
                    text = " | ".join(x for x in (it.get("heading"), it.get("subheading"), it.get("location"),
                                                  it.get("dates")) if x)
                    yield "cv.%s[%d]" % (sec.get("title"), ii), it, text, refs

    def check_cv(self):
        cv = self.p["cv"]
        if self.p["meta"].get("date") is not None and not valid_date(self.p["meta"]["date"]):
            self.err("E_SOURCE_DATE", "meta.date must be a real date YYYY-MM-DD")
        if self.mode == "cover-letter":
            return  # the CV block only carries name and contact details
        all_ev = list(self.ev)
        if cv.get("headline"):
            self.check_numbers("cv.headline", cv["headline"], all_ev)

        def prints(it, title):  # as build_docs.py renders it: a label repeating the section title is dropped
            label = str(it.get("label") or "")
            if label.strip() and build_docs.slug(label).lower() == build_docs.slug(str(title or "")).lower():
                label = ""
            return any(str(x or "").strip() for x in (it.get("heading"), it.get("text"), label))

        for si, sec in enumerate(cv.get("sections", [])):  # every section title is printed
            where = "cv.sections[%d]" % si
            if not any(prints(it, sec.get("title")) for it in sec.get("items", [])):
                self.err("E_CV_EMPTY_SECTION", "%s (%r) prints a title without content: remove it or add items that "
                                               "cite evidence" % (where, sec.get("title")))
            self.check_numbers(where + ".title", sec.get("title", ""), self.section_refs(sec))
        for where, text, refs in self.cv_lines():
            if not refs:
                self.err("E_CV_UNSUPPORTED", "%s has no evidence reference" % where)
                continue
            bad = [r for r in refs if r not in self.ev]
            if bad:
                self.err("E_BAD_REF", "%s cites unknown evidence %s" % (where, bad))
            self.check_numbers(where, text, refs)
        for where, it, _, refs in self.cv_items():
            if not refs:
                self.err("E_CV_UNSUPPORTED", "%s (%s): heading, title or dates cite no evidence" % (where, it["heading"]))
                continue
            bad = [r for r in refs if r not in self.ev]
            if bad:
                self.err("E_BAD_REF", "%s cites unknown evidence %s" % (where, bad))
            corpus = self.corpus(refs)
            head = " ".join(x for x in (it.get("heading"), it.get("subheading"), it.get("location")) if x)
            extra = (nums(head) - nums(corpus)) | (years(it.get("dates", "")) - years(corpus))
            if extra:
                self.err("E_CV_ITEM_UNSUPPORTED", "%s: %s in heading or dates absent from cited evidence %s"
                         % (where, sorted(extra), refs))

    def cv_text(self):
        cv = self.p["cv"]
        parts = [cv.get("headline", "")]
        for sec in cv.get("sections", []):
            parts.append(sec.get("title", ""))
            for it in sec.get("items", []):
                parts += [it.get("heading", ""), it.get("subheading", ""), it.get("text", ""), it.get("label", "")]
                parts += [b.get("text", "") for b in it.get("bullets", [])]
        return "\n".join(parts)

    @staticmethod
    def interview_text(q):
        """The question and its talking points: a question can presuppose a fact ("your doctorate")."""
        return "\n".join(x for x in (q.get("question", ""), q.get("talking_points", "")) if x)

    def identity_text(self):
        cv = self.p.get("cv") or {}
        return "\n".join([cv.get("name", "")] + list(cv.get("contact") or []))

    def letter_header_text(self):
        L = self.p.get("letter") or {}
        return "\n".join([L.get("date") or ""] + list(L.get("recipient") or []) +
                         [L.get(k) or "" for k in ("subject", "salutation", "closing", "signature")])

    def gap_terms(self):
        """Missing skills of every requirement, matched or not: a partial match never licenses its gap terms."""
        terms = []
        for r in (self.p.get("job") or {}).get("requirements", []):
            terms += r.get("gap_terms") or []
            for m in r.get("match") or []:
                if m not in self.ev:
                    self.err("E_BAD_REF", "requirement %s matches unknown evidence %s" % (r.get("id"), m))
        return terms

    def named_recipient(self, L):
        """True when the salutation or first recipient line addresses a person rather than a team or role."""
        head = [L.get("salutation", ""), (L.get("recipient") or [""])[0]]
        if any(CIVILITY.search(h or "") for h in head):
            return True
        unit = (self.p.get("company_profile") or {}).get("unit") or ""
        allowed = GENERIC_WORDS | {w.lower() for w in re.findall(r"[\w'’-]+", self.p["meta"].get("company", "") + " " + unit)}
        return any(w.lower() not in allowed for h in head for w in re.findall(r"[\w'’-]+", h or ""))

    def contract_corpus(self):
        """Contract values a letter may cite (duration, start, location); never the source id ('S4' is not a 4)."""
        c = (self.p.get("job") or {}).get("contract") or {}
        return " ".join(str(v) for k, v in c.items() if v is not None and k != "source")

    def check_letter(self):
        L = self.p.get("letter")
        gaps = self.gap_terms()
        cvt = self.cv_text()
        for t in gaps:
            if term_in(t, cvt):
                self.err("E_GAP_IN_CV", "missing skill '%s' appears in the CV" % t)
        if not L:
            return
        if self.named_recipient(L) and L.get("recipient_source") not in self.src:
            self.err("E_RECIPIENT_UNSOURCED", "named recipient without recipient_source: %r" % L.get("salutation"))
        cited_confirmed, has_ev, words, contribution = 0, False, 0, []
        paras = L.get("paragraphs", [])
        for i, para in enumerate(paras):
            text = para.get("text", "")
            words += len(re.findall(r"\b[\w'’-]+\b", text))
            ev, cl, rq = para.get("evidence", []) or [], para.get("claims", []) or [], para.get("requirements", []) or []
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
            for r in rq:
                if r not in self.reqs:
                    self.err("E_BAD_REF", "letter paragraph %d cites unknown requirement %s" % (i, r))
            self.check_numbers("letter.paragraphs[%d]" % i, text, ev or list(self.ev), cl, rq, self.contract_corpus())
            for t in gaps:
                if term_in(t, text) and not para.get("addresses_gap"):
                    self.err("E_GAP_IN_LETTER", "paragraph %d mentions missing skill '%s' without addresses_gap" % (i, t))
            if para.get("contribution"):
                contribution.append((i, text))
        if paras and not (paras[0].get("claims") or paras[0].get("requirements")):
            self.req("E_OPENING_GENERIC", "the opening paragraph cites no company claim or posting requirement: "
                                          "why this company must rest on a sourced fact")
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
        body = " ".join(x.get("text", "") for x in paras)
        if company and company.lower() not in body.lower():
            self.warn("W_COMPANY_ABSENT", "company name not in letter body")
        self.letter_words = words
        if self.p["meta"].get("language") == "fr" and not re.match(r"\s*Objet\s*:", L.get("subject") or ""):
            self.err("E_FR_SUBJECT", "French letters need a subject line starting with \"Objet :\" (got %r)"
                     % L.get("subject"))
        if self.targeted:
            if not contribution:
                self.req("E_CONTRIBUTION_MISSING", "no letter paragraph flagged contribution: true (the plausible "
                                                   "contribution, sized to the employment contract)")
            months = ((self.p.get("job") or {}).get("contract") or {}).get("duration_months")
            for i, text in contribution:
                over = [m for m in horizon_months(text) if isinstance(months, (int, float)) and m > months]
                if over:
                    self.err("E_CONTRIBUTION_HORIZON", "letter paragraph %d promises a horizon of %.0f months for a "
                                                       "%s-month contract" % (i, max(over), months))

    def doc_lines(self):
        """(where, text, evidence refs) for every CV line (section titles included) and letter paragraph."""
        cv = self.p.get("cv") or {}
        if cv.get("headline"):
            yield "cv.headline", cv["headline"], []
        for si, sec in enumerate(cv.get("sections", [])):
            yield "cv.sections[%d].title" % si, sec.get("title", ""), self.section_refs(sec)
        for line in self.cv_lines():
            yield line
        if self.p.get("letter"):
            yield "letter.header", self.letter_header_text(), list(self.ev)
        for i, para in enumerate((self.p.get("letter") or {}).get("paragraphs", [])):
            yield "letter.paragraphs[%d]" % i, para.get("text", ""), para.get("evidence") or []

    def check_levels(self):
        """A stated level (language, CEFR, skill adjective) must cite evidence whose own levels are anchored in the
        candidate's documents. Whether 'bilingue' fits a source saying 'fluent' is a meaning question: these lines
        become level targets for application-auditor, never decided by a word list."""
        self.level_lines = set()
        for where, text, refs in self.doc_lines():
            lang = next((m for m in LANGUAGE_LEVEL.finditer(text)  # "courant" only next to a language name
                         if LANGUAGE_NAME.search(text[max(0, m.start() - 40):m.end() + 40])), None)
            skill, cefr = SKILL_LEVEL.search(text), CEFR.findall(text)
            if not (lang or skill or cefr):
                continue
            self.level_lines.add(where)
            leveled = [lv for r in refs or list(self.ev) for lv in self.ev.get(r, {}).get("levels") or []]
            if (lang or cefr) and not leveled:
                self.req("E_LEVEL_UNSUPPORTED", "%s states a level (%r) but cites no evidence with recorded levels"
                         % (where, (lang.group(0) if lang else cefr[0])))
            elif skill and not leveled:
                self.warn("W_LEVEL_UNANCHORED", "%s uses a level word (%r) without leveled evidence: application-"
                                                "auditor must confirm it" % (where, skill.group(0)))
            if cefr:
                anchored = [c for lv in leveled for c in CEFR.findall(lv.get("level", ""))]
                if not anchored or max(cefr) > max(anchored):
                    self.err("E_LEVEL_UNSUPPORTED", "%s states CEFR %s; evidence records %s"
                             % (where, max(cefr), max(anchored) if anchored else "no CEFR level"))

    def check_estimates(self):
        """A figure that comes from an estimate or a survey stays attributed where it is used ('my supervisor
        estimated…', '(estimated by …)'); stated bare, it would read as a measurement."""
        soft = {}
        for e in self.p["evidence"]:
            n = set()
            for m in e.get("metrics", []):
                if ATTRIBUTED.search(m):
                    n |= nums(m)
            # '4 coordinators' is a fact, not part of the estimate: trust the verbatim, unattributed source sentences,
            # not the agent's paraphrased facts (older packages without excerpts keep the facts)
            plain = [s for x in e.get("excerpts") or [] for s in re.split(r"(?<=[.!?;])\s+", x)
                     if not ATTRIBUTED.search(s)] if e.get("excerpts") else e.get("facts", [])
            n -= nums(" ".join(plain))
            if n:
                soft[e["id"]] = n
        if not soft:
            return
        lines = list(self.doc_lines()) + [("interview[%d]" % i, self.interview_text(q), q.get("evidence") or [])
                                          for i, q in enumerate(self.p.get("interview") or [])]
        months = ((self.p.get("job") or {}).get("contract") or {}).get("duration_months")

        def contract_duration(m):  # "stage de 10 mois" is the contract, not the 10 of a survey
            v = horizon_months(m.group(0), DURATION)
            return " " if isinstance(months, (int, float)) and v and abs(v[0] - months) < 0.5 else m.group(0)

        for where, text, refs in lines:
            figures = set().union(*[soft.get(r, set()) for r in (refs or list(self.ev))])
            for sentence in re.split(r"(?<=[.!?;])\s+", DATE_TEXT.sub(" ", text)):
                hit = nums(DURATION.sub(contract_duration, sentence)) & figures
                if hit and not ATTRIBUTED.search(sentence):
                    self.err("E_ESTIMATE_AS_MEASURE", "%s states %s from an estimate or survey as a measurement: say who "
                                                      "estimated or reported it" % (where, sorted(hit)))

    def check_job(self):
        job = self.p.get("job") or {}
        st = job.get("posting_status", "unverified")
        if st not in POSTING_STATUSES:
            self.err("E_POSTING_STATUS", "job.posting_status %r not in %s" % (st, sorted(POSTING_STATUSES)))
            return
        if st in ("closed", "expired", "unverified") and not self.p["meta"].get("warnings"):
            self.err("E_POSTING_STATUS", "posting status '%s' must be surfaced in meta.warnings" % st)
        if st == "open":
            js = self.src.get(job.get("source"))
            if not js or js.get("reachable") is not True:
                self.err("E_POSTING_STATUS", "posting marked open but its source %s is not reachable: use 'unverified' "
                                             "and warn" % job.get("source"))

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
            self.err("E_DISCLAIMER", "say who estimated or reported a figure (\"they said in a survey\", \"(estimated by "
                                     "my supervisor)\"), not a self-deprecating disclaimer: %r" % m.group(0))
        m = LETTER_CITATION.search("\n".join(p.get("text", "") for p in L.get("paragraphs", [])))
        if m:
            self.err("E_CITATION_IN_LETTER", "sources belong in dossier.md, not in the letter: %r" % m.group(0))
        m = SIZE_CLICHE.search(text)
        if m:
            self.err("E_SIZE_CLICHE", "company-size cliché: state the sourced fact instead: %r" % m.group(0))
        m = FLATTERY.search(text)
        if m:
            self.warn("W_FLATTERY", "generic flattery: %r" % m.group(0))

    def check_interview(self):
        items = self.p.get("interview") or []
        if self.mode == "package" and not items:
            self.req("E_INTERVIEW_MISSING", "package mode needs interview talking points")
        for i, q in enumerate(items):
            refs = q.get("evidence") or []
            bad = [r for r in refs if r not in self.ev] + [c for c in q.get("claims") or [] if c not in self.claims]
            bad += [r for r in q.get("requirements") or [] if r not in self.reqs]
            if bad:
                self.err("E_BAD_REF", "interview[%d] cites unknown ids %s" % (i, bad))
            self.check_numbers("interview[%d]" % i, self.interview_text(q),
                               refs or list(self.ev), list(self.claims), q.get("requirements") or [])

    def basis_ok(self, where, basis, allow=()):
        """Basis ids must exist (claims, requirements, or the extra kinds allowed) and never be unavailable claims."""
        known = set(self.claims) | set(self.reqs) | set(allow)
        bad = [b for b in basis if b not in known]
        dead = [b for b in basis if self.claims.get(b, {}).get("status") == "unavailable"]
        if not basis or bad or dead:
            self.err("E_ADAPTATION_UNSUPPORTED", "%s: basis %s must cite existing claims or requirements, none "
                                                 "unavailable" % (where, basis))
            return False
        if set(basis) <= self.profile_basis:
            self.err("E_SIZE_ONLY", "%s rests only on company size/stage %s: cite the verified need it serves"
                     % (where, basis))
            return False
        sourced_reqs = set(self.reqs) if (self.p.get("job") or {}).get("source") in self.src else set()
        if not [b for b in basis if self.claims.get(b, {}).get("status") == "confirmed" or b in sourced_reqs]:
            self.err("E_ADAPTATION_UNVERIFIED", "%s rests only on hypotheses or contract rows %s: cite at least one "
                                                "confirmed claim or posting requirement" % (where, basis))
            return False
        return True

    def check_strategy(self):
        st = self.p.get("strategy") or {}
        args = st.get("arguments", [])
        if not args:
            if self.strict:
                self.err("E_STRATEGY_MISSING", "strategy.arguments is empty: the recruitment-strategist note must "
                                               "precede writing")
            else:
                self.warn("W_STRATEGY", "no strategy.arguments: analysis must precede writing")
        elif len(args) > 3:
            self.warn("W_STRATEGY", "more than 3 core arguments")
        vp = st.get("value_proposition", "")
        if self.strict and not vp:
            self.err("E_STRATEGY_MISSING", "strategy.value_proposition is empty")
        self.check_numbers("strategy.value_proposition", vp, list(self.ev), list(self.claims))
        notes = [("strategy.gaps[%d]" % i, g) for i, g in enumerate(st.get("gaps") or [])]
        for where, text in notes + [("strategy.differentiation", st.get("differentiation") or "")]:
            self.check_numbers(where, text, list(self.ev), list(self.claims), list(self.reqs))
        known = set(self.claims) | set(self.reqs) | set(self.fit)
        for i, a in enumerate(args):
            for r in a.get("evidence", []):
                if r not in self.ev:
                    self.err("E_BAD_REF", "strategy argument cites unknown evidence %s" % r)
            ids = need_ids(a.get("need", ""))
            bad = sorted(ids - known)
            if bad:
                self.err("E_BAD_REF", "strategy argument %d need cites unknown ids %s" % (i, bad))
            conf, place = a.get("confidence"), a.get("placement")
            if conf not in CONFIDENCE or place not in PLACEMENT:
                self.req("E_STRATEGY_ENUM", "argument %d: confidence %r / placement %r not in %s / %s"
                         % (i, conf, place, sorted(CONFIDENCE), sorted(PLACEMENT)))
            if conf == "low" and place in ("cv", "both"):
                self.err("E_ARGUMENT_PLACEMENT", "argument %d has low confidence (a gap) but is placed in the CV" % i)
            stages = {self.ev[e].get("stage") for e in a.get("evidence", []) if e in self.ev}
            if conf == "high" and stages and stages <= {"self-reported"}:
                self.warn("W_SELF_REPORTED_HIGH", "argument %d: high confidence rests only on self-reported evidence %s"
                          % (i, a.get("evidence")))
            below = [r for r in sorted(ids) if self.reqs.get(r, {}).get("level_match") == "below"]
            if conf == "high" and below:
                self.err("E_CONFIDENCE_INFLATED", "argument %d: high confidence on %s whose required level is not met"
                         % (i, below))
        for r in (self.p.get("job") or {}).get("requirements", []):
            if r.get("level") == "required" and not r.get("match") and not r.get("gap_terms"):
                self.req("E_REQUIREMENT_UNASSESSED", "required %s (%s) has neither match nor gap_terms"
                         % (r.get("id"), r.get("text")))
            if r.get("level_required") and r.get("match") and r.get("level_match") not in LEVEL_MATCH:
                self.req("E_LEVEL_UNASSESSED", "%s asks for level %r: set level_match to %s from the cited evidence"
                         % (r.get("id"), r.get("level_required"), sorted(LEVEL_MATCH)))
        adapt = st.get("adaptation") or []
        levers = [a.get("lever") for a in adapt]
        if self.reqs and (set(levers) != LEVERS or len(levers) != len(set(levers))):
            self.err("E_ADAPTATION_MISSING", "strategy.adaptation needs each lever exactly once: %s" % sorted(LEVERS))
        for i, a in enumerate(adapt):
            if a.get("lever") not in LEVERS:
                self.warn("W_LEVER", "adaptation %d (%s): lever not in %s" % (i, a.get("lever"), sorted(LEVERS)))
            self.basis_ok("adaptation %d (%s)" % (i, a.get("lever")), list(a.get("basis") or []))
        hc = st.get("hiring_context")
        if not hc:
            if self.reqs:
                self.req("E_HIRING_CONTEXT_MISSING", "strategy.hiring_context (problem, risk, basis) is missing: why "
                                                     "the team hires and what risk the hire must reduce")
        else:
            if not hc.get("problem") or not hc.get("risk"):
                self.req("E_HIRING_CONTEXT_MISSING", "strategy.hiring_context needs both problem and risk")
            self.basis_ok("hiring_context", list(hc.get("basis") or []))
        contrib = st.get("contribution")
        if contrib:
            self.basis_ok("contribution", list(contrib.get("basis") or []), allow=self.fit)
            months = ((self.p.get("job") or {}).get("contract") or {}).get("duration_months")
            h = contrib.get("horizon_months")
            if isinstance(h, (int, float)) and isinstance(months, (int, float)) and h > months:
                self.err("E_CONTRIBUTION_HORIZON", "strategy.contribution horizon %s months exceeds the %s-month "
                                                   "contract" % (h, months))
        elif self.mode in LETTER_MODES:
            self.req("E_CONTRIBUTION_MISSING", "strategy.contribution (scope, horizon_months, basis) is missing")

    def check_contract(self):
        job = self.p.get("job") or {}
        c = job.get("contract")
        if not c:
            self.req("E_CONTRACT_MISSING", "job.contract (type, duration, rhythm, start, location) is missing: "
                                           "check the employment contract before writing")
        elif c.get("type") not in CONTRACT_TYPES:
            self.req("E_CONTRACT_MISSING", "job.contract.type %r not in %s" % (c.get("type"), sorted(CONTRACT_TYPES)))
        fit = (self.p.get("strategy") or {}).get("contract_fit")
        if fit is None:
            self.req("E_CONTRACT_FIT_MISSING", "strategy.contract_fit is missing: compare the posting's contract with "
                                               "the candidate's stated availability before writing")
            return
        c = c or {}
        need = {"type", "start", "location"} | ({"duration"} if c.get("duration_months") is not None else set()) | (
            {"rhythm"} if c.get("rhythm") else set())
        missing = sorted(need - {k.get("field") for k in fit})
        if missing:
            self.req("E_CONTRACT_FIT_INCOMPLETE", "strategy.contract_fit lacks the comparison(s) %s: one row per field, "
                                                  "status 'unknown' when a side is not stated" % missing)
        known = set(self.src) | set(self.claims) | set(self.reqs) | set(self.ev)
        for k in fit:
            where = "contract_fit %s (%s)" % (k.get("id"), k.get("item"))
            if k.get("field") not in FIT_FIELDS:
                self.req("E_CONTRACT_FIT", "%s: field %r not in %s" % (where, k.get("field"), sorted(FIT_FIELDS)))
            key = FIT_FIELDS.get(k.get("field"))
            if key and c.get(key) in (None, "", "unknown") and k.get("status") in ("compatible", "incompatible"):
                self.err("E_CONTRACT_FIT_UNSUPPORTED", "%s is %s but the posting does not state its %s: the status "
                                                       "must be 'unknown'" % (where, k.get("status"), k.get("field")))
            if k.get("status") not in FIT_STATUSES:
                self.req("E_CONTRACT_FIT", "%s: status %r not in %s" % (where, k.get("status"), sorted(FIT_STATUSES)))
            basis = list(k.get("basis") or [])
            bad = [b for b in basis if b not in known]
            if not basis or bad:
                self.err("E_BAD_REF", "%s: basis %s must cite existing sources, claims, requirements or evidence"
                         % (where, basis))
            if k.get("status") == "compatible" and not [b for b in basis if b in self.ev]:
                self.err("E_CONTRACT_FIT_UNSUPPORTED", "%s marked compatible without candidate-side evidence" % where)
            if k.get("status") == "incompatible" and not self.p["meta"].get("contract_override"):
                self.err("E_CONTRACT_INCOMPATIBLE", "%s is incompatible (%s vs %s): stop and ask the candidate; record "
                                                    "their decision in meta.contract_override"
                         % (where, k.get("posting"), k.get("candidate")))

    def check_questions(self):
        qs = self.p.get("questions") or []
        if len(qs) > 5:
            self.warn("W_QUESTIONS", "%d questions: keep the 5 that would change the application most" % len(qs))
        known = set(self.claims) | set(self.reqs) | set(self.fit) | set(self.ev)
        covered = set()
        for q in qs:
            ids = list(q.get("need") or []) + list(q.get("evidence") or [])
            bad = [b for b in ids if b not in known]
            if bad:
                self.err("E_BAD_REF", "question %s cites unknown ids %s" % (q.get("id"), bad))
            covered |= set(q.get("need") or [])
            if q.get("blocking") and not q.get("answer"):
                self.req("E_BLOCKING_QUESTION_OPEN", "blocking question %s is unanswered: ask it before writing"
                         % q.get("id"))
        st = self.p.get("strategy") or {}
        for i, a in enumerate(st.get("arguments", [])):
            ids = need_ids(a.get("need", ""))
            if a.get("confidence") == "low" and ids and not ids & covered:
                self.warn("W_NO_QUESTION", "low-confidence argument %d (%s) has no question that could strengthen it"
                          % (i, a.get("need")))
        for k in st.get("contract_fit") or []:
            if k.get("status") == "unknown" and k.get("id") not in covered:
                self.warn("W_NO_QUESTION", "contract_fit %s (%s) is unknown and no question asks about it"
                          % (k.get("id"), k.get("item")))

    def check_language(self):
        meta = self.p["meta"]
        if self.strict and not meta.get("language"):
            self.err("E_LANGUAGE_MISSING", "meta.language is required (the market sets conventions, not the language)")
        jl = (self.p.get("job") or {}).get("language")
        if jl and meta.get("language") and jl != meta["language"] and not meta.get("language_basis"):
            self.warn("W_LANGUAGE_MISMATCH", "documents in %r for a posting in %r: follow the posting or record why in "
                                             "meta.language_basis" % (meta["language"], jl))

    # -- semantic verification by application-auditor
    def fingerprint(self, t):
        """Hash of what a verdict examines: the statement and the current content of every reference it cites.
        Any change to the text, a cited evidence card, claim, requirement or source makes old verdicts stale."""
        refs = {"evidence": [self.ev.get(e) for e in t["evidence"]],
                "claims": [self.claims.get(c) for c in t["claims"]],
                "requirements": [self.reqs.get(r) for r in t["requirements"]],
                "sources": [dict(self.src.get(s, {"url": s}), read=self.source_digest(s)) for s in t["sources"]]}
        data = json.dumps({"target": t["target"], "text": t["text"], "refs": refs, "context": t.get("context", {})},
                          sort_keys=True, ensure_ascii=False)
        return hashlib.sha256(data.encode("utf-8")).hexdigest()[:16]

    def targets(self):
        """Every statement the auditor must check, the sources its references allow it to quote, and a fingerprint
        the verdict must copy."""
        job_source = (self.p.get("job") or {}).get("source")

        def srcs(ev_ids, claim_ids=(), req_ids=()):
            out = {str(self.ev[e].get("source", "")).split("#")[0] for e in ev_ids if e in self.ev}
            for c in claim_ids:
                out |= set(self.claims.get(c, {}).get("sources") or [])
            if job_source and [r for r in req_ids if r in self.reqs]:
                out.add(job_source)  # a requirement is quoted from the posting
            return sorted(x for x in out if x)

        cand = sorted({str(e.get("source", "")).split("#")[0] for e in self.p["evidence"] if e.get("source")})
        out = []

        def add(target, text, ev=(), claims=(), reqs=(), sources=None, context=None):
            t = {"target": target, "text": text, "evidence": list(ev), "claims": list(claims), "requirements": list(reqs),
                 "sources": sources if sources is not None else srcs(ev, claims, reqs),
                  "level": target in getattr(self, "level_lines", set()), "context": context or {}}
            t["fingerprint"] = self.fingerprint(t)
            out.append(t)

        cv = self.p.get("cv") or {}
        add("cv.identity", self.identity_text(), sources=cand)
        vp = (self.p.get("strategy") or {}).get("value_proposition")
        if vp:  # the interview pitch: a number present elsewhere ("3 years") passes the scripts, not the auditor
            argued = set().union(*[need_ids(a.get("need", "")) for a in self.p["strategy"].get("arguments", [])])
            add("strategy.value_proposition", vp, sources=sorted(set(cand) | set(srcs((), argued, argued))))
        if self.mode != "cover-letter":
            if cv.get("headline"):
                add("cv.headline", cv["headline"], sources=cand)
            for si, sec in enumerate(cv.get("sections", [])):  # a title can state a degree ("Ph.D. …")
                add("cv.sections[%d].title" % si, sec.get("title", ""), self.section_refs(sec))
            for where, _, text, refs in self.cv_items():
                add(where, text, refs)
            for where, text, refs in self.cv_lines():
                add(where, text, refs or [])
        L = self.p.get("letter") or {}
        interview = self.p.get("interview") or []
        if L:
            header_sources = set(cand)
            if job_source:
                header_sources.add(job_source)
            if L.get("recipient_source"):
                header_sources.add(L["recipient_source"])
            add("letter.header", self.letter_header_text(), sources=sorted(header_sources),
                context={"application_date": self.p["meta"].get("date"),
                         "company": self.p["meta"].get("company"), "role": self.p["meta"].get("role")})
        for i, para in enumerate(L.get("paragraphs", [])):
            add("letter.paragraphs[%d]" % i, para.get("text", ""), para.get("evidence") or [], para.get("claims") or [],
                para.get("requirements") or [])
        if L and self.named_recipient(L):
            add("letter.recipient", "\n".join([L.get("salutation", "")] + list(L.get("recipient") or [])),
                sources=[L.get("recipient_source")] if
                L.get("recipient_source") else [])
        for c, claim in self.claims.items():
            if claim.get("status") != "unavailable":
                add("claim:%s" % c, claim.get("text", ""), claims=[c], context={"status": claim.get("status")})
        for i, q in enumerate(interview):
            add("interview[%d]" % i, self.interview_text(q), q.get("evidence") or [], q.get("claims") or [],
                q.get("requirements") or [])
        # Gaps and the differentiation note reach the dossier without references of their own: they are judged
        # against every evidence card and requirement (and the company facts for differentiation).
        strategy = self.p.get("strategy") or {}
        all_ev, all_reqs = sorted(self.ev), sorted(r for r in self.reqs if isinstance(r, str))
        notes = {"kind": "assessment", "company": self.p["meta"].get("company"), "role": self.p["meta"].get("role")}
        for i, gap in enumerate(strategy.get("gaps") or []):
            add("strategy.gaps[%d]" % i, gap, all_ev, (), all_reqs, context=notes)
        if strategy.get("differentiation"):
            live = sorted(c for c, claim in self.claims.items() if claim.get("status") != "unavailable")
            add("strategy.differentiation", strategy["differentiation"], all_ev, live, all_reqs, context=notes)
        if self.targeted:
            job = self.p.get("job") or {}
            if job.get("posting_status") != "unverified" and job_source:
                add("job.posting_status", job.get("posting_status", "unverified"), sources=[job_source])
            contract = job.get("contract") or {}
            values = {k: v for k, v in contract.items() if k != "source" and v not in (None, "", "unknown")}
            if values:
                add("job.contract", json.dumps(values, sort_keys=True, ensure_ascii=False),
                    sources=[contract.get("source") or job_source] if contract.get("source") or job_source else [])
            for rid, req in self.reqs.items():
                stated = {k: req.get(k) for k in ("text", "level", "level_required") if req.get(k)}
                add("job.requirement:%s" % rid, json.dumps(stated, sort_keys=True, ensure_ascii=False), reqs=[rid])

            def assessment(target, value, basis, ev=()):
                """Derived strategy may use both the posting needs and the evidence matched to them."""
                ids = set(basis)
                for fid in ids & set(self.fit):
                    ids.update(self.fit[fid].get("basis") or [])
                claims, reqs = sorted(ids & set(self.claims)), sorted(ids & set(self.reqs))
                evidence = set(ev) | (ids & set(self.ev))
                for rid in reqs:
                    evidence.update(self.reqs[rid].get("match") or [])
                sources = sorted(set(srcs(sorted(evidence), claims, reqs)) | (ids & set(self.src)))
                if target.startswith("strategy.contract_fit["):
                    sources = sorted(set(sources) | set(cand))
                add(target, json.dumps(value, sort_keys=True, ensure_ascii=False), sorted(evidence), claims, reqs,
                    sources, context={"kind": "assessment", "company": self.p["meta"].get("company"),
                                      "role": self.p["meta"].get("role")})

            profile = self.p.get("company_profile")
            if profile and (profile.get("basis") or profile.get("hiring_triggers")):
                assessment("company_profile", profile,
                           list(profile.get("basis") or []) + list(profile.get("hiring_triggers") or []))
            strategy = self.p.get("strategy") or {}
            for key in ("hiring_context", "contribution"):
                if strategy.get(key):
                    assessment("strategy.%s" % key, strategy[key], strategy[key].get("basis") or [])
            for key in ("contract_fit", "adaptation", "arguments"):
                for i, row in enumerate(strategy.get(key) or []):
                    basis = need_ids(row.get("need", "")) if key == "arguments" else row.get("basis") or []
                    assessment("strategy.%s[%d]" % (key, i), row, basis, row.get("evidence") or [])
        return out

    def check_verdicts(self, verdicts):
        bad = verdict_structure_errors(verdicts)
        if bad:
            for msg in bad:
                self.err("E_STRUCTURE", msg)
            return
        rows = verdicts["verdicts"]
        given = {v["target"]: v for v in rows}
        missing, unchecked = [], []
        for t in self.targets():
            v = given.get(t["target"])
            if v is None:
                missing.append(t["target"])
                continue
            if v.get("fingerprint") != t["fingerprint"]:
                self.err("E_VERDICT_STALE", "%s: the statement or one of its references changed since this verdict (or "
                                            "the verdict lacks the target's fingerprint): judge it again" % t["target"])
                continue
            if v.get("verdict") not in VERDICTS:
                self.err("E_VERDICT_REJECTED", "%s: verdict %r not in %s" % (t["target"], v.get("verdict"), sorted(VERDICTS)))
                continue
            if v["verdict"] != "supported":
                self.err("E_VERDICT_REJECTED", "%s judged %s by application-auditor: %s"
                         % (t["target"], v["verdict"], v.get("note", "")))
                continue
            sid = str(v.get("source", "")).split("#")[0]
            if not t["sources"]:
                self.err("E_VERDICT_SOURCE", "%s: the statement cites no evidence, claim or requirement, so no source "
                                             "may support it" % t["target"])
                continue
            if sid not in t["sources"]:
                self.err("E_VERDICT_SOURCE", "%s: verdict quotes %s, not one of its sources %s" % (t["target"], sid, t["sources"]))
                continue
            excerpt = str(v.get("excerpt", "")).strip()
            state, text, where = self.source_state(sid)
            if not norm(excerpt):
                self.err("E_VERDICT_EXCERPT", "%s: supported verdict without meaningful source text" % t["target"])
            elif state == "missing":
                self.err("E_SOURCE_MISSING", "%s: local source %s does not exist" % (t["target"], where))
            elif state == "ok" and norm(excerpt) in norm(text):
                pass
            elif state == "ok":
                self.err("E_VERDICT_EXCERPT", "%s: excerpt not found verbatim in %s: %r" % (t["target"], sid, excerpt[:80]))
            else:  # remote page, unreadable file, partly readable PDF: the quotation could not be checked
                unchecked.append("%s (%s %s)" % (t["target"], state, where))
            if t["level"] and v.get("level_checked") is not True:
                self.err("E_VERDICT_LEVEL", "%s states a level: the verdict must compare it with the source level "
                                            "(level_checked: true)" % t["target"])
        if missing:
            self.err("E_VERDICT_COVERAGE", "%d target(s) without a verdict: %s" % (len(missing), missing[:8]))
        if unchecked:
            self.unchecked += ["verdict %s: quotation not checked" % u for u in unchecked]
            self.warn("W_VERDICT_UNCHECKED", "%d quotation(s) NOT checked (live page without local copy, or a file "
                                             "whose text cannot be extracted): %s" % (len(unchecked), unchecked[:5]))


def letter_words(pkg):
    L = pkg.get("letter") or {}
    text = " ".join(p.get("text", "") for p in L.get("paragraphs", [])).lower()
    for k in ("company", "role"):
        v = pkg.get("meta", {}).get(k, "")
        if v:
            text = text.replace(v.lower(), " ")
    return re.findall(r"[\w']+", text)


def cv_lead(pkg):
    """Headline and the first heading of each CV section: what a recruiter reads first."""
    cv = pkg.get("cv") or {}
    heads = [next((i.get("heading") for i in s.get("items", []) if i.get("heading")), None) for s in cv.get("sections", [])]
    return cv.get("headline"), [h for h in heads if h]


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
    if cv_lead(a)[0] and cv_lead(a) == cv_lead(b):
        warnings.append({"code": "W_SAME_CV_LEAD", "msg": "same CV headline and same lead entries: the top of the CV "
                                                          "does not reflect either company's needs"})
    return {"letter_similarity": round(ratio, 3), "errors": errors, "warnings": warnings}


def load_json(path):
    with open(path, encoding="utf-8-sig") as f:
        return json.load(f)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("package")
    ap.add_argument("--compare")
    ap.add_argument("--root", help="base folder for relative source paths (default: current directory)")
    ap.add_argument("--targets", nargs="?", const="-", metavar="FILE",
                    help="write the targets application-auditor must verify to FILE (UTF-8), or print them")
    ap.add_argument("--verdicts", nargs="+", metavar="FILE",
                    help="application-auditor verdicts JSON to check against the targets; with several files "
                         "(audit rounds, any order), the verdict on the current statement is used")
    a = ap.parse_args(argv)
    if hasattr(sys.stdout, "reconfigure"):  # a redirected Windows console would otherwise write cp1252
        sys.stdout.reconfigure(encoding="utf-8")
    try:
        pkg = load_json(a.package)
    except (OSError, ValueError) as exc:
        print(json.dumps({"package": a.package, "ok": False, "errors": [{"code": "E_STRUCTURE", "msg": str(exc)}]},
                         indent=2, ensure_ascii=False))
        return 1
    au = Audit(pkg, a.root).run()
    if a.targets:
        if not hasattr(au, "ev"):
            print(json.dumps({"package": a.package, "errors": au.errors, "ok": False}, indent=2, ensure_ascii=False))
            return 1
        data = json.dumps({"package": a.package, "targets": au.targets()}, indent=2, ensure_ascii=False)
        if a.targets == "-":
            print(data)
        else:
            with open(a.targets, "w", encoding="utf-8") as f:
                f.write(data + "\n")
            print(json.dumps({"targets": a.targets, "count": len(au.targets())}))
        return 0
    if a.verdicts and hasattr(au, "ev"):
        current = {t["target"]: t["fingerprint"] for t in au.targets()}
        merged = {}  # per target, the verdict on the current statement wins whatever the file order
        for f in a.verdicts:
            try:
                data = load_json(f)
            except (OSError, ValueError) as exc:
                au.err("E_STRUCTURE", "%s: %s" % (f, exc))
                continue
            bad = verdict_structure_errors(data)
            if bad:
                for msg in bad:
                    au.err("E_STRUCTURE", "%s: %s" % (f, msg))
                continue
            for v in data["verdicts"]:
                t, old = v.get("target"), merged.get(v.get("target"))
                if (old is not None and current.get(t) is not None and
                        old.get("fingerprint") == v.get("fingerprint") == current[t] and
                        old.get("verdict") != v.get("verdict")):
                    au.err("E_VERDICT_CONFLICT", "%s: conflicting verdicts on the current fingerprint; resolve the "
                                                "conflict explicitly, file order cannot select a verdict" % t)
                if old is None or v.get("fingerprint") == current.get(t) or old.get("fingerprint") != current.get(t):
                    merged[t] = v
        au.check_verdicts({"verdicts": list(merged.values())})
    safe_pkg = pkg if isinstance(pkg, dict) else {}
    meta = safe_pkg.get("meta") if isinstance(safe_pkg.get("meta"), dict) else {}
    profile = safe_pkg.get("company_profile") if isinstance(safe_pkg.get("company_profile"), dict) else {}
    out = {"package": a.package, "errors": au.errors, "warnings": au.warnings, "verification": au.verification(),
           "stats": {"schema": meta.get("schema", 1), "mode": meta.get("mode", "package"),
                     "confirmed_company_facts": getattr(au, "confirmed", 0),
                      "company_type": profile.get("type", "missing"),
                     "letter_words": getattr(au, "letter_words", 0)}}
    if a.compare and not au.initial_structure:
        try:
            other = load_json(a.compare)
            bad = list(structure_errors(other)) + list(misshapen(other)) if isinstance(other, dict) else ["package must be an object"]
            if bad:
                au.err("E_STRUCTURE", "%s: %s" % (a.compare, "; ".join(bad)))
            else:
                cmp_ = compare(pkg, other)
                out["compare"] = cmp_
                out["errors"] = out["errors"] + cmp_["errors"]
                out["warnings"] = out["warnings"] + cmp_["warnings"]
        except (OSError, ValueError) as exc:
            au.err("E_STRUCTURE", "%s: %s" % (a.compare, exc))
    out["ok"] = not out["errors"]
    print(json.dumps(out, indent=2, ensure_ascii=False))
    return 0 if out["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
