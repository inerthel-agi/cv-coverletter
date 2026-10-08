#!/usr/bin/env python3
"""Check DOCX/PDF résumés and letters: text extraction, page size, layout hazards.

Stdlib only. On macOS, also cross-checks with independent extractors
(textutil for DOCX, PDFKit via osascript for PDF) when available.
This does NOT compute or promise any ATS score.

Usage:
  python3 check_docs.py FILE... [--market US|FR|INTERNATIONAL] [--package PKG.json] [--expect TEXT]...
  python3 check_docs.py --text FILE          # print extracted text only (e.g. a candidate's DOCX CV)
Exit code 1 if any error.
"""
import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import xml.etree.ElementTree as ET
import zipfile
import zlib

W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
DOCX_SIZES = {"letter": (12240, 15840), "a4": (11906, 16838)}
PDF_SIZES = {"letter": (612.0, 792.0), "a4": (595.28, 841.89)}
MARKET_PAPER = {"US": ["letter"], "FR": ["a4"], "INTERNATIONAL": ["letter", "a4"]}
SAFE_FONTS = {"Arial", "Calibri", "Helvetica", "Helvetica-Bold", "Times New Roman", "Georgia", "Garamond"}


# ---------------------------------------------------------------- extraction

def docx_text(path):
    with zipfile.ZipFile(path) as z:
        root = ET.fromstring(z.read("word/document.xml"))
    lines = []
    for p in root.iter(W + "p"):
        parts = []
        for el in p.iter():
            if el.tag == W + "t":
                parts.append(el.text or "")
            elif el.tag == W + "tab" and not el.attrib:  # run tab, not a tab-stop definition
                parts.append("\t")
            elif el.tag in (W + "br", W + "cr"):
                parts.append("\n")
        lines.append("".join(parts))
    return "\n".join(lines)


def _pdf_unescape(s):
    out, i = bytearray(), 0
    esc = {"n": 10, "r": 13, "t": 9, "b": 8, "f": 12, "(": 40, ")": 41, "\\": 92}
    while i < len(s):
        c = s[i]
        if c == "\\" and i + 1 < len(s):
            nxt = s[i + 1]
            m = re.match(r"[0-7]{1,3}", s[i + 1:])
            if m:
                out.append(int(m.group(0), 8) & 255)
                i += 1 + len(m.group(0))
                continue
            out.append(esc.get(nxt, ord(nxt) & 255))
            i += 2
            continue
        out.append(ord(c) & 255)
        i += 1
    return out.decode("cp1252", "replace")


PDF_TOKEN = re.compile(r"\(((?:\\.|[^\\()])*)\)|([A-Za-z'\"*]+)|\S", re.S)


def pdf_info(path):
    data = open(path, "rb").read()
    pages = len(re.findall(rb"/Type\s*/Page(?![a-zA-Z])", data))
    mb = re.search(rb"/MediaBox\s*\[\s*([\d.\s-]+)\]", data)
    box = [float(x) for x in mb.group(1).split()] if mb else None
    fonts = sorted({f.decode() for f in re.findall(rb"/BaseFont\s*/([A-Za-z0-9+,\-]+)", data)})
    lines, low_y = [], None
    for m in re.finditer(rb"<<(.*?)>>\s*stream\r?\n(.*?)\r?\nendstream", data, re.S):
        raw = m.group(2)
        if b"FlateDecode" in m.group(1):
            try:
                raw = zlib.decompress(raw)
            except zlib.error:
                continue
        ys = [float(y) for y in re.findall(rb"[\d.]+ ([\d.]+) Td", raw)]
        if ys:
            low_y = min(ys)  # lowest text baseline of the last page with positioned text
        cur, last = None, None
        for tok in PDF_TOKEN.finditer(raw.decode("latin-1")):
            lit, op = tok.group(1), tok.group(2)
            if lit is not None:
                last = lit
            elif op == "BT":
                cur, last = [], None
            elif op == "ET" and cur is not None:
                if cur:
                    lines.append("".join(cur))
                cur = None
            elif op in ("Tj", "'", '"') and cur is not None and last is not None:
                cur.append(_pdf_unescape(last))
                last = None
    return {"pages": pages, "box": box, "fonts": fonts, "text": "\n".join(lines), "low_y": low_y}


