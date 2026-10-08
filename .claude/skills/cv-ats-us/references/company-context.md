# Company context — read the hire like the hiring manager

Company size is a **weak prior**: it tells you which questions to research, never what to write.
Every adaptation of the CV or letter cites a verified need: a confirmed claim (`C…`) or a posting
requirement (`R…`), recorded in `strategy.adaptation`.

## Three questions before writing
1. **Why hire now?** A documented trigger: launch, funding, expansion, migration, new regulation, new team,
   first hire in the function, several similar open roles. Otherwise a hedged hypothesis. A backfill is
   usually unknowable: do not guess.
2. **What problem will this person take off someone's desk in the first 6–12 months?** From the posting's
   missions crossed with the company's documented priorities.
3. **What risk does the hiring manager want to reduce, and which evidence lowers it?** Ramp-up time on the
   stack, autonomy without a senior nearby, regressions in a shared codebase, contact with non-technical
   users or customers, fitting an existing process, language or site coverage.

## `company_profile`
| type | only when a confirmed claim states | where it is usually stated |
|---|---|---|
| `startup` | recent founding, funding stage or small stated team | about/team page, funding release |
| `sme` | small or medium independent business (EU: < 250 staff) | about page, legal registry, local press |
| `mid-size` | established, hundreds to a few thousand staff, several products or sites | careers, newsroom |
| `large` / `multinational` | group, several countries or business units | annual report, group site |
| `public-sector` / `non-profit` | statute, public body, mission funding | official site, annual report |
| `unknown` | default | — |

The source need not use the category word: a stated headcount, founding/funding or structure is enough
(e.g. "about 420 people in two cities" → `mid-size`).

Traps:
- Customer size ≠ company size: "dashboards for SMEs" says nothing about the publisher's headcount.
- Group ≠ hiring unit: at a group, research the business unit, country entity, product and team; use a
  group-wide fact only when a source shows it reaches that team, and name the unit in the letter (`unit`).
- A name ("Labs", "Group"), a modern site or office photos prove nothing.
- Job-board size ranges are leads; a LinkedIn company page reachable without login may support
  "LinkedIn lists 51–200 employees" (self-declared, dated).
- Headcount and funding age quickly: give the date; prefer sources under 24 months.

## Research focus by type (questions, not conclusions)
| type | look first at |
|---|---|
| startup | product pages and changelog, funding announcement, what is launched vs planned, team page |
| sme | services and customers, the business process the role touches, leadership statements, local press, registry |
| mid-size | product lines, newsroom, engineering blog, new market or growth, the team the role joins |
| large / multinational | unit and team pages, the team's product, group programmes that reach it (annual report, strategy pages), stated processes |
| public-sector / non-profit | mission, funded programmes, public reports, regulatory or procurement constraints |
| unknown | the posting; expect `research_level: limited` |

## Verified signal → adaptation
| Signal (sourced) | CV | Letter |
|---|---|---|
| First or only hire in the function; small team stated | lead with work owned end to end; breadth; direct contact with users | the concrete problem the hire takes on; autonomy shown by evidence, not claimed |
| Recent launch, funding or growth | shipping and iterating on a real user problem; tests | tie the lead evidence to the launched product |
| Several teams, stated process (code review, release, SDLC, compliance) | testing, CI, documentation, working within conventions; the posting's exact terms | how the evidence fits their process; name the unit and product, not the group |
| Regulated domain | rigour, data handling, traceability | the constraint, only if sourced |
| Migration or transformation (stack named) | evidence on the target stack first | the migration and its date |
| User- or customer-facing role | adoption, support, feedback from users | the users named by the sources |
| Several sites or languages | language, written communication | the sites named by the sources |
| Nothing verified | requirements in posting order | posting-based and cautious |

## Levers (`strategy.adaptation`: `{"lever", "choice", "basis": [ids]}`)
- `positioning`: headline and value proposition.
- `experience`: which bullets lead; how a transferable job is framed (support job → users, automation).
- `projects`: which projects, in which order; leave out what does not serve a verified need.
- `keywords`: the posting's exact terms, only where evidence supports them; gaps stay gaps.
- `letter`: opening fact, body evidence, closing contribution (hedged if hypothesis).
- `register`: mirror the company's own posting/careers tone; FR stays formal.
A basis made only of the `company_profile.basis` claims is refused (`E_SIZE_ONLY`): size alone justifies nothing.

## Size clichés (refused by the audit, `E_SIZE_CLICHE`)
"fast-paced startup", "wear many hats", "startup mindset", "a global leader like yours", "a large company like
yours", "company of your size", "esprit start-up", "grand groupe comme le vôtre", "entreprise à taille humaine".
Write the sourced fact instead: "a team of 18 hiring its first junior engineers", "FieldLink's shared CI pipeline".
