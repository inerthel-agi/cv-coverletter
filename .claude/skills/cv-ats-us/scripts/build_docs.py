#!/usr/bin/env python3
"""Build an ATS-friendly CV and cover letter (DOCX + PDF) from a package JSON.

Stdlib only (Python 3.9+). Output: single column, real text, no tables, images,
text boxes, headers/footers or hidden text. Format: references/package-format.md

Usage:
  python3 build_docs.py PACKAGE.json --out DIR [--only cv|letter] [--no-pdf]
Prints a JSON summary of the files written and records them in DIR/build.json (package and file hashes), so
check_docs.py can prove the documents come from this exact package. The PDF uses the standard Helvetica font
(WinAnsi): text outside it is never replaced by '?'; the PDF is refused (pdf_error, exit code 1) and the DOCX
must be exported to PDF with Word or LibreOffice.
"""
import argparse
import datetime
import hashlib
import json
import math
import os
import re
import sys
import unicodedata
import zipfile
import zlib
from xml.sax.saxutils import escape

PAPER_PT = {"letter": (612.0, 792.0), "a4": (595.28, 841.89)}
PAPER_TWIPS = {"letter": (12240, 15840), "a4": (11906, 16838)}
FONTS = ("Arial", "Calibri")
LINE = 1.15  # Word "single" spacing for Arial/Helvetica ~ 1.15 em

# Helvetica / Helvetica-Bold AFM widths, ASCII 32..126 (1/1000 em). Arial is metric-compatible.
_W_REG = ([278, 278, 355, 556, 556, 889, 667, 191, 333, 333, 389, 584, 278, 333, 278, 278] + [556] * 10 +
          [278, 278, 584, 584, 584, 556, 1015,
           667, 667, 722, 722, 667, 611, 778, 722, 278, 500, 667, 556, 833, 722, 778, 667, 778, 722, 667, 611,
           722, 667, 944, 667, 667, 611,
           278, 278, 278, 469, 556, 333,
           556, 556, 500, 556, 556, 278, 556, 556, 222, 222, 500, 222, 833, 556, 556, 556, 556, 333, 500, 278,
           556, 500, 722, 500, 500, 500,
           334, 260, 334, 584])
_W_BOLD = ([278, 333, 474, 556, 556, 889, 722, 238, 333, 333, 389, 584, 278, 333, 278, 278] + [556] * 10 +
           [333, 333, 584, 584, 584, 611, 975,
            722, 722, 722, 722, 667, 611, 778, 722, 278, 556, 722, 611, 833, 722, 778, 667, 778, 722, 667, 611,
            722, 667, 944, 667, 667, 611,
            333, 278, 333, 584, 556, 333,
            556, 611, 556, 611, 556, 333, 611, 611, 278, 278, 556, 278, 889, 611, 611, 611, 611, 389, 556, 333,
            611, 556, 778, 556, 556, 500,
            389, 280, 389, 584])
_W_EXTRA = {"•": (350, 350), "–": (556, 556), "—": (1000, 1000), "‘": (222, 278),
            "’": (222, 278), "“": (333, 500), "”": (333, 500), "…": (1000, 1000),
            "«": (556, 556), "»": (556, 556), "€": (556, 556), " ": (278, 278),
            "°": (400, 400), "·": (278, 278)}
_SUBST = {"→": "->", "←": "<-", "‑": "-", "‐": "-", " ": " ", " ": " ", "−": "-"}


def clean(s):
    """Normalise text: strip control chars, substitute glyphs missing from WinAnsi."""
    s = "".join(_SUBST.get(c, c) for c in str(s))
    return re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", "", s)


def pdf_unencodable(blocks):
    """Characters the built-in PDF font (WinAnsi / cp1252) cannot show: they would print as '?'."""
    bad = set()
    for b in blocks:
        for t in [t for t, _ in b["runs"]] + [b["right"] or ""]:
            for c in t:
                try:
                    c.encode("cp1252")
                except UnicodeEncodeError:
                    bad.add(c)
    return sorted(bad)


MANIFEST = "build.json"


