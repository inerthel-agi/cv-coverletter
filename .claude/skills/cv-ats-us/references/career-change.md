# Career change (reconversion)

Applies when the candidate's past job titles do not name the target role (e.g. logistics → data analyst).
A student or recent graduate in the target field whose past jobs were student or side jobs is not a career change.
Project guidance, not a university rule; the posting's explicit requirements still win.

## Where the ATS risk really is
No parser rejects "a career change". The risks are concrete:
| Risk | Cause | Answer |
|---|---|---|
| Not found by recruiter search | the target title and skills appear nowhere | headline with the target role; posting's terms in Skills/Projects where evidence supports them |
| Knockout question (years, degree, licence) | portal form, not the CV | never fake: declared gap; tell the candidate in `dossier.md` before they apply |
| Misread structure | functional (skills-only) CV, no dates | keep a dated, reverse-chronological hybrid CV |
| Human skim stops at line 3 | unrelated job first | lead with the section that proves the target skills |

## What to put first
Rank sections by the strength of evidence they carry for the strategy matrix's **top needs**, not by type:
1. Headline: the target role, honest about the stage ("Junior Data Analyst — career change from logistics",
   "Développeur web junior en reconversion"). Never rename a past job title.
2. The section holding the highest-confidence evidence for the top 1–3 needs. In a reconversion this is
   usually **Projects** (delivered or deployed, dated, with tools) or the **target-field training/certificate**.
3. Skills: only evidenced skills, in the posting's words; this is what recruiter keyword search reads.
4. Experience: always kept (no unexplained gap), reverse chronological, compressed to the bullets that prove
   transferable needs (users, deadlines, processes, data, automation). An unrelated job keeps 1–2 bullets.
5. Education.
Exception: if a past job directly proves a top need (support job → customer-facing role, Excel reporting →
data role), Experience leads. A personal project never moves into Experience; real freelance, volunteer or
internal work in the target field does, under its true title and status.

Standard titles only: "Projects" / "Projets", "Relevant Experience" / "Other Experience" when splitting helps
("Expérience" / "Autres expériences"); never "My journey", "Portfolio adventures".

## Letter
One sentence on the pivot: what moved the candidate, then the evidence that the move is already under way
(project, training, result). No apology, no "despite my lack of experience", no "I have never…": a missing
skill is what the documents do not mention. The gap paragraph rules of
[project-evidence.md](project-evidence.md) apply.

## Strategy fields
`recruitment-strategist` records the pivot in the `positioning` lever and the chosen section order in the
`experience` and `projects` levers, each with its `basis` ids.

## Hiring-manager review
`hiring-manager` reads a reconversion as a manager would: why this move, why now, what is already done in the
new field, what carries over. It sets `career_change: true`, which adds the `career_bridge` criterion and doubles
the weight of `coherence`. It lists transferable skills, relevant past work and achievements worth showing even
under an unrelated title, and rewrites their bullets in the target field's terms (XYZ, same evidence). A pivot
explained and under way scores as coherent; the career change itself is never a penalty and is never hidden.
A `long-shot` band still means apply, with the fixes that give the application its best chance.
