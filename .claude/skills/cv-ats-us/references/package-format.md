# package.json — contract between analysis, generation and audit

One file per application: `applications/<company>-<role>-<YYYY-MM-DD>/package.json`.
The schema below is complete: build each package from this application's own sources, never from another
package or a test fixture.

```jsonc
{
  "meta": {
    "schema": 2,                                   // integer 1 or 2; absent = older package (see below)
    "mode": "create | tailor | cover-letter | package",
    "market": "US | FR | INTERNATIONAL",           // paper and country conventions
    "language": "en | fr | …",                     // language of the documents
    "language_basis": ["R4"],                      // only if language differs from job.language: why (ids or "user")
    "company": "…", "role": "…", "date": "YYYY-MM-DD",
    "research_level": "standard | limited",      // limited if < 3 confirmed facts
    "warnings": ["posting unverified …"],          // required if posting not confirmed open
    "contract_override": "…",                      // only if the candidate chose to apply despite an incompatible row
    "font": "Arial | Calibri", "margin_in": 0.7, "paper": "letter | a4"   // margin 0.5–1.0; paper optional (from market)
  },
  "sources": [{"id": "S1", "kind": "official | press-release | engineering-blog | job-posting | press | user-provided | candidate",
               "url": "https://… | inputs/cv.pdf", "title": "…", "published": "YYYY-MM-DD | unknown", "accessed": "YYYY-MM-DD",
               "reachable": true, "error": "…", "retrieved_via": "live | user-provided snapshot",
               "copy_path": "inputs/about.md"}],   // local copy of a snapshot: lets excerpts be checked offline
  "company_claims": [{"id": "C1", "status": "confirmed | hypothesis | unavailable", "text": "…", "sources": ["S1"]}],
  "company_profile": {"type": "startup | sme | mid-size | large | multinational | public-sector | non-profit | unknown",
                      "basis": ["C6"],             // confirmed claims on the company's OWN size/stage/structure; [] if unknown
                      "unit": "business unit / team / country entity hiring, or null",
                      "hiring_triggers": ["C2", "C5"],   // why hire now (hypotheses allowed, hedged)
                      "note": "…"},                // e.g. "customers are SMEs; own size undocumented"
  "job": {"source": "S4", "posting_status": "open | closed | expired | unverified", "language": "en",
          "contract": {"type": "cdi | cdd | internship | alternance | apprenticeship | full-time | part-time | fixed-term | freelance | unknown",
                       "duration_months": 24, "rhythm": "3 days company / 2 days school", "start": "2027-09",
                       "location": "Lyon", "remote": "hybrid", "source": "S4"},   // only what the posting states, else null
          "requirements": [{"id": "R1", "text": "…", "level": "required | preferred",
                            "level_required": "fluent | 3+ years | …",            // posting's words, or null
                            "level_match": "meets | below | unknown",              // set by the strategist
                            "match": ["E1"], "gap_terms": ["Kubernetes"], "note": "…"}]},
  "evidence": [{"id": "E1", "title": "…", "stage": "prototype | used | …", "dates": "…",
                "tools": ["…"], "facts": ["…"], "metrics": ["…"], "source": "S6#section",
                "excerpts": ["words copied verbatim from the source"],          // every number/year of the card is in them
                "levels": [{"subject": "English", "level": "fluent"}]}],       // only levels the source states
  "strategy": {"value_proposition": "…", "differentiation": "…", "gaps": ["…"],
               "arguments": [{"need": "C2, R1", "evidence": ["E1"], "confidence": "high | medium | low",
                              "placement": "cv | letter | both | interview"}],
               "adaptation": [{"lever": "positioning | experience | projects | keywords | letter | register",
                               "choice": "…", "basis": ["C2", "R1"]}],   // see company-context.md
               "hiring_context": {"problem": "…", "risk": "…", "basis": ["C2", "R1"]},
               "contract_fit": [{"id": "K1", "field": "type | start | location | duration | rhythm | remote | language | authorization",
                                 "item": "start date", "posting": "…", "candidate": "…",
                                 "status": "compatible | incompatible | unknown", "basis": ["S4", "E8"]}],
               "contribution": {"scope": "…", "horizon_months": 6, "basis": ["C2", "R1"]}},
  "questions": [{"id": "Q1", "need": ["R5", "K2"], "evidence": ["E1"], "ask": "…", "why": "…",
                 "blocking": false, "answer": null}],   // answer: the candidate's reply, saved as a candidate source
  "cv": {"name": "…", "contact": ["City", "phone", "email", "portfolio"], "headline": "…",
         "sections": [{"title": "Projects", "items": [
            {"heading": "…", "subheading": "tools or organisation", "location": "…", "dates": "…",
             "evidence": ["E1"],                     // optional: item-level evidence (else its bullets' evidence)
             "bullets": [{"text": "…", "evidence": ["E1"]}]},
            {"label": "Skills", "text": "…", "evidence": ["E1", "E3"]}]}]},
  "letter": {"date": "…", "recipient": ["Hiring Team", "Company", "City"], "recipient_source": null,
             "subject": "…", "salutation": "Dear Hiring Team,",
             "paragraphs": [{"text": "…", "claims": ["C2"], "evidence": ["E1"], "requirements": ["R1"],
                             "addresses_gap": false, "contribution": false}],
             "closing": "Sincerely,", "signature": "…"},
  "interview": [{"question": "…", "talking_points": "…", "evidence": ["E1"], "claims": ["C3"], "requirements": []}]
}
```

