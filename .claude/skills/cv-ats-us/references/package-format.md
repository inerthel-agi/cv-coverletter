# package.json — contract between analysis, generation and audit

One file per application: `applications/<company>-<role>-<YYYY-MM-DD>/package.json`.
Full examples in `tests/fixtures/packages/`: `brindlewood.json` (US startup), `halvane.json` (US mid-size),
`tamberlin.json` (US SME), `orvanta.json` (US multinational), `quarrelane.json` (FR, limited research, size unknown).

```jsonc
{
  "meta": {
    "market": "US | FR | INTERNATIONAL", "language": "en | fr | …",
    "company": "…", "role": "…", "date": "YYYY-MM-DD",
    "research_level": "standard | limited",      // limited if < 3 confirmed facts
    "warnings": ["posting unverified …"],          // required if posting not confirmed open
    "font": "Arial | Calibri", "margin_in": 0.7, "paper": "letter | a4"   // paper optional (from market)
  },
  "sources": [{"id": "S1", "kind": "official | press-release | engineering-blog | job-posting | press | user-provided | candidate",
               "url": "https://…", "title": "…", "published": "YYYY-MM-DD | unknown", "accessed": "YYYY-MM-DD",
               "reachable": true, "error": "…", "retrieved_via": "live | user-provided snapshot"}],
  "company_claims": [{"id": "C1", "status": "confirmed | hypothesis | unavailable", "text": "…", "sources": ["S1"]}],
  "company_profile": {"type": "startup | sme | mid-size | large | multinational | public-sector | non-profit | unknown",
                      "basis": ["C6"],             // confirmed claims on the company's OWN size/stage/structure; [] if unknown
                      "unit": "business unit / team / country entity hiring, or null",
                      "hiring_triggers": ["C2", "C5"],   // why hire now (hypotheses allowed, hedged)
                      "note": "…"},                // e.g. "customers are SMEs; own size undocumented"
  "job": {"source": "S4", "posting_status": "open | closed | expired | unverified",
          "requirements": [{"id": "R1", "text": "…", "level": "required | preferred",
                            "match": ["E1"], "gap_terms": ["Kubernetes"], "note": "…"}]},
  "evidence": [{"id": "E1", "title": "…", "stage": "prototype | used | …", "dates": "…",
                "tools": ["…"], "facts": ["…"], "metrics": ["…"], "source": "S6#section"}],
  "strategy": {"value_proposition": "…", "differentiation": "…", "gaps": ["…"],
               "arguments": [{"need": "C2, R1", "evidence": ["E1"], "confidence": "high", "placement": "both"}],
               "adaptation": [{"lever": "positioning | experience | projects | keywords | letter | register",
                               "choice": "…", "basis": ["C2", "R1"]}]},   // see company-context.md
  "cv": {"name": "…", "contact": ["City", "phone", "email", "portfolio"], "headline": "…",
         "sections": [{"title": "Projects", "items": [
            {"heading": "…", "subheading": "tools or organisation", "location": "…", "dates": "…",
             "bullets": [{"text": "…", "evidence": ["E1"]}]},
            {"label": "Skills", "text": "…", "evidence": ["E1", "E3"]}]}]},
  "letter": {"date": "…", "recipient": ["Hiring Team", "Company", "City"], "recipient_source": null,
             "subject": "…", "salutation": "Dear Hiring Team,",
             "paragraphs": [{"text": "…", "claims": ["C2"], "evidence": ["E1"], "addresses_gap": false}],
             "closing": "Sincerely,", "signature": "…"},
  "interview": [{"question": "…", "talking_points": "…", "evidence": ["E1"]}]
}
```

Rules enforced by `scripts/audit_package.py` (exit 1 on error):
- confirmed claim → ≥1 source with http(s) URL, title, accessed date, not unreachable, not a candidate file;
- one URL cannot be both `reachable: true` and `false` (pasted copy of a dead page stays `false`, see source-policy.md);
- < 3 confirmed claims → `research_level: "limited"`; letter must otherwise cite ≥1 confirmed claim;
- every CV bullet / line cites existing evidence; every number in CV and letter appears in the cited evidence
  (or cited claims for the letter);
- `gap_terms` never in the CV; in the letter only in a paragraph with `addresses_gap: true`;
- hypothesis claims only in hedged sentences; `unavailable` claims never used;
- letter body 150–300 words in every language;
- named recipient requires `recipient_source`; no ATS score / guarantee wording; no placeholders;
- `posting_status` other than `open` → `meta.warnings` not empty;
- `company_profile.type` other than `unknown` → a confirmed `basis` claim stating size, stage or structure
  (`E_PROFILE_UNSOURCED`); missing profile → warning; large/multinational letter should name `unit` (warning);
- job requirements present → `strategy.adaptation` not empty (`E_ADAPTATION_MISSING`); each `basis` cites existing
  claims/requirements, none unavailable (`E_ADAPTATION_UNSUPPORTED`), and not only the size claims (`E_SIZE_ONLY`);
- size clichés ("fast-paced startup", "wear many hats", "grand groupe comme le vôtre"…) in CV/letter → `E_SIZE_CLICHE`;
- `--compare OTHER.json`: letters < 75 % similar once company and role names are removed.
