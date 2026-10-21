#!/usr/bin/env python3
"""Build a portable copy of the cv-ats-us skill for claude.ai, ChatGPT and the Gemini app.

Single source of truth: .claude/skills/cv-ats-us and .claude/agents. These apps import Agent Skills
(a folder with SKILL.md) but have no subagents, so each agent becomes a role file that the single model
runs in turn. Output (git-ignored), checked after every build:
  dist/cv-ats-us/       the skill folder (upload it where a folder is accepted)
  dist/cv-ats-us.zip    the same folder as the zip root (the layout claude.ai requires)
  dist/gemini/SKILL.md  one self-contained file for the Gemini app: references and roles appended, no scripts
  python3 tools/build_portable.py [--out DIR]
"""
import argparse
import os
import re
import shutil
import sys
import zipfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SKILL = os.path.join(ROOT, ".claude", "skills", "cv-ats-us")
AGENTS = os.path.join(ROOT, ".claude", "agents")
NAME = "cv-ats-us"
# claude.ai caps skill descriptions at 200 characters, below the 1024 of the Agent Skills spec.
DESCRIPTION = ("Tailor a CV and cover letter to a job posting or company: sourced company research, real "
               "candidate evidence only, ATS-readable DOCX/PDF, truth audit. US, FR and international markets.")
HARNESS = """Harness (portable build for claude.ai, ChatGPT and the Gemini app): there are no subagents here.
`<skill-dir>` is the folder that holds this SKILL.md. Where this file says to spawn or call an agent, take on that
role yourself: read `<skill-dir>/roles/<agent>.md` and follow it, one role at a time, and save its note as
`<dir>/notes/<agent>.md` before the next role starts. Later roles read earlier notes but never rewrite them.
`application-auditor` runs last and judges each target against the source documents, not against your drafts.
In the delivery, say that the roles ran in sequence in one conversation, not as independent agents.
Scripts need only the Python standard library: run them with `python3` (or `python`). If this environment cannot
run Python or create files, skip the script steps, give the CV, letter and dossier as structured text, list the
checks that did not run, and never claim that a file exists. Use the web search or browsing tool you have; if
there is none, ask the user to paste the posting and company pages and mark everything else unavailable."""
GEMINI_DESCRIPTION = DESCRIPTION.replace("ATS-readable DOCX/PDF", "ATS-readable CV text")
GEMINI_HARNESS = """Harness (Gemini app, single file): this file is the whole skill. There are no subagents, no
scripts and no other files. Roles: where this file says to spawn or call an agent, take on that role yourself by
following its section `roles/<agent>.md` in the appendix, one role at a time, and show its note in the conversation
before the next role starts. Later roles use earlier notes but never rewrite them. `application-auditor` runs
last and judges each statement against the source documents, not against your drafts. References: a mention of
`references/<name>.md` means the appendix section of that name. Wherever a step says to save a note or write a
file, write it in the conversation instead.
Scripts: none can run here. Skip every `python3` command and do its checks yourself: every company sentence cites a
source id with its URL and access date, or is labelled a hypothesis; every CV and letter statement matches an
evidence excerpt copied verbatim from the candidate's documents; names, dates, titles and numbers match the sources
exactly; stated levels are never upgraded; the letter body stays under 300 words. Keep the package.json content as
a structured outline in the dossier. Deliver the CV, the letter and the dossier as structured text the user can paste
into Word or Google Docs; never say that a DOCX or PDF was created. In the delivery, say that the deterministic
checks did not run and that the audit was done by the same model. Use the web search you have; never put the CV's
personal content in a search."""
# (regex, replacement) on the built SKILL.md: steps that only make sense with scripts. Each must match once.
GEMINI_EDITS = [
    (r"DOCX CV → text via\n.*?otherwise its evidence stays explicitly unverified\.",
     "Read an attached CV (DOCX, PDF) directly; if its text\n   cannot be read, ask for a text export, "
     "otherwise its evidence stays explicitly unverified."),
    (r"4\. Working folder: .*?make the final files downloadable\.",
     "4. No working folder: write every note and deliverable in the conversation."),
    (r"Files created \(paths\), mode", "Deliverables, mode"),
    (r"2\. Deterministic checks, fix until.*?(?=3\. Write `<dir>/dossier\.md`)",
     "2. Checks: do the checks listed in the harness note yourself and fix every failure.\n"),
    (r"## 6\. Independent audit\n.*?(?=Fix \*\*only\*\* confirmed problems)",
     "## 6. Audit\nRun the `application-auditor` role last, on the CV, the letter and the dossier: one verdict per CV\n"
     "line (section titles included), letter sentence, interview question and talking points, gap, differentiation\n"
     "note, company claim, requirement note, dossier question, candidate reply and warning (supported, partial,\n"
     "unsupported), each with its source id and an excerpt copied verbatim from that source; a question or warning\n"
     "that takes no fact for granted is judged neutral, without an excerpt. Ignore the role's mentions of\n"
     "targets.json, fingerprints and script outputs: judge each statement directly against its source.\n"),
    (r"Save its JSON as `<dir>/review\.json`, then\n.*?--review <dir>/review\.json`\n   checks it and computes",
     "Check its review yourself (every score below 3 has a fix, every rated\n   requirement matches the package) and "
     "compute"),
    (r"rerun the affected scripts and the audit of the changed targets", "rerun the audit of the changed statements"),
    (r"Say what the scripts prove.*?as \*\*not verified\*\*\.",
     "Say that no script checked the documents:\nevery check rests on the judgement of the same model."),
]
ROLE_NOTE = ("You take on this role yourself, inside the main conversation; it is not a separate agent. Use only "
             "the inputs listed below, never edit the candidate's sources, and save the note in the Output format "
             "below (\"final message\" means that saved note). Use the web search or browsing tool you have; if "
             "none is available, record the items as unavailable instead of guessing.")

