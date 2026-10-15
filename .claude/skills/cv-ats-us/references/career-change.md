# Career change (reconversion)

Applies when the candidate's past job titles do not name the target role (e.g. logistics → data analyst).
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
(project, training, result). No apology, no "despite my lack of experience". The gap paragraph rules of
[project-evidence.md](project-evidence.md) apply.

## Strategy fields
`recruitment-strategist` records the pivot in the `positioning` lever and the chosen section order in the
`experience` and `projects` levers, each with its `basis` ids.
