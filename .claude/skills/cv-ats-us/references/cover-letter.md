# Cover letter

One page. Specific to this company and role. Does not repeat the CV line by line.

## Structure (Yale / Harvard pattern, see university-guidelines.md)
1. **Opening** (1–3 sentences): role + why this company, anchored on one *confirmed*, cited fact (with limited
   research: a requirement of the posting). The paragraph cites it (`claims` or `requirements`).
2. **Body** (1–2 paragraphs, 3–5 sentences each): one need per paragraph → candidate's best evidence →
   what it shows. Prefer the strongest project over a weaker job.
3. **Gap** (optional, `addresses_gap: true`): honest and short. State what the documents do not show
   ("My CV and project notes do not mention X"), then the nearest real evidence. A ramp-up plan only in the
   candidate's own words from a saved reply; never "I have never…" or an invented commitment
   ([project-evidence.md](project-evidence.md), "Absences and gaps").
4. **Closing** (`contribution: true`): plausible contribution (hedged if based on a hypothesis), from
   `strategy.contribution`, invitation to talk.

## Contribution and contract
The contribution comes from what the posting says the person will do and deliver, read with the hiring
context and the candidate's evidence; its basis cites a confirmed claim or a posting requirement. The contract
only bounds it: never a horizon longer than a stated duration, and a stated rhythm (alternance) limits what can
be promised. The contract type alone never decides it; with no stated duration, state no horizon.

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
a recruiter's name or gender. "Madame Dupont," or "Dear Hiring Manager Sarah Lee," names a person: the audit
requires the source, whatever the language; "Madame, Monsieur," and "Dear Hiring Team," do not.

## Tone
Plain, confident, active voice, specific. Ban: "dream company", "world-class", "I have always admired",
unverifiable superlatives, flattery, claims about the company not in `company_claims`.
Every company statement maps to a claim id; every candidate statement maps to an evidence id.
Placing two facts side by side states a link: a candidate fact right after an organisation or a company
capability reads as belonging to it (a pilot after a named charity, a grouping heuristic after an API that
"optimizes"). Write a link only when a source states it; otherwise keep the facts in separate paragraphs.
Hypotheses stay hedged: "If the team is focused on…", "D'après l'offre, le poste semble…".
Figures from an estimate or a survey stay attributed to who produced them, in the sentence ("coordinators said
in a survey that…") or in brackets ("(estimated by my supervisor)"); stated bare they would read as measurements
(`E_ESTIMATE_AS_MEASURE`). No self-deprecating disclaimer ("(self-reported; no other measurement)"). No sources inside the letter (URLs, "(company
blog, dated …)"): mention the fact naturally ("your engineering blog describes…"); citations live in `dossier.md`.

## Differentiation test
Same candidate, two companies, same title: the opening fact, the lead evidence and the contribution must
change for reasons traceable to each company's sources. `audit_package.py A --compare B` fails at ≥ 75 %
word-sequence similarity once company and role names are removed.