# (old, new): each `old` must occur in the source SKILL.md, otherwise the build stops so it never ships
# Claude Code instructions by mistake. Update this list when SKILL.md changes.
EDITS = [
    ("Request: $ARGUMENTS\n\n", ""),
    ("`applications/<company>-<role>-<YYYY-MM-DD>/` (git-ignored). Write nowhere else.",
     "`applications/<company>-<role>-<YYYY-MM-DD>/` in your writable work area. Write nowhere else; at\n"
     "   delivery, make the final files downloadable."),
    ("## 1–3. Analysis (parallel agents, one message)", "## 1–3. Analysis (roles, in turn)"),
    ("Spawn these three agents in parallel (one message, exact names):", "Run these three roles in turn:"),
    ("Pass paths and URLs, never the CV's personal content to web agents. Do the analysis yourself only if the\n"
     "harness reports that the agent does not exist (then say so in the delivery).",
     "Never put the CV's personal content in a web search or a fetched URL."),
    ("**mandatory** agent call, never done inline. Spawn",
     "**mandatory** role step, saved as its own note before any document. Run"),
    ("**Write nothing (not even package.json) until its final note is back**: run it in the foreground; a launch\n"
     "acknowledgement or a failed call is not the note.",
     "**Write nothing (not even package.json) until its note is saved.**"),
    ("${CLAUDE_SKILL_DIR}", "<skill-dir>"),
]
REFERENCE_EDITS = {
    "recruiting-framework.md": [("Steps 1–3 are independent: run them in parallel.",
                                 "Steps 1–3 are independent of each other: run them one after the other.")],
}
CLAUDE_CODE_ONLY = ["$ARGUMENTS", "CLAUDE_SKILL_DIR", "subagent_type", "`Agent` tool", ".codex/", "in parallel"]