def independent_text(path):
    """Second extractor, independent from this script (macOS only). None if unavailable."""
    try:
        if path.endswith(".docx") and shutil.which("textutil"):
            r = subprocess.run(["textutil", "-convert", "txt", "-stdout", path],
                               capture_output=True, text=True, timeout=60)
            return ("textutil", r.stdout) if r.returncode == 0 else None
        if path.endswith(".pdf") and sys.platform == "darwin" and shutil.which("osascript"):
            for fw in ("PDFKit", "Quartz"):
                js = ('ObjC.import("%s"); var d = $.PDFDocument.alloc.initWithURL($.NSURL.fileURLWithPath(%s));'
                      ' d.isNil() ? "" : d.string.js' % (fw, json.dumps(os.path.abspath(path))))
                r = subprocess.run(["osascript", "-l", "JavaScript", "-e", js],
                                   capture_output=True, text=True, timeout=60)
                if r.returncode == 0 and r.stdout.strip():
                    return ("PDFKit", r.stdout)
    except (OSError, subprocess.SubprocessError):
        return None
    return None


def squash(s):
    return re.sub(r"\s+", "", s).lower()


# ---------------------------------------------------------------- checks

def kind_of(path):
    n = os.path.basename(path).lower()
    return "letter" if ("letter" in n or "lettre" in n) else "cv"


def expectations(pkg, kind):
    cv = pkg["cv"]
    exp = [cv["name"]] + list(cv.get("contact", []))
    if kind == "cv":
        for sec in cv.get("sections", []):
            exp.append(sec["title"].upper())
            for it in sec.get("items", []):
                exp += [it.get("heading", ""), it.get("dates", "")] + [b["text"] for b in it.get("bullets", [])]
                exp.append(it.get("text", ""))
    elif pkg.get("letter"):
        exp += [p["text"] for p in pkg["letter"]["paragraphs"]]
    return [e for e in exp if e]


