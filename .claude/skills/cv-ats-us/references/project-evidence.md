# Candidate evidence

## Evidence card
`{id, title, stage, dates, tools[], facts[], metrics[], excerpts[], levels[], source}`
- `excerpts`: the source's own words, copied verbatim (≤ 30 words each), covering every number, year and level
  of the card. The audit finds each excerpt in the file; it does not judge whether a fact restates it fairly.
- `levels`: `{subject, level}` only when the source states the level, in the source's words.
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
- Unmeasured figure (estimate, survey): keep it attributed to who produced it, in the sentence or in
  brackets: "coordinators said in a survey that…", "my supervisor estimated…", "(estimated by my supervisor)" /
  "selon les coordinateurs", "(estimation de la responsable)". Stated bare, it reads as a measurement and the
  audit rejects it (`E_ESTIMATE_AS_MEASURE`). No self-deprecating disclaimers ("(self-reported; no other
  measurement)", "(déclaratif)", "(non mesuré)", "it is their own estimate and the only measurement").
- One fact per claim: never move a number or scope from one fact to another (office hours for a class of 40
  + graded SQL ≠ "graded SQL for 40 students").
- No negative-only bullets ("the app was not deployed"): scope positive bullets instead ("course prototype",
  "Docker for local development"); limits go to `dossier.md` and interview notes.

## XYZ rewrite (improvement round)
"Accomplished [X] as measured by [Y], by doing [Z]": Laszlo Bock (then Google SVP People Operations),
"My Personal Formula for a Winning Resume", LinkedIn, 2014. Original post not fetched; known through secondary
coverage (Business Insider, accessed 2026-10-21). FR: « Accompli [X], mesuré par [Y], grâce à [Z] ». A guide
for each bullet, not a template to fill in; the formula above (verb + work + attested effect) stays the rule.
- **X** = the outcome for someone (users, team, client, process), **Y** = the attested measure, **Z** = what the
  candidate personally did, with the tools actually used. Lead with X when Y exists; otherwise lead with Z.
- **Y missing**: never estimate. Either add a targeted question (origin of a number, who measured) or write Y
  qualitatively from the source: stage and scope ("used by the club's volunteers during the pilot"), adoption
  ("adopted by"), feedback with its author ("coordinators reported…"), or a before/after the source describes.
- Same evidence only: a rewrite rewords its bullet's own evidence card, never borrows another card's figure.

| Field | X (outcome) | Y (typical attested measure) | Z (method) |
|---|---|---|---|
| Tech | feature shipped, bug class removed, faster build, data made usable | users, latency, test coverage, incidents, run time | stack, design choice, tests, automation |
| Finance | closing, reporting, reconciliation, analysis delivered | deadline met, error count, volume handled, scope (entities, accounts) | model, tool (Excel, SQL, ERP), control |
| Transversal (project, ops, support, sales, HR) | process improved, people served, decision enabled | people or cases handled, time, satisfaction as reported, adoption | coordination, procedure, tool, training |
In a career change, the X of a past job is written in the target field's terms when it is the same skill
(a logistics schedule → "planned routes for N drivers"), never by renaming the job.

## Forbidden
Inventing or inflating numbers, skills, degrees, dates, titles, management, users, adoption, revenue,
responsibilities, language levels. Turning "used" into "expert", a prototype into a product, a course
into experience. `scripts/audit_package.py` rejects any number in the CV or letter not found in the cited evidence.

## Gaps
A skill listed in the candidate's own CV or skills section is self-reported evidence, not a gap: cite that
card and, when possible, a project that used it. A required skill with no evidence anywhere goes to
`job.requirements[].gap_terms`. It never appears in the CV.
The letter may address it honestly in one paragraph flagged `addresses_gap: true`
(what the documents do not show, then the nearest real evidence).

## Absences and gaps: how to write them
The sources prove what the documents contain, never what the person has not done. Write every absence as a
fact about the documents checked, from the first draft (CV, letter, interview, notes, questions):
- "My CV and project notes do not mention Airflow." / « Mon CV et mes notes de projets ne mentionnent pas
  Airflow. » Never "I have never used Airflow", « je n'ai pas encore utilisé… », « vous n'avez jamais… »
  (`E_ABSENCE_AS_FACT`), unless a candidate source says it in those words (a saved reply).
- A documented limit keeps the source's subject: "its accuracy was not formally measured", "the app was never
  deployed with Kubernetes", not "I never measured" or "I have not deployed services".
- No unsourced commitment: no learning plan, first goals or "I would learn X with the team" unless the candidate
  stated it (`E_UNSOURCED_COMMITMENT` catches the common forms; the auditor catches the rest). Name the gap,
  give the nearest evidence, and stop; ask for the plan in `questions` and put the answer, once saved, in the
  letter or the interview notes.
- An interview question presupposes nothing either: "Your documented projects do not show Airflow: how would you
  start?", not "You have never used Airflow".

## Targeted questions (`questions` in package.json)
At most 5, ranked by how much the answer would change the application, each tied to the need ids it serves:
dates, personal role in team projects, whether something was deployed or used and by whom, origin of a number,
language level, availability, contract sought, alternance rhythm (FR). Ask for a verifiable fact (link,
document, date, who measured), never for an estimate. Blocking questions are asked before writing; the others
go to the dossier.
