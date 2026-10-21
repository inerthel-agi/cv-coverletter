# Rejection debrief (mode `debrief`)

A generic rejection ("we decided to move forward with other candidates") gives no reason. The real reason stays
unknown: the debrief ranks **hypotheses**, each with the signals for and against it, and turns the likely ones
into CV changes. It never states a cause as fact and never contacts the recruiter.

## Inputs
- The CV and letter **exactly as sent** (the files, not a later version).
- The posting (URL or the saved copy) and, if any, the earlier application folder with its `package.json`.
- The rejection context, from the candidate: date sent, date of the rejection, stage (`no-reply`, `automatic`,
  `recruiter-screen`, `after-interview`, `unknown`), the rejection message copied verbatim, and the portal's
  screening questions with the answers given, if remembered.

## Folder
`applications/<company>-<role>-<date>/debrief-<YYYY-MM-DD>/`: `sent/` (copies of the sent files), `rejection.md`
(the message and context, verbatim, listed as a `candidate` source), `review.sent.json`, `debrief.json`,
`debrief.md`.

## Steps
1. **Package of the sent version.** If the application was built by this skill and `build.json` matches the sent
   files, use its `package.json`. Otherwise run `candidate-evidence` and `job-intelligence` (and
   `company-researcher` if a letter was sent), then write a `package.json` whose `cv` and `letter` transcribe
   the sent documents **verbatim**, without improving them; its `meta.mode` is the mode of the sent application. Errors from `audit_package.py` on this package are
   findings (a number the sources cannot back, a skill without evidence), not things to hide.
2. **In parallel** (one message):
   - `job-intelligence`: the posting today. Still open, closed or reposted? Did the requirements change?
     → `posting_now`.
   - `hiring-manager`: the sent version. Its JSON is `review.sent.json`: it declines with a clear explanation
     when the band is `long-shot` or `blocked`.
   - Text extraction of the sent files:
     `python3 <skill-dir>/scripts/check_docs.py "<dir>/sent/*.pdf" "<dir>/sent/*.docx"` (no `--package`). A file
     with no extractable text, or text in the wrong order, makes `ats-parse` a strong hypothesis.
3. **Rank the causes** (main session), from the table below, into `debrief.json`.
4. **Check**:
   `python3 <skill-dir>/scripts/audit_package.py <dir>/package.json --review <dir>/review.sent.json --debrief <dir>/debrief.json [earlier debrief.json …]`
   Passing earlier debriefs of the same candidate lists `patterns`: causes in the top 3 of two or more rejections.
5. **Write `debrief.md`** for the candidate, in their language: what we know and what we do not, the ranked
   hypotheses, the manager's explanation (weak points, why it would decline), the readjustment plan (most effect
   first, with the XYZ rewrites from [project-evidence.md](project-evidence.md)), questions for the candidate,
   recurring patterns, and the feedback request draft.
6. **Next application**: pass `debrief.json` to `recruitment-strategist` in the next `tailor` or `package` run.

## Signals → causes
| Signal | Points to |
|---|---|
| Rejection within hours, `automatic` stage | `knockout` (a screening answer: authorisation, location, years, degree) or `ats-parse` |
| `check_docs.py` extraction failure, columns, text in images | `ats-parse` |
| A required requirement rated `gap`, most of all one the posting stresses | `requirement-gap` |
| Evidenced posting terms missing from the CV (`coverage`, `W_TERM_NOT_IN_CV`) | `keywords` |
| `level_fit` ≤ 2, `level_match: below`, or far more experience than asked | `level` |
| `first_screen` ≤ 2 | `first-screen` |
| `evidence_strength` ≤ 2, prototypes or bullets without effect | `evidence` |
| `company_fit` or `motivation` ≤ 2, letter fits any company | `company-fit`, `motivation` |
| `coherence` or `career_bridge` ≤ 2 in a career change | `coherence` |
| Posting closed soon after, or nothing weak found | `invisible` (filled internally, volume, budget): say it cannot be checked |
| Posting reposted unchanged | the role is still open: the application, not the vacancy, did not convince |
| Rejection `after-interview` | the documents passed: the debrief covers the CV and letter only; say so |

## debrief.json
```json
{"debrief": {
  "rejection": {"sent": "YYYY-MM-DD", "received": "YYYY-MM-DD", "stage": "automatic", "message": "generic",
                "source": "S31"},
  "posting_now": "open | reposted | closed | unverified",
  "extraction_ok": true,
  "hypotheses": [{"rank": 1, "cause": "keywords", "for": ["…"], "against": ["…"],
                  "basis": ["R2", "first_screen"], "action": "how to readjust the CV"}],
  "questions": ["what only the candidate can answer"],
  "feedback_request": "short draft, the candidate's to send or not"}}
```
Ranks run 1..n without ties. Every cause except `invisible` has signals for it, `basis` ids (package ids or
rubric criteria) and an `action`. `audit_package.py` rejects certainty ("the reason was…", « la raison est… »),
percentages and probabilities.

## Feedback request draft
Three to five sentences: thanks, the role and date, one precise question ("which part of my profile fell short
for this role?"), openness to future roles. No pressure, no argument, no attachment. The candidate decides
whether to send it; the skill never sends it.

## Limits
A debrief judges the documents, not the competition, the budget or the interview. With one rejection, the ranking
is weak evidence; patterns across several rejections for similar roles are stronger.