def split_frontmatter(path):
    text = open(path, encoding="utf-8").read()
    m = re.match(r"^---\n(.*?)\n---\n(.*)$", text, re.S)
    if not m:
        raise SystemExit("%s: no frontmatter" % path)
    fm = dict(line.split(":", 1) for line in m.group(1).splitlines() if ":" in line)
    return {k.strip(): v.strip() for k, v in fm.items()}, m.group(2)


def skill_md():
    _, body = split_frontmatter(os.path.join(SKILL, "SKILL.md"))
    harness = re.search(r"^Harness: Claude Code.*?\n\n", body, re.S | re.M)
    if not harness:
        raise SystemExit("SKILL.md: Harness paragraph not found; update tools/build_portable.py")
    body = apply(body.replace(harness.group(0), HARNESS + "\n\n"), EDITS, "SKILL.md")
    return "---\nname: %s\ndescription: %s\n---\n%s" % (NAME, DESCRIPTION, body)


def apply(text, edits, name):
    for old, new in edits:
        if old not in text:
            raise SystemExit("%s no longer contains %r; update tools/build_portable.py" % (name, old))
        text = text.replace(old, new)
    return text


def role_md(path):
    fm, body = split_frontmatter(path)
    return "# Role: %s\n\n%s\n\n%s\n\n%s" % (fm["name"], fm["description"], ROLE_NOTE, body.strip() + "\n")


