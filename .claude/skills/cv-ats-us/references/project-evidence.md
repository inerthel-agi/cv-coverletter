# Candidate evidence

## Evidence card
`{id, title, stage, dates, tools[], facts[], metrics[], source}`
- `facts`: what the candidate personally did, in their own documents' terms. Team work → state the
  team size and the candidate's part.
- `tools`: only tools actually used in this item (not "familiar with").
- `metrics`: only measures present in the source, with their nature (measured, survey, estimate by whom).
- `stage`: `idea` < `prototype` < `delivered` < `deployed` < `used` < `measured`; also `coursework`,
  `experience`, `self-reported` (languages, availability).

## Reading a project
| Question | Why |
|---|---|
| Problem and context? | Links to a company need |
| What exactly did *you* do? | Separates personal action from team output |
| Tools really used? | Prevents keyword inflation |
| Stage reached? | Prototype ≠ product ≠ adoption |
| Who used it, how many, how long? | Real adoption, if stated |
| Any measure? How obtained? | Only attested numbers survive |
| Role of AI tools? | Using an AI assistant is not mastery of the underlying tech |

## Bullet formula
`action verb + what was built/done + attested effect`.
- With metric: "Piloted with 4 coordinators for 3 weeks; they reported planning time falling from ~25 to ~10 min."
- Without metric (never invent one): "Built OpenCV preprocessing and trained a PyTorch model that counts
  products on shelf photos (course prototype, public dataset)." Stage and scope replace the missing number.
- Transferable experience is valid when it proves a relevant skill (support job → reliability, automation).
- Unmeasured figure: attribute it once, in plain words, inside the sentence: "coordinators said in a survey
  that…", "my supervisor estimated…" / "selon les coordinateurs", "selon l'estimation de la responsable".
  No parenthetical disclaimers ("(self-reported; no other measurement)", "(déclaratif)", "(non mesuré)") and no
  "it is their own estimate and the only measurement" sentences: the audit rejects them.
- One fact per claim: never move a number or scope from one fact to another (office hours for a class of 40
  + graded SQL ≠ "graded SQL for 40 students").
- No negative-only bullets ("the app was not deployed"): scope positive bullets instead ("course prototype",
  "Docker for local development"); limits go to `dossier.md` and interview notes.

## Forbidden
Inventing or inflating numbers, skills, degrees, dates, titles, management, users, adoption, revenue,
responsibilities, language levels. Turning "used" into "expert", a prototype into a product, a course
into experience. `scripts/audit_package.py` rejects any number in the CV or letter not found in the cited evidence.

## Gaps
A skill listed in the candidate's own CV or skills section is self-reported evidence, not a gap: cite that
card and, when possible, a project that used it. A required skill with no evidence anywhere goes to
`job.requirements[].gap_terms`. It never appears in the CV.
The letter may address it honestly in one paragraph flagged `addresses_gap: true`
(what is missing, nearest real evidence, concrete ramp-up).

## Questions to ask (only if blocking)
Dates, personal role in team projects, whether something was deployed or used and by whom,
origin of a number, language level, availability / alternance rhythm (FR).