## Truth rules: errors for every package, old or new (`scripts/audit_package.py`, exit 1)
- confirmed claim → ≥1 source with http(s) URL, title, real accessed date, `reachable: true`, not a candidate file;
  `published` is a real date or `unknown`; a publication date cannot follow the access date;
- one URL cannot be both `reachable: true` and `false` (pasted copy of a dead page stays `false`, see source-policy.md);
- `posting_status` is `open | closed | expired | unverified`; `open` needs `job.source` with `reachable: true`;
  any other status needs `meta.warnings`;
- < 3 confirmed claims → `research_level: "limited"`; letter must otherwise cite ≥1 confirmed claim;
- every CV bullet / line, including its label, and every heading item (organisation, title, degree, dates) cites existing evidence;
  every section prints content under its title (`E_CV_EMPTY_SECTION`, a label that repeats the title does not count);
  every number in the CV (section titles included), letter and interview questions and points appears in the cited
  evidence (claims and cited requirements for the letter); numbers in the value proposition appear in the package's
  evidence or claims, and in gaps and differentiation in its evidence, claims or requirements; years in CV dates
  appear in the cited evidence;
- evidence read from a local file: excerpts found verbatim, and every number and year of the card inside its
  excerpts (older packages without excerpts: inside the document). Source states are kept apart: a declared
  local file that does not exist is an error (`E_SOURCE_MISSING`); a file whose text cannot be extracted (or a
  PDF the reader only partly decodes, even when its quotes were found, or a live page without local copy) leaves the card **unverified**
  (`W_EVIDENCE_UNCHECKED`, listed in `verification.unchecked`, `complete: false`); a readable file without the
  quote is an error. An excerpt empty after normalization is invalid. A `.docx`/`.md` export recorded as
  `copy_path` is read instead of an unreadable PDF. A direct candidate URL is remote, not a missing local file;
- a figure from an estimate or survey stays attributed where it is used ("my supervisor estimated…",
  "(estimated by …)"); stated bare → `E_ESTIMATE_AS_MEASURE`; calendar dates and ISO date-times ("October 2, 2026",
  "2 octobre 2026", "2026-10-02", "2026-10-02T10:00+02:00") are not figures;
- generation settings `market`, `language`, `paper`, `font`, `margin_in` (0.5–1.0), `fit`, `max_cv_pages` and
  `cv.name_size` have valid types and values (located `E_STRUCTURE`); `build_docs.py` refuses the same values
  before writing anything;
- `gap_terms` never in the CV, even when the requirement is partly matched; in the letter only in a paragraph
  with `addresses_gap: true`;
- hypothesis claims only in hedged sentences; `unavailable` claims never used;
- letter body 150–300 words in every language;
- named recipient (civility + name, or a name in the salutation, in any language) requires `recipient_source`;
  no ATS score / guarantee wording; no placeholders;
- a CEFR level in the documents or the interview talking points never exceeds the level recorded in the cited
  evidence; argument with
  `confidence: low` never placed in the CV; `confidence: high` never on a requirement whose `level_match` is
  `below`; need ids of arguments exist;
- `contract_fit`: `compatible` needs candidate-side evidence; a field the posting does not state is `unknown`,
  never compatible or incompatible; `incompatible` needs `meta.contract_override`;
  a contribution horizon (in `strategy.contribution` or in the contribution paragraph) never exceeds
  `job.contract.duration_months`;
- `company_profile.type` other than `unknown` → a confirmed `basis` claim stating size, stage or structure
  (`E_PROFILE_UNSOURCED`); large/multinational letter should name `unit` (warning);
  `non-profit` and `public-sector` instead need a confirmed legal-status claim;
- job requirements present → `strategy.adaptation` has each of the six levers exactly once (`E_ADAPTATION_MISSING`);
  each `basis` (adaptation,
  hiring context, contribution) cites existing claims/requirements, none unavailable (`E_ADAPTATION_UNSUPPORTED`),
  not only the size claims (`E_SIZE_ONLY`), and at least one confirmed claim or posting requirement: hypotheses
  and contract rows may complete a basis, never form it alone (`E_ADAPTATION_UNVERIFIED`);
- size clichés ("fast-paced startup", "wear many hats", "grand groupe comme le vôtre"…) in CV/letter → `E_SIZE_CLICHE`;
- `--compare OTHER.json`: letters < 75 % similar once company and role names are removed; same CV headline and
  lead entries → `W_SAME_CV_LEAD`.

## Contract rules: errors for `meta.schema: 2`, warnings (`W_…`) for older packages
- `meta.schema`, when present, is the integer `1` or `2`; strings, booleans and other versions are errors,
  never an implicit downgrade. Objects, text, numbers and id lists have the documented types; malformed input
  gets a located `E_STRUCTURE`. `cv.name` is non-empty text. Durations/horizons are positive numbers or null;
