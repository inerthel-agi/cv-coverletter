# Test fixtures — all FICTITIOUS

Person, companies, URLs (`.example`, `.invalid`), phone (`555-01xx`) and email (`example.com`) are invented.
Never add real candidate data here.

| Scenario | Fixture |
|---|---|
| (a) same candidate, two companies, same job title | `packages/brindlewood.json` vs `packages/halvane.json` |
| (b) poorly documented company | `companies/quarrelane-analytics/`, `packages/quarrelane.json` (`research_level: limited`) |
| (c) required technology missing | Brindlewood requires Kubernetes, Quarrelane requires pandas: gaps, never in CV |
| (d) project without metrics | ShelfScan (`candidate/projects.md`) |
| (e) unreachable site | Quarrelane posting URL on `.invalid` → `reachable: false`, pasted copy used, warning raised |
| (f) structured CV/letter + DOCX/PDF extraction | every package, built by `build_docs.py`, checked by `check_docs.py` |
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
