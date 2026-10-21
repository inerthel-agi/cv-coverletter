# Test fixtures — all FICTITIOUS

Person, companies, URLs (`.example`, `.invalid`), phone (`555` numbers) and email (`example.com`) are invented.
Never add real candidate data here.

| Scenario | Fixture |
|---|---|
| (a) same candidate, two companies, same job title | `packages/brindlewood.json` vs `packages/halvane.json` |
| (b) poorly documented company | `companies/quarrelane-analytics/`, `packages/quarrelane.json` (`research_level: limited`) |
| (c) required technology missing | Brindlewood requires Kubernetes, Quarrelane requires pandas: gaps, never in CV |
| (d) project without metrics | ShelfScan (`candidate/projects.md`) |
| (e) unreachable site | Quarrelane posting URL on `.invalid` → `reachable: false`, pasted copy used, warning raised |
| (f) structured CV/letter + DOCX/PDF extraction | every package, built by `build_docs.py`, checked by `check_docs.py` |
| (h) hiring-manager review | `reviews/brindlewood.json`: band `competitive` (weighted mean 3.69 on 1–4, one required gap R5) with one XYZ rewrite of a RouteWise bullet; `run_tests.py` mutates it to reach `strong`, `long-shot` and `blocked`, a career-change variant, and to reject invented matches, borrowed evidence, invented figures, missing fixes and percentages |
| (i) rejection debrief | `debriefs/brindlewood.json` (automatic rejection, ranked hypotheses: requirement gap, knockout, invisible) and `debriefs/earlier-rejection.json`: the pattern `requirement-gap` recurs; `run_tests.py` also forces a simulated decline that must be explained |
| (j) career change, finance → IT (FR) | `candidate/sacha-morel-cv.md` and `candidate/sacha-morel-projects.md`: quant analyst moving to backend or data engineering; measured run time from job logs, a personal deployed pipeline, an open-source contribution, Kubernetes only as a training exercise, C++ coursework only, an intern supervised (scope to keep exact) |
| (g) company types, same title | `brindlewood` startup (team of 18, first junior hires), `halvane` mid-size (about 420 staff, product teams), `tamberlin` SME (45 staff, first in-house engineer), `orvanta` multinational (letter written to the Orvanta Digital unit), `quarrelane` unknown (its SMEs are customers) |

`packages/*.json` are reference outputs ("golden", `meta.schema: 2`): they must pass `audit_package.py` and
`check_docs.py`. Their evidence excerpts are copied verbatim from `candidate/`; snapshot sources point to the
company files through `copy_path`. `tests/run_tests.py` also mutates them to prove the guardrails reject invented facts.
`packages/legacy/brindlewood-v1.json` is the package as committed before schema 2: older application folders must
keep auditing (new contract rules as warnings, truth rules as errors).
`verdicts/brindlewood.json` exercises the verdict checks (coverage, fingerprints, verbatim excerpts, sources,
level targets); regenerate it whenever `brindlewood.json` changes, since edited targets make its verdicts stale;
its excerpts were picked by word overlap to test the mechanism, not as an example of a careful semantic review.

Final pre-commit review update (2026-10-13): section titles, `strategy.gaps` and `strategy.differentiation` became
audit targets and interview targets now include the question. `brindlewood.json` names the documents its absences
were checked against (gaps "not in the CV or project notes", interview question "Kubernetes is not in your CV or
project notes"), as the strategist and auditor contracts require. In `verdicts/brindlewood.json`, only the two
interview verdicts were re-issued (new fingerprints; `interview[0]` now quotes the heuristic sentence) and seven
verdicts were added (four section titles, two gaps, differentiation), each excerpt hand-picked and found verbatim in
an allowed source; every other verdict is unchanged. These verdicts still only test the mechanism.

Second pre-commit review update (2026-10-13): CV targets are named by position (`cv.sections[i].items[j]`), and
dossier questions, requirement notes, warnings and candidate replies became targets. In `brindlewood.json`, the R7
note and the two question rationales name the documents an absence was checked against and keep the source's wording
("openness to relocating", not "a move"). In `verdicts/brindlewood.json`, 16 CV verdicts were renamed (same
statement, same quotation), 5 were re-issued because the R7 note is part of their references (`job.requirement:R7`,
`strategy.adaptation[1]`, both gaps, differentiation; statements unchanged), and 5 were added: `questions[0].ask`
judged neutral (it takes no fact for granted) and four quotations found verbatim in an allowed source.

Absence wording update (2026-10-21): the gap sentences of the five reference letters (and two Tamberlin
interview items) now state what the documents show ("my CV and project notes do not mention X") instead of "I have
not…", and their unsourced learning plans were removed (`E_ABSENCE_AS_FACT`, `E_UNSOURCED_COMMITMENT`). Only the
`letter.paragraphs[3]` verdict of `verdicts/brindlewood.json` was re-issued (new fingerprint, same excerpt).
