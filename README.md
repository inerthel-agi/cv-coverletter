# cv-ats-us — company-first job applications for Claude Code

Turns a candidate's real evidence and verifiable research on a company (startup, SME, mid-size,
multinational, public or non-profit) into an ATS-readable CV, a cover letter written for **that** company,
and interview talking points. Strategy comes before writing; every
company fact is sourced and dated or labelled as a hypothesis; every candidate claim traces to a document.

## Requirements
- Claude Code with project skills and subagents (tested with 2.1.294). `AGENTS.md` is read natively.
- Python 3.9+ (stdlib only, no install). macOS adds independent text-extraction checks (textutil, PDFKit).
- WebSearch/WebFetch for company research. No MCP server or external dependency required.

## Usage
```
/cv-ats-us Tailor my CV to this posting https://… and write a cover letter explaining why my projects are relevant to this company. CV: inputs/cv.pdf, projects: inputs/projects.md
```
Modes: `create`, `tailor`, `cover-letter`, `projects`, `audit`, `package` (CV + letter + dossier).
Markets: `US` (English, US Letter, no photo), `FR` (French, A4, degree / availability / alternance when known),
`INTERNATIONAL` (posting language). Inferred from the posting when not given.

Put private inputs in `inputs/`; outputs land in `applications/<company>-<role>-<date>/` — both git-ignored:
`package.json` (sources, claims, evidence, strategy, texts), `*_Resume|CV_*.docx/.pdf`,
`*_Cover-Letter|Lettre-de-motivation_*.docx/.pdf`, `dossier.md` (brief, evidence table, strategy, interview prep).

## How it works
| Step | Component | Tools |
|---|---|---|
| Company intelligence | `.claude/agents/company-researcher.md` | WebSearch, WebFetch, Read (read-only) |
| Why the role exists | `.claude/agents/job-intelligence.md` | WebFetch, WebSearch, Read (read-only) |
| Candidate evidence | `.claude/agents/candidate-evidence.md` | Read, WebFetch (read-only) |
| Positioning + adaptation per lever | `.claude/agents/recruitment-strategist.md` | Read (read-only) |
| Writing + files | `.claude/skills/cv-ats-us/SKILL.md` + `scripts/` | main session |
| Independent audit | `.claude/agents/application-auditor.md` | Read, WebFetch (read-only) |

Model policy: a large model orchestrates, subagents run small — Claude Code agents use `model: haiku`
(Haiku 5.5) whatever the main model (Fable, Opus, Sonnet). Deterministic guardrails in `scripts/`:
`audit_package.py` (traceability, no invented numbers, gaps never in the CV, hedged hypotheses, no ATS
score, differentiation with `--compare`, company type sourced, adaptations traced to verified needs, no
size-only choice or size cliché), `build_docs.py` (DOCX + PDF), `check_docs.py` (layout and
two-way text extraction). References and university sources: `.claude/skills/cv-ats-us/references/`.

## Codex
- Skill: `.agents/skills/cv-ats-us` is a symlink to the Claude skill (one source). Invoke with `$cv-ats-us`.
- Agents: `.codex/agents/*.toml`, generated from `.claude/agents/*.md` with `model = "gpt-6-luna"` and
  `sandbox_mode = "read-only"`. After editing an agent: `python3 tools/sync_codex_agents.py`.
- Codex only loads `.codex/` for **trusted** projects: accept the trust prompt when opening this folder in
  Codex, or add `[projects."<this folder>"] trust_level = "trusted"` to `~/.codex/config.toml`.
  Untrusted, the skill still loads but the five agents do not.
- Web search inside Codex subagents depends on your `web_search` setting (not documented for subagents).

## Global install (links, single source)
`SKILL.md` at the root links to `.claude/skills/cv-ats-us/SKILL.md` (edit either, same file; its relative
links resolve from the skill folder). Installed for every folder as links to this project:
`~/.claude/skills/cv-ats-us`, `~/.claude/agents/<agent>.md`, `~/.agents/skills/cv-ats-us` (Codex),
`~/.codex/agents/<agent>.toml` (Codex). Moving or deleting this folder breaks them.

## Tests
```bash
python3 tests/run_tests.py
```
Offline, fictitious fixtures: config/frontmatter, privacy, DOCX/PDF build and extraction, and guardrail
mutations for scenarios (a) two companies, (b) poorly documented company, (c) missing technology,
(d) project without metrics, (e) unreachable site, (f) document extraction, (g) the same title at a startup,
an SME, a mid-size company, a multinational and a company of unknown size.

```bash
python3 tests/e2e/run_e2e.py --model haiku
```
Live: runs `/cv-ats-us` headless on the same fixtures and checks the outputs. Uses API credits
(`--budget` per scenario); never applies or sends anything.

## Company context
The researcher classifies the company only from its own sourced size/stage/structure facts (customer size is
not company size; a group is not the hiring unit) and finds why it is hiring now. The strategist then records
one adaptation per lever (positioning, experience, projects, keywords, letter, register), each traced to a
claim or requirement id. Size steers research, never content: see
`.claude/skills/cv-ats-us/references/company-context.md`.

## Limits
- No ATS score, no guarantee of passing a screen or getting an interview: parsers differ.
- Research is light and targeted: public pages only; no login, CAPTCHA, paywall or anti-bot bypass;
  LinkedIn often requires login and is then skipped. Thin results lead to cautious personalisation.
- The PDF uses Helvetica (Arial metrics, standard PDF font). For an exact Arial/Calibri PDF, export the DOCX
  from Word or LibreOffice. DOCX page count is approximated by the PDF.
- No photo support; no automatic applying, emailing or form filling.
