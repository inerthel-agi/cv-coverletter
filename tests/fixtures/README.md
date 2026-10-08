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

`packages/*.json` are reference outputs ("golden"): they must pass `audit_package.py` and `check_docs.py`.
`tests/run_tests.py` also mutates them to prove the guardrails reject invented facts.