def check_file(path, market, expects, max_pages):
    kind = kind_of(path)
    res = {"file": path, "kind": kind, "errors": [], "warnings": [], "extractors": []}
    err, warn = res["errors"].append, res["warnings"].append
    papers = MARKET_PAPER.get(market, ["letter", "a4"])
    if path.endswith(".docx"):
        with zipfile.ZipFile(path) as z:
            names = z.namelist()
            doc = z.read("word/document.xml").decode("utf-8")
            styles = z.read("word/styles.xml").decode("utf-8") if "word/styles.xml" in names else ""
        for pat, msg in ((r"<w:tbl[ >]", "table"), (r"<w:drawing|<w:pict|<v:shape|<w:object", "image/shape"),
                         (r"<w:txbxContent", "text box"), (r"<w:vanish/>|<w:vanish ", "hidden text"),
                         (r"<w:fldSimple|<w:instrText", "field code")):
            if re.search(pat, doc):
                err("DOCX contains %s (layout hazard for parsers)" % msg)
        if re.search(r"<w:(header|footer)Reference", doc):
            warn("header/footer present: some parsers ignore them; keep contact info in the body")
        cols = re.search(r'<w:cols[^>]*w:num="(\d+)"', doc)
        if cols and int(cols.group(1)) > 1:
            err("multi-column section (%s columns)" % cols.group(1))
        fonts = set(re.findall(r'w:ascii="([^"]+)"', styles + doc))
        if fonts - SAFE_FONTS:
            warn("non-standard fonts: %s" % sorted(fonts - SAFE_FONTS))
        res["fonts"] = sorted(fonts)
        sz = re.search(r'<w:rPrDefault>.*?<w:sz w:val="(\d+)"', styles, re.S)
        if sz and not 20 <= int(sz.group(1)) <= 24:
            warn("default body size %.1f pt outside 10-12 pt" % (int(sz.group(1)) / 2))
        pg = re.search(r'<w:pgSz w:w="(\d+)" w:h="(\d+)"', doc)
        if not pg:
            warn("no explicit page size")
        else:
            w, h = int(pg.group(1)), int(pg.group(2))
            res["paper"] = next((p for p, (pw, ph) in DOCX_SIZES.items() if abs(w - pw) < 40 and abs(h - ph) < 40), "other")
            if res["paper"] not in papers:
                err("paper %s does not match market %s (expected %s)" % (res["paper"], market, papers))
        mar = re.search(r'<w:pgMar w:top="(\d+)" w:right="(\d+)" w:bottom="(\d+)" w:left="(\d+)"', doc)
        if mar and not all(720 <= int(v) <= 1440 for v in mar.groups()):
            warn("margins outside 0.5-1 inch")
        text = docx_text(path)
        res["extractors"].append("docx-xml")
    elif path.endswith(".pdf"):
        info = pdf_info(path)
        res.update(pages=info["pages"], fonts=info["fonts"])
        if info["box"]:
            w, h = info["box"][2] - info["box"][0], info["box"][3] - info["box"][1]
            res["paper"] = next((p for p, (pw, ph) in PDF_SIZES.items() if abs(w - pw) < 2 and abs(h - ph) < 2), "other")
            if res["paper"] not in papers:
                err("paper %s does not match market %s" % (res["paper"], market))
        limit = 1 if kind == "letter" else max_pages
        if info["pages"] > limit:
            err("%d pages > limit %d for %s" % (info["pages"], limit, kind))
        elif kind == "cv" and info["pages"] > 1:
            warn("CV is %d pages: justify it (one page preferred for early-career)" % info["pages"])
        if info["low_y"] is not None and info["low_y"] > 1.5 * 72:
            warn("last page has %.1f in of blank space at the bottom: fill it with evidence-backed content "
                 "or let build_docs auto-fit" % (info["low_y"] / 72))
        res["bottom_blank_in"] = round(info["low_y"] / 72, 2) if info["low_y"] is not None else None
        text = info["text"]
        if text.strip():
            res["extractors"].append("pdf-ops")
    else:
        err("unsupported file type")
        return res
    ind = independent_text(path)
    texts = [text] if text.strip() else []
    if ind and ind[1].strip():
        res["extractors"].append(ind[0])
        texts.append(ind[1])
    if not texts:
        err("no extractable text")
    res["chars"] = len(text)
    missing = [e for e in expects if not all(squash(e) in squash(t) for t in texts)]
    if missing:
        err("text missing from extraction: %s" % [m[:60] for m in missing[:5]])
    return res


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("files", nargs="+")
    ap.add_argument("--market", default=None)
    ap.add_argument("--package")
    ap.add_argument("--expect", action="append", default=[])
    ap.add_argument("--max-pages", type=int, default=2, help="hard page limit for CVs (letters: 1)")
    ap.add_argument("--text", action="store_true", help="print extracted text and exit")
    a = ap.parse_args(argv)
    if a.text:
        for f in a.files:
            print(docx_text(f) if f.endswith(".docx") else pdf_info(f)["text"] if f.endswith(".pdf")
                  else open(f, encoding="utf-8").read())
        return 0
    pkg = json.load(open(a.package, encoding="utf-8")) if a.package else None
    market = (a.market or (pkg or {}).get("meta", {}).get("market") or "INTERNATIONAL").upper()
    results = []
    for f in a.files:
        exp = list(a.expect) + (expectations(pkg, kind_of(f)) if pkg else [])
        results.append(check_file(f, market, exp, a.max_pages))
    ok = not any(r["errors"] for r in results)
    print(json.dumps({"ok": ok, "market": market, "results": results}, indent=2, ensure_ascii=False))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