def package_hash(pkg):
    """Hash of the package content (not of its file bytes or dates): same data, same hash."""
    data = json.dumps(pkg, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(data.encode("utf-8")).hexdigest()


def file_hash(path):
    with open(path, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


def write_manifest(out_dir, pkg, written):
    """Record which files this package produced; a rebuild of the same package adds to the record."""
    path, h, files = os.path.join(out_dir, MANIFEST), package_hash(pkg), {}
    try:
        with open(path, encoding="utf-8-sig") as f:
            old = json.load(f)
        if old.get("package_sha256") == h:
            files = old.get("files", {})
    except (OSError, ValueError):
        pass
    for rec in written:
        for k in ("docx", "pdf"):
            if rec.get(k):
                files[os.path.basename(rec[k])] = file_hash(rec[k])
    with open(path, "w", encoding="utf-8") as f:
        json.dump({"package_sha256": h, "files": files}, f, indent=2, ensure_ascii=False)
    return path


def char_w(ch, bold):
    i = ord(ch) - 32
    if 0 <= i < 95:
        return (_W_BOLD if bold else _W_REG)[i]
    if ch in _W_EXTRA:
        return _W_EXTRA[ch][1 if bold else 0]
    base = unicodedata.normalize("NFD", ch)[0]
    if base != ch:
        return char_w(base, bold)
    return 556


def text_w(s, bold, size):
    return sum(char_w(c, bold) for c in s) * size / 1000.0


def wrap_runs(runs, size, width):
    """Greedy word wrap of [(text, bold)] runs -> list of lines, each [(text, bold)]."""
    atoms = []
    for text, bold in runs:
        for tok in re.findall(r"\S+|\s+", text):
            atoms.append((" " if tok.isspace() else tok, bold))
    lines, cur, cur_w = [], [], 0.0

    def flush():
        while cur and cur[-1][0] == " ":
            cur.pop()
        merged = []
        for t, b in cur:
            if merged and merged[-1][1] == b:
                merged[-1] = (merged[-1][0] + t, b)
            else:
                merged.append((t, b))
        lines.append(merged)

    for tok, bold in atoms:
        w = text_w(tok, bold, size)
        if tok == " ":
            if cur:
                cur.append((tok, bold))
                cur_w += w
            continue
        if cur and cur_w + w > width:
            flush()
            cur, cur_w = [], 0.0
        while w > width:  # hard-break very long tokens (URLs)
            n = 1
            while n < len(tok) and text_w(tok[:n + 1], bold, size) <= width:
                n += 1
            lines.append([(tok[:n], bold)])
            tok = tok[n:]
            w = text_w(tok, bold, size)
        cur.append((tok, bold))
        cur_w += w
    if cur:
        flush()
    return lines or [[("", False)]]


def right_on_new_line(b, width):
    """True if a block's right-aligned text (dates) cannot share the last line of its text."""
    lines = wrap_runs(b["runs"], b["size"], width)
    last_w = sum(text_w(t, bb, b["size"]) for t, bb in lines[-1])
    return last_w + text_w(b["right"], False, b["size"]) + 12 > width


def blk(runs, size=11.0, before=0.0, after=0.0, align="left", right=None, rule=False, bullet=False,
        keep_next=False, line=LINE):
    return {"runs": [(clean(t), b) for t, b in runs if t], "size": size, "before": before, "after": after,
            "align": align, "right": clean(right) if right else None, "rule": rule, "bullet": bullet,
            "keep_next": keep_next, "line": line}


# ---------------------------------------------------------------- content -> blocks

def header_blocks(cv, name_size, contact_size=10, gap=1.0, line=LINE):
    out = [blk([(cv["name"], True)], size=name_size, align="center", after=2 * gap, line=line)]
    if cv.get("contact"):
        out.append(blk([(" | ".join(cv["contact"]), False)], size=contact_size, align="center", after=4 * gap,
                       line=line))
    return out


# CV auto-fit range (t = 0 compact .. 1 airy): text grows before gaps do. 12 pt max (Berkeley suggests 10-11 pt;
# set meta.fit = false to keep a fixed 11 pt).
FIT = {"body": (10.0, 12.0), "name": (16.0, 18.0), "contact": (9.0, 11.0), "gap": (0.6, 2.0), "line": (1.15, 1.30)}


# Letters are prose with less text: more line height and paragraph spacing, always one page.
LETTER_FIT = {"body": (10.0, 12.0), "name": (16.0, 18.0), "contact": (9.0, 11.0), "gap": (0.6, 3.0),
              "line": (1.15, 1.45)}


# Below this share of the text area, warn: ~0.8 in of blank above the bottom margin, the same point at which
# check_docs.py flags 1.5 in of blank space from the page edge.
MIN_FILL = 0.92


def style_at(t, rng=None):
    st = {k: lo + (hi - lo) * t for k, (lo, hi) in (rng or FIT).items()}
    for k in ("body", "name", "contact"):  # half-points, so DOCX and PDF use identical sizes
        st[k] = round(st[k] * 2) / 2
    return st


def cv_blocks(pkg, st=None):
    cv = pkg["cv"]
    st = st or {"body": 11.0, "name": float(cv.get("name_size", 17)), "contact": 10.0, "gap": 1.0, "line": LINE}
    sz, g, ln = st["body"], st["gap"], st["line"]
    colon = "\u00a0: " if pkg.get("meta", {}).get("language") == "fr" else ": "  # FR: non-breaking space before colon
    out = header_blocks(cv, st["name"], st["contact"], g, ln)
    if cv.get("headline"):
        out.append(blk([(cv["headline"], False)], size=sz, align="center", after=2 * g, line=ln))
    for sec in cv.get("sections", []):
        out.append(blk([(sec["title"].upper(), True)], size=sz, before=8 * g, after=3 * g, rule=True,
                       keep_next=True, line=ln))
        for i, it in enumerate(sec.get("items", [])):
            if it.get("heading"):
                bullets = it.get("bullets", [])
                sub = ", ".join(x for x in (it.get("subheading"), it.get("location")) if x)
                out.append(blk([(it["heading"], True)], size=sz, right=it.get("dates"), before=3 * g if i else 0,
                               keep_next=bool(sub or bullets), line=ln))
                if sub:
                    out.append(blk([(sub, False)], size=sz, keep_next=bool(bullets), line=ln))
                for b in bullets:
                    out.append(blk([(b["text"], False)], size=sz, bullet=True, after=1 * g, line=ln))
            else:
                label = it.get("label")
                if label and slug(label).lower() == slug(sec["title"]).lower():  # "Skills:" under SKILLS
                    label = None
                runs = ([(label + colon, True)] if label else []) + [(it["text"], False)]
                out.append(blk(runs, size=sz, after=1 * g, line=ln))
    return out


def fit_doc(pkg, make_blocks, rng, paper, margin_pt, max_pages=2):
    """Largest typography/spacing (within rng) that keeps the document on its minimum page count: fills the page."""
    def render(st):
        doc = Pdf(paper, margin_pt)
        doc.render(make_blocks(pkg, st))
        return st, doc

    def largest(lo, run):  # largest u in [lo, 1] that keeps the target page count
        hi = 1.0
        if len(run(1.0)[1].pages) <= target:
            return 1.0
        for _ in range(16):
            mid = (lo + hi) / 2
            if len(run(mid)[1].pages) <= target:
                lo = mid
            else:
                hi = mid
        return lo

    run = lambda t: render(style_at(t, rng))
    target = len(run(0.0)[1].pages)
    t = largest(0.0, run)
    # Font sizes move in half-point steps, so the next step can overflow while spacing still has room:
    # keep the chosen sizes and stretch only line height and spacing (continuous) into the remaining space.
    sizes = style_at(t, rng)
    stretch = lambda u: render(dict(sizes, gap=style_at(u, rng)["gap"], line=style_at(u, rng)["line"]))
    st, doc = stretch(largest(t, stretch))
    info = {"pages": len(doc.pages), "body_pt": st["body"], "line": round(st["line"], 3),
            "spacing": round(st["gap"], 2), "fill": round(doc.fill(), 3)}
    if target > max_pages:
        info["warning"] = "content needs %d pages even at 10 pt (limit %d): cut the weakest items" % (target, max_pages)
    elif info["fill"] < MIN_FILL:
        info["warning"] = ("page only %d%% full at the largest type and spacing that keep %d page(s): add "
                           "evidence-backed content (another project, a supported bullet), never filler"
                           % (info["fill"] * 100, target))
    return make_blocks(pkg, st), info


def letter_blocks(pkg, st=None):
    cv, L = pkg["cv"], pkg["letter"]
    st = st or {"body": 11.0, "name": 16.0, "contact": 10.0, "gap": 1.0, "line": LINE}
    sz, g, ln = st["body"], st["gap"], st["line"]
    out = header_blocks(cv, st["name"], st["contact"], g, ln)
    out.append(blk([(L.get("date", ""), False)], size=sz, before=14 * g, line=ln))
    for i, line in enumerate(L.get("recipient", [])):
        out.append(blk([(line, False)], size=sz, before=10 * g if i == 0 else 0, line=ln))
    if L.get("subject"):
        out.append(blk([(L["subject"], True)], size=sz, before=10 * g, line=ln))
    out.append(blk([(L["salutation"], False)], size=sz, before=10 * g, after=8 * g, line=ln))
    for p in L["paragraphs"]:
        out.append(blk([(p["text"], False)], size=sz, after=8 * g, line=ln))
    out.append(blk([(L.get("closing", ""), False)], size=sz, before=2 * g, line=ln))
    out.append(blk([(L.get("signature", cv["name"]), False)], size=sz, before=22 * g, line=ln))
    return out


# ---------------------------------------------------------------- PDF

def pdf_str(s):
    out = []
    for byte in s.encode("cp1252", "replace"):
        c = chr(byte)
        if c in "\\()":
            out.append("\\" + c)
        elif byte < 32 or byte > 126:
            out.append("\\%03o" % byte)
        else:
            out.append(c)
    return "(" + "".join(out) + ")"


class Pdf:
    SLACK = 0.03  # keep 3% of the text area free so Word's slightly different rounding stays on the same page

    def __init__(self, paper, margin):
        self.W, self.H = PAPER_PT[paper]
        self.m = margin
        self.floor = margin + self.SLACK * (self.H - 2 * margin)  # lowest y a line may reach
        self.pages = []
        self.new_page()

    def fill(self):
        """Share of the last page's text area that is used."""
        return (self.H - self.m - self.y) / (self.H - 2 * self.m)

    def new_page(self):
        self.ops = []
        self.pages.append(self.ops)
        self.y = self.H - self.m

    def at_top(self):
        return abs(self.y - (self.H - self.m)) < 0.01

    def text(self, x, y, line, size):
        parts, font = ["BT", "%.2f %.2f Td" % (x, y)], None
        for t, b in line:
            f = "/F2" if b else "/F1"
            if f != font:
                parts.append("%s %.1f Tf" % (f, size))
                font = f
            parts.append(pdf_str(t) + " Tj")
        parts.append("ET")
        self.ops.append(" ".join(parts))

    def render(self, blocks):
        left, cw = self.m, self.W - 2 * self.m
        for b in blocks:
            size = b["size"]
            lh = size * b["line"]
            indent = 14.0 if b["bullet"] else 0.0
            lines = wrap_runs(b["runs"], size, cw - indent)
            right_at = None  # right-aligned text (dates) sits on the last line, like a Word right tab
            if b["right"]:
                if right_on_new_line(b, cw - indent):
                    lines.append([("", False)])
                right_at = len(lines) - 1
            need = b["before"] + lh * (min(len(lines), 2) + (2 if b["keep_next"] else 0))
            if self.y - need < self.floor and not self.at_top():
                self.new_page()
            if not self.at_top():
                self.y -= b["before"]
            for i, line in enumerate(lines):
                if self.y - lh < self.floor:
                    self.new_page()
                base = self.y - size * 0.93
                lw = sum(text_w(t, bb, size) for t, bb in line)
                x = left + (cw - lw) / 2 if b["align"] == "center" else left + indent
                if b["bullet"] and i == 0:
                    self.text(left + 3, base, [("•", False)], size)
                if any(t for t, _ in line):
                    self.text(x, base, line, size)
                if i == right_at:
                    self.text(left + cw - text_w(b["right"], False, size), base, [(b["right"], False)], size)
                self.y -= lh
            if b["rule"]:
                self.ops.append("0.6 w %.2f %.2f m %.2f %.2f l S" % (left, self.y - 1, left + cw, self.y - 1))
                self.y -= 2
            self.y -= b["after"]

    def to_bytes(self, title):
        objs = []

        def add(body):
            objs.append(body)
            return len(objs)

        f1 = add(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>")
        f2 = add(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Bold /Encoding /WinAnsiEncoding >>")
        pages_n = add(b"")
        kids = []
        for ops in self.pages:
            data = zlib.compress("\n".join(ops).encode("latin-1"))
            c = add(b"<< /Length %d /Filter /FlateDecode >>\nstream\n" % len(data) + data + b"\nendstream")
            kids.append(add(("<< /Type /Page /Parent %d 0 R /MediaBox [0 0 %.2f %.2f] /Resources << /Font "
                             "<< /F1 %d 0 R /F2 %d 0 R >> >> /Contents %d 0 R >>"
                             % (pages_n, self.W, self.H, f1, f2, c)).encode()))
        objs[pages_n - 1] = ("<< /Type /Pages /Kids [%s] /Count %d >>"
                             % (" ".join("%d 0 R" % k for k in kids), len(kids))).encode()
        cat = add(b"<< /Type /Catalog /Pages %d 0 R >>" % pages_n)
        stamp = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%d%H%M%SZ")
        info = add(("<< /Title %s /Producer (cv-ats-us build_docs.py) /CreationDate (D:%s) >>"
                    % (pdf_str(title), stamp)).encode("latin-1"))
        out = bytearray(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
        offsets = []
        for i, body in enumerate(objs, 1):
            offsets.append(len(out))
            out += b"%d 0 obj\n" % i + body + b"\nendobj\n"
        xref = len(out)
        out += b"xref\n0 %d\n0000000000 65535 f \n" % (len(objs) + 1)
        for off in offsets:
            out += b"%010d 00000 n \n" % off
        out += (b"trailer\n<< /Size %d /Root %d 0 R /Info %d 0 R >>\nstartxref\n%d\n%%%%EOF\n"
                % (len(objs) + 1, cat, info, xref))
        return bytes(out)


# ---------------------------------------------------------------- DOCX

def _xml(s):
    return escape(re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", "", s))


def docx_par(b, content_twips):
    tw = lambda pt: int(round(pt * 20))
    ppr = []
    if b["keep_next"]:
        ppr.append("<w:keepNext/>")
    if b["rule"]:
        ppr.append('<w:pBdr><w:bottom w:val="single" w:sz="6" w:space="1" w:color="000000"/></w:pBdr>')
    if b["right"]:
        ppr.append('<w:tabs><w:tab w:val="right" w:pos="%d"/></w:tabs>' % content_twips)
    ppr.append('<w:spacing w:before="%d" w:after="%d" w:line="%d" w:lineRule="auto"/>'
               % (tw(b["before"]), tw(b["after"]), int(round(240 * b["line"] / LINE))))
    if b["bullet"]:
        ppr.append('<w:ind w:left="280" w:hanging="280"/>')
    if b["align"] == "center":
        ppr.append('<w:jc w:val="center"/>')
    hs = int(round(b["size"] * 2))

    def run(text, bold, tab=False, br=False):
        rpr = ("<w:b/><w:bCs/>" if bold else "") + '<w:sz w:val="%d"/><w:szCs w:val="%d"/>' % (hs, hs)
        body = ("<w:br/>" if br else "") + ("<w:tab/>" if tab else '<w:t xml:space="preserve">%s</w:t>' % _xml(text))
        return "<w:r><w:rPr>%s</w:rPr>%s</w:r>" % (rpr, body)

    runs = []
    if b["bullet"]:
        runs += [run("•", False), run("", False, tab=True)]
    runs += [run(t, bold) for t, bold in b["runs"]]
    if b["right"]:  # same decision as the PDF: dates move to their own line when the heading is too long
        br = right_on_new_line(b, content_twips / 20.0 - (14.0 if b["bullet"] else 0.0))
        runs += [run("", False, tab=True, br=br), run(b["right"], False)]
    return "<w:p><w:pPr>%s</w:pPr>%s</w:p>" % ("".join(ppr), "".join(runs))


def write_docx(path, blocks, paper, margin_in, font, lang, title, author):
    pw, ph = PAPER_TWIPS[paper]
    mt = int(round(margin_in * 1440))
    body = "".join(docx_par(b, pw - 2 * mt) for b in blocks)
    w_ns = 'xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"'
    doc = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n<w:document %s><w:body>%s'
           '<w:sectPr><w:pgSz w:w="%d" w:h="%d"/><w:pgMar w:top="%d" w:right="%d" w:bottom="%d" w:left="%d" '
           'w:header="0" w:footer="0" w:gutter="0"/><w:cols w:space="720"/></w:sectPr></w:body></w:document>'
           % (w_ns, body, pw, ph, mt, mt, mt, mt))
    styles = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n<w:styles %s><w:docDefaults><w:rPrDefault>'
              '<w:rPr><w:rFonts w:ascii="{f}" w:hAnsi="{f}" w:eastAsia="{f}" w:cs="{f}"/><w:sz w:val="22"/>'
              '<w:szCs w:val="22"/><w:lang w:val="{l}"/></w:rPr></w:rPrDefault><w:pPrDefault><w:pPr>'
              '<w:spacing w:after="0" w:line="240" w:lineRule="auto"/></w:pPr></w:pPrDefault></w:docDefaults>'
              '<w:style w:type="paragraph" w:default="1" w:styleId="Normal"><w:name w:val="Normal"/><w:qFormat/>'
              '</w:style></w:styles>' % w_ns).replace("{f}", font).replace("{l}", lang)
    now = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    parts = {
        "[Content_Types].xml": (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
            '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
            '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
            '<Default Extension="xml" ContentType="application/xml"/>'
            '<Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.'
            'wordprocessingml.document.main+xml"/>'
            '<Override PartName="/word/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.'
            'wordprocessingml.styles+xml"/>'
            '<Override PartName="/docProps/core.xml" ContentType="application/vnd.openxmlformats-package.'
            'core-properties+xml"/>'
            '<Override PartName="/docProps/app.xml" ContentType="application/vnd.openxmlformats-officedocument.'
            'extended-properties+xml"/></Types>'),
        "_rels/.rels": (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/'
            'officeDocument" Target="word/document.xml"/>'
            '<Relationship Id="rId2" Type="http://schemas.openxmlformats.org/package/2006/relationships/metadata/'
            'core-properties" Target="docProps/core.xml"/>'
            '<Relationship Id="rId3" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/'
            'extended-properties" Target="docProps/app.xml"/></Relationships>'),
        "word/_rels/document.xml.rels": (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/'
            'styles" Target="styles.xml"/></Relationships>'),
        "word/document.xml": doc,
        "word/styles.xml": styles,
        "docProps/core.xml": (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n<cp:coreProperties '
            'xmlns:cp="http://schemas.openxmlformats.org/package/2006/metadata/core-properties" '
            'xmlns:dc="http://purl.org/dc/elements/1.1/" xmlns:dcterms="http://purl.org/dc/terms/" '
            'xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"><dc:title>%s</dc:title><dc:creator>%s'
            '</dc:creator><dcterms:created xsi:type="dcterms:W3CDTF">%s</dcterms:created></cp:coreProperties>'
            % (_xml(title), _xml(author), now)),
        "docProps/app.xml": (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n<Properties xmlns="http://schemas.'
            'openxmlformats.org/officeDocument/2006/extended-properties"><Application>cv-ats-us</Application>'
            '</Properties>'),
    }
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
        for name, data in parts.items():
            z.writestr(name, data.encode("utf-8"))


# ---------------------------------------------------------------- main

# Latin letters with no Unicode decomposition: NFKD would drop them from file names ("Łucja" -> "ucja")
FOLD = str.maketrans({"Ł": "L", "ł": "l", "Ø": "O", "ø": "o", "Đ": "D", "đ": "d", "Þ": "Th", "þ": "th", "ß": "ss",
                      "Æ": "AE", "æ": "ae", "Œ": "OE", "œ": "oe", "ı": "i"})


def slug(s):
    a = unicodedata.normalize("NFKD", s.translate(FOLD)).encode("ascii", "ignore").decode()
    if len(re.findall(r"[A-Za-z]", a)) < len(re.findall(r"[^\W\d_]", s)):  # a letter would vanish: keep the name
        a = unicodedata.normalize("NFC", s)
    return re.sub(r"[\W_]+", "-", a).strip("-") or "x"


def _number(v):
    return type(v) in (int, float) and math.isfinite(v)


# (block, key, valid, rule): generation settings, checked only when present (absent = default).
SETTINGS = (
    ("meta", "market", lambda v: isinstance(v, str), "must be text (US, FR or INTERNATIONAL)"),
    ("meta", "language", lambda v: isinstance(v, str), "must be text"),
    ("meta", "paper", lambda v: v in (None, "") or (isinstance(v, str) and v in PAPER_PT), "must be letter or a4"),
    ("meta", "font", lambda v: isinstance(v, str) and v in FONTS, "must be one of %s" % ", ".join(FONTS)),
    ("meta", "margin_in", lambda v: _number(v) and 0.5 <= v <= 1.0, "must be a number of inches within 0.5-1.0"),
    ("meta", "fit", lambda v: type(v) is bool, "must be true or false"),
    ("meta", "max_cv_pages", lambda v: type(v) is int and v >= 1, "must be a whole number of pages, 1 or more"),
    ("cv", "name_size", lambda v: _number(v) and v > 0, "must be a positive number of points"),
)


def settings_errors(meta, cv=None):
    """Located errors in the generation settings. audit_package.py reports them before generation; build()
    refuses them before writing anything, instead of crashing or silently ignoring a value."""
    blocks = {"meta": meta, "cv": cv}
    return ["%s.%s %s (got %r)" % (block, key, rule, blocks[block][key]) for block, key, valid, rule in SETTINGS
            if isinstance(blocks[block], dict) and key in blocks[block] and not valid(blocks[block][key])]


def settings(meta, cv=None):
    errors = settings_errors(meta, cv)
    if errors:
        raise SystemExit("invalid generation settings: " + "; ".join(errors))
    market = meta.get("market", "US").upper()
    paper = meta.get("paper") or {"US": "letter", "FR": "a4"}.get(market, "a4")
    margin = float(meta.get("margin_in", 0.7))
    font = meta.get("font", "Arial")
    lang = meta.get("language", "en")
    return market, paper, margin, font, {"en": "en-US", "fr": "fr-FR"}.get(lang, lang)


def build(pkg, out_dir, only=None, pdf=True):
    meta = pkg.get("meta", {})
    market, paper, margin, font, lang = settings(meta, pkg.get("cv"))
    only = only or {"cover-letter": "letter", "create": "cv", "tailor": "cv"}.get(meta.get("mode"))
    fr = meta.get("language", "en") == "fr"
    name, company = pkg["cv"]["name"], meta.get("company", "")
    kinds = {"cv": ("CV" if fr or market != "US" else "Resume", cv_blocks),
             "letter": ("Lettre-de-motivation" if fr else "Cover-Letter", letter_blocks)}
    os.makedirs(out_dir, exist_ok=True)
    written = []
    for kind, (label, fn) in kinds.items():
        if (only and kind != only) or (kind == "letter" and not pkg.get("letter")):
            continue
        fit = None
        if meta.get("fit", True):
            rng, limit = (FIT, int(meta.get("max_cv_pages", 2))) if kind == "cv" else (LETTER_FIT, 1)
            blocks, fit = fit_doc(pkg, fn, rng, paper, margin * 72, limit)
        else:
            blocks = fn(pkg)
        stem = os.path.join(out_dir, "_".join(x for x in (slug(name), label, slug(company) if company else "") if x))
        title = "%s - %s" % (name, label.replace("-", " "))
        write_docx(stem + ".docx", blocks, paper, margin, font, lang, title, name)
        rec = {"kind": kind, "docx": stem + ".docx"}
        lost = pdf_unencodable(blocks) if pdf else []
        if lost:
            rec.update(pdf=None, pdf_error="characters outside the built-in PDF font (WinAnsi): %s. No PDF written: "
                                           "export the DOCX to PDF with Word or LibreOffice; never remove or replace "
                                           "these characters (names, places)" % " ".join(lost))
        elif pdf:
            doc = Pdf(paper, margin * 72)
            doc.render(blocks)
            with open(stem + ".pdf", "wb") as f:
                f.write(doc.to_bytes(title))
            rec.update(pdf=stem + ".pdf", pages=len(doc.pages))
        if fit:
            rec["fit"] = fit
        written.append(rec)
    return {"market": market, "paper": paper, "font_docx": font, "font_pdf": "Helvetica (Arial-metric)",
            "files": written, "manifest": write_manifest(out_dir, pkg, written)}


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("package")
    ap.add_argument("--out", required=True)
    ap.add_argument("--only", choices=["cv", "letter"])
    ap.add_argument("--no-pdf", action="store_true")
    a = ap.parse_args(argv)
    if hasattr(sys.stdout, "reconfigure"):  # a redirected Windows console would otherwise write cp1252
        sys.stdout.reconfigure(encoding="utf-8")
    with open(a.package, encoding="utf-8-sig") as f:
        pkg = json.load(f)
    res = build(pkg, a.out, a.only, not a.no_pdf)
    print(json.dumps(res, indent=2, ensure_ascii=False))
    return 1 if any(r.get("pdf_error") for r in res["files"]) else 0


if __name__ == "__main__":
    sys.exit(main())