def write(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(text)


def build(out):
    folder = os.path.join(out, NAME)
    if os.path.isdir(folder):
        shutil.rmtree(folder)
    write(os.path.join(folder, "SKILL.md"), skill_md())
    for f in sorted(os.listdir(os.path.join(SKILL, "references"))):
        if f.endswith(".md"):
            text = open(os.path.join(SKILL, "references", f), encoding="utf-8").read()
            write(os.path.join(folder, "references", f), apply(text, REFERENCE_EDITS.get(f, []), f))
    for f in sorted(os.listdir(os.path.join(SKILL, "scripts"))):
        if f.endswith(".py"):
            os.makedirs(os.path.join(folder, "scripts"), exist_ok=True)
            shutil.copyfile(os.path.join(SKILL, "scripts", f), os.path.join(folder, "scripts", f))
    for f in sorted(os.listdir(AGENTS)):
        if f.endswith(".md"):
            write(os.path.join(folder, "roles", f), role_md(os.path.join(AGENTS, f)))
    zpath = os.path.join(out, NAME + ".zip")
    with zipfile.ZipFile(zpath, "w", zipfile.ZIP_DEFLATED) as z:
        for base, _, files in os.walk(folder):
            for f in sorted(files):
                full = os.path.join(base, f)
                z.write(full, os.path.relpath(full, out).replace(os.sep, "/"))
    return folder, zpath


def build_gemini(out, folder):
    """Inline the built folder into one SKILL.md: the Gemini app reliably loads a single file."""
    text = open(os.path.join(folder, "SKILL.md"), encoding="utf-8").read()
    text = text.replace(HARNESS, GEMINI_HARNESS).replace(DESCRIPTION, GEMINI_DESCRIPTION, 1)
    for pattern, new in GEMINI_EDITS:
        text, n = re.subn(pattern, lambda _: new, text, flags=re.S)
        if n != 1:
            raise SystemExit("SKILL.md: %r matched %d times; update GEMINI_EDITS in tools/build_portable.py"
                             % (pattern, n))
    parts = [text.rstrip() + "\n\n# Appendix\nThe sections below are the reference and role files of this skill.\n"]
    for sub in ("references", "roles"):
        for f in sorted(os.listdir(os.path.join(folder, sub))):
            body = open(os.path.join(folder, sub, f), encoding="utf-8").read().strip()
            parts.append("\n---\n\n## Appendix file: %s/%s\n\n%s\n" % (sub, f, body))
    # [label](references/x.md) or [label](x.md) -> `references/x.md`: there are no files to link to.
    md = re.sub(r"\[[^\]]+\]\((?:references/)?([a-z0-9-]+\.md)\)", r"`references/\1`", "".join(parts))
    path = os.path.join(out, "gemini", "SKILL.md")
    write(path, md)
    return path


def check_gemini(path, folder):
    problems = []
    fm, body = split_frontmatter(path)
    if set(fm) != {"name", "description"} or fm.get("name") != NAME or len(fm.get("description", "")) > 200:
        problems.append("gemini: frontmatter must hold name %s and a description of 200 chars at most" % NAME)
    problems += ["gemini: Claude Code-only text %r" % s for s in CLAUDE_CODE_ONLY if s in body]
    problems += ["gemini: link to a missing file: %s" % l for l in re.findall(r"\]\(([^)#:]+)\)", body)]
    if GEMINI_HARNESS not in body or HARNESS in body:
        problems.append("gemini: the Gemini harness note must replace the folder one")
    if "python3 " in body.split("# Appendix")[0]:
        problems.append("gemini: a script command is left in the main instructions")
    for sub in ("references", "roles"):
        for f in os.listdir(os.path.join(folder, sub)):
            if "## Appendix file: %s/%s\n" % (sub, f) not in body:
                problems.append("gemini: missing appendix %s/%s" % (sub, f))
    return problems


def check(folder, zpath):
    """Return the problems that would make an upload fail or carry Claude Code-only instructions."""
    problems = []
    fm, body = split_frontmatter(os.path.join(folder, "SKILL.md"))
    if set(fm) != {"name", "description"}:
        problems.append("frontmatter keys: %s" % sorted(fm))
    if fm.get("name") != os.path.basename(folder) or not re.match(r"^[a-z0-9-]{1,64}$", fm.get("name", "")):
        problems.append("name must match the folder, lowercase, <= 64 chars")
    if not 0 < len(fm.get("description", "")) <= 200 or re.search(r"[<>]", fm.get("description", "")):
        problems.append("description must be 1-200 chars without < or > (claude.ai)")
    if len(body.splitlines()) >= 500:
        problems.append("SKILL.md body must stay under 500 lines")
    for base, _, files in os.walk(folder):
        for f in files:
            path = os.path.join(base, f)
            if os.path.splitext(f)[1] not in (".md", ".py"):
                problems.append("not plain text (Gemini): %s" % path)
            elif f.endswith(".md"):
                text = open(path, encoding="utf-8").read()
                problems += ["%s: Claude Code-only text %r" % (os.path.relpath(path, folder), s)
                             for s in CLAUDE_CODE_ONLY if s in text]
            else:
                try:
                    compile(open(path, encoding="utf-8").read(), path, "exec")
                except SyntaxError as e:
                    problems.append("%s: %s" % (path, e))
    for link in re.findall(r"\]\(([^)#]+)\)", body):
        if not os.path.isfile(os.path.join(folder, link)):
            problems.append("broken link in SKILL.md: %s" % link)
    for agent in re.findall(r"`([a-z]+(?:-[a-z]+)+)`", body):
        if os.path.isfile(os.path.join(AGENTS, agent + ".md")) and \
                not os.path.isfile(os.path.join(folder, "roles", agent + ".md")):
            problems.append("missing role file: %s" % agent)
    with zipfile.ZipFile(zpath) as z:
        names = z.namelist()
    if [n for n in names if n.lower().endswith("skill.md")] != [NAME + "/SKILL.md"]:
        problems.append("zip must hold exactly one SKILL.md, under %s/" % NAME)
    if any(not n.startswith(NAME + "/") for n in names):
        problems.append("zip root must be the %s/ folder" % NAME)
    return problems


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", default=os.path.join(ROOT, "dist"), help="output folder (default: dist/)")
    out = ap.parse_args().out
    folder, zpath = build(out)
    gemini = build_gemini(out, folder)
    problems = check(folder, zpath) + check_gemini(gemini, folder)
    for p in problems:
        print("error: " + p)
    if not problems:
        print("built: %s, %s and %s" % (folder, zpath, gemini))
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
