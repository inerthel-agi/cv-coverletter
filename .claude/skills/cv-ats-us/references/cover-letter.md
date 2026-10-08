# Cover letter

One page. Specific to this company and role. Does not repeat the CV line by line.

## Structure (Yale / Harvard pattern, see university-guidelines.md)
1. **Opening** (1–3 sentences): role + why this company, anchored on one *confirmed*, cited fact.
2. **Body** (1–2 paragraphs, 3–5 sentences each): one need per paragraph → candidate's best evidence →
   what it shows. Prefer the strongest project over a weaker job.
3. **Gap** (optional, `addresses_gap: true`): honest, short, nearest evidence, ramp-up plan.
4. **Closing**: plausible contribution (hedged if based on a hypothesis), invitation to talk.

## Length
- Every language: **300 words maximum** for the body (audit error above 300 or below 150; target 220–300).
- Over the limit: cut CV repetition first, then the weakest evidence; never drop the sourced opening fact or
  an honest gap paragraph.

## Market conventions
- US: date, recipient block, optional "Re:" line, "Dear Hiring Team," / "Dear Hiring Manager,",
  "Sincerely,". No photo, age, marital status.
- FR: subject line starting with "Objet : …" (audit error otherwise), "Madame, Monsieur,", formal closing ("Je vous prie d'agréer…"). Mention degree,
  availability date and alternance rhythm **only if known and relevant**.
- INTERNATIONAL: language of the posting; conventions of the job's country.

## Recipient
Generic salutation unless a name is **sourced** (`letter.recipient_source` → a source id). Never guess
a recruiter's name or gender.

## Tone
Plain, confident, active voice, specific. Ban: "dream company", "world-class", "I have always admired",
unverifiable superlatives, flattery, claims about the company not in `company_claims`.
Every company statement maps to a claim id; every candidate statement maps to an evidence id.
Hypotheses stay hedged: "If the team is focused on…", "D'après l'offre, le poste semble…".
Unmeasured figures are attributed once, in the sentence ("coordinators said in a survey that…"), never with a
disclaimer in brackets or an extra sentence about measurement. No sources inside the letter (URLs, "(company
blog, dated …)"): mention the fact naturally ("your engineering blog describes…"); citations live in `dossier.md`.

## Differentiation test
Same candidate, two companies, same title: the opening fact, the lead evidence and the contribution must
change for reasons traceable to each company's sources. `audit_package.py A --compare B` fails at ≥ 75 %
word-sequence similarity once company and role names are removed.