- `meta.mode` and `meta.language` stated (language also in `create`); keys required by the mode (`create`: cv + evidence; `tailor`: + sources,
  claims, job, strategy; `cover-letter` and `package`: + letter);
- evidence read from a local file has `excerpts`; a language level or CEFR in the documents or the interview
  talking points cites evidence with recorded `levels`;
- `job.contract` and `strategy.contract_fit` present, with one row per `field` for `type`, `start`, `location`,
  plus `duration` and `rhythm` when the posting states them (`[]` is incomplete); `strategy.hiring_context` with
  problem, risk and basis;
  letter modes: `strategy.contribution` and one paragraph flagged `contribution: true`; the opening paragraph
  cites a claim or requirement;
- every required requirement has `match` or `gap_terms`; a `level_required` with a match has `level_match`;
- `strategy.arguments` and `value_proposition` present; argument enums valid; `package` mode has interview points;
- blocking questions are answered before writing.
Warnings for every package: self-reported-only `high` confidence, unknown contract rows or low-confidence
arguments without a question, more than 5 questions, documents in another language than the posting without
`meta.language_basis`.

## What the scripts cannot prove
They check references, numbers, years, verbatim quotations and structure. They do not prove that a sentence
means what its source says: a month shifted inside the same year, "expected" turned into "awarded", a number
moved from one fact to another, "fluent" turned into "bilingual", a source that does not say the claim. Those
are judged by `application-auditor`: `audit_package.py --targets FILE` lists every statement to check, the
sources its references allow it to quote (cited evidence, claims, and the posting for cited requirements) and
a `fingerprint` of the statement, its `context`, the current content of those references, source metadata and
the text actually read from each source document (its `copy_path` when present). Binary and partly readable
sources also include a file-byte hash. Complete plaintext uses its whole decoded text so fingerprints remain
portable across checkout line endings. Targets cover every text of the documents and the dossier, each with the
treatment below (`context.kind`); `strategy.gaps` and `strategy.differentiation` cite no ids: they are judged
against every evidence card and requirement, plus the company facts for differentiation. An assessment may be an
explicitly qualified inference; it is never a new factual
claim. `letter.header.context.application_date` supplies the application stamp; the auditor checks that the
displayed date matches it and checks names/contacts/role against source files. `--verdicts audit.json` rejects
a missing target, a stale verdict (fingerprint changed: the statement or a reference was edited), a verdict
other than `supported`, a source outside the target's references, a target with no reference at all, a level
target without `level_checked`, a `"neutral": true` verdict on a target that is not a question or a technical
note, and an excerpt not found verbatim in a readable local source or empty after
normalization. Conflicting verdict statuses on the same current fingerprint are errors regardless of file
order; resolve the saved conflict explicitly. Quotations it cannot check (live page, unreadable or partly
readable file) are listed in `verification.unchecked`, never counted as verified.

| Treatment | Fields (target names) | A `supported` verdict |
|---|---|---|
| statement to source | `cv.identity`, `cv.headline`, `cv.sections[i].title`, `cv.sections[i].items[j]` and `….bullets[k]`, `letter.*`, `interview[i]` (question and talking points), confirmed `claim:<id>`, `job.posting_status`, `job.contract`, `job.requirement:<id>`; candidate replies `questions[i].answer`, `meta.contract_override` | quotes one of its sources; a reply is quoted from the copy saved as a `candidate` source |
| qualified hypothesis | hypothesis `claim:<id>`, `company_profile`, `strategy.*`, `job.requirement:<id>.note`, `questions[i].why` (`kind: assessment`) | quotes the facts it rests on; the inference stays hedged |
| neutral question | `questions[i].ask` (`kind: question`) | `"neutral": true` when it takes no fact for granted; a premise is quoted |
| technical note | `meta.warnings[i]`, a `company_profile` that cites no claim (`kind: technical`) | `"neutral": true` when it only restates the package's records (source states and dates, posting status, research level); any other fact is quoted |
| not a target | `unavailable` claims (never used), ids, enums, source metadata | checked by the scripts |

CV targets are named by position, so two sections with the same title never share a target and a reordered
section's verdicts go stale. The CV, the letter and the interview talking points state the candidate's levels
(anchored in leveled evidence); a level an interview question asks about, or a dossier note mentions, makes the
target a level target only. In dossier text, a CEFR-like code that is also a package id (claim `C2`) is a level
only next to a language name or a level word.

## Documents built from the package
`build_docs.py` writes `build.json` next to the documents (hash of the package content and of each file).
`check_docs.py --package` fails when the package changed after the build, or when a document is not the one
the last build wrote. Schema 2: `build.json` is required; older folders get a warning.
The scripts accept JSON UTF-8 with or without a BOM. `check_docs.py` accepts case-insensitive extensions,
expands quoted file patterns on every platform, and diagnoses unmatched patterns. Document kind follows the
generated `Resume`/`CV`/`Cover-Letter`/`Lettre-de-motivation` marker, never a substring of the candidate's name.
