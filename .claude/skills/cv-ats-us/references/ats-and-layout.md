# ATS-readable layout

There is no universal ATS. Parsers differ by vendor and version, so: **never** output an "ATS score",
a match percentage, or a promise to pass a screen or get an interview. The goal is a document a human
reads in seconds and whose text any parser can extract in the right order.

## Defaults (project choices, see university-guidelines.md for what sources actually say)
| Item | US | FR | INTERNATIONAL |
|---|---|---|---|
| Paper | US Letter | A4 | country of the job, A4 if unknown |
| Font | Arial (Calibri alternative); auto-fit 10–12 pt for CV and letter | same | same |
| Name | 16–18 pt bold | same | same |
| Margins | 0.6–0.8 in (script default 0.7) | same | same |
| Photo | never | not supported by the generator; rarely useful | never unless local norm and requested |
| Length | 1 full page early-career (no blank bottom half); 2 only if justified | same | same |

## Structure
- One column. Standard section titles: Education / Experience / Projects / Skills (FR: Formation /
  Expérience / Projets / Compétences). Order by relevance to the role; reverse chronology inside sections.
  Career change: [career-change.md](career-change.md) (hybrid CV, strongest evidence first, never functional).
- Contact info in the body, not in a header/footer: name, city, phone, email, portfolio/GitHub/LinkedIn as text.
- Entry line: bold title + right-aligned dates (tab stop, not a table). Then organisation, location.
- Bullets: `action verb + work done + attested result`. A measure is optional; never invent one.
- Skills: only skills proven by evidence; qualify partial ones ("Docker (local development)").
- Never repeat a section title as a line label ("Skills:" under SKILLS); `build_docs.py` drops such labels.
- No tables, text boxes, images, icons, skill bars, colors as meaning, hidden or white text, keyword stuffing.
- Keywords: reuse the posting's exact terms **only** where the evidence supports them. ATS search matches words,
  not synonyms: write "Power BI" when the posting says it and a project used it, not "dashboards". Put each
  evidenced term in Skills **and** in the bullet that proves it. `W_TERM_NOT_IN_CV` flags an evidenced term left out.

## Files
- `scripts/build_docs.py` writes DOCX (editable, Arial/Calibri) and PDF (Helvetica = Arial metrics,
  standard PDF font, text extractable). For a pixel-exact Arial PDF, export the DOCX from Word or LibreOffice.
  Text outside the PDF font's character set (WinAnsi: e.g. ł, ő, ș, ≥) is never replaced: the PDF is refused
  (`pdf_error`) and the DOCX must be exported. `build.json` records what was built from which package content.
- `scripts/check_docs.py` verifies: paper vs market, margins, no table/image/text box/hidden text
  (direct properties, document defaults and applicable styles, respecting disabled flags),
  single column, page count (letter = 1, CV ≤ 2 with warning > 1), and that every expected string from the
  package, including rendered labels and headers, is present in **two** extractions
  (own parser + textutil/PDFKit on macOS). File patterns are expanded by the script, including on Windows.
- Fill: `build_docs.py` scales font (10–12 pt), line height (CV 1.15–1.30, letter 1.15–1.45) and spacing to
  fill the CV's minimum page count and the letter's single page, keeping 3 % slack so Word stays on the same page count (checked by exporting the DOCX from Word).
  If `fit.warning` says the page is under-filled at the maximum, add evidence-backed content (another project,
  a supported bullet, coursework); never filler. `meta.fit: false` keeps a fixed 11 pt.
- French labels use a non-breaking space before the colon ("Outils : …").
- DOCX page count is not measured (needs a renderer); the PDF uses the same layout engine and metrics.
- Submit the format the posting asks for; otherwise PDF for humans, DOCX when a portal requests Word.
