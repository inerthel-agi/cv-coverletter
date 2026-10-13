#!/usr/bin/env python3
"""Check DOCX/PDF résumés and letters: text extraction, page size, layout hazards.

Stdlib only. On macOS, also cross-checks with independent extractors
(textutil for DOCX, PDFKit via osascript for PDF) when available.
This does NOT compute or promise any ATS score.

With --package, the files must also match DIR/build.json written by build_docs.py: same package content
(hash of the data, not file dates) and unchanged documents, so a document left by an earlier attempt or
edited afterwards is reported.

Usage:
  python3 check_docs.py FILE... [--market US|FR|INTERNATIONAL] [--package PKG.json] [--expect TEXT]...
  python3 check_docs.py --text FILE          # print extracted text only (e.g. a candidate's DOCX CV)
Exit code 1 if any error.
"""
import argparse
import glob
import json
import os
import re
import shutil
import subprocess
import sys
import xml.etree.ElementTree as ET
import zipfile
import zlib

from build_docs import MANIFEST, clean, file_hash, package_hash, slug

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
    with open(path, "rb") as f:
        data = f.read()
    pages = len(re.findall(rb"/Type\s*/Page(?![a-zA-Z])", data))
    mb = re.search(rb"/MediaBox\s*\[\s*([\d.\s-]+)\]", data)
    box = [float(x) for x in mb.group(1).split()] if mb else None
    fonts = sorted({f.decode() for f in re.findall(rb"/BaseFont\s*/([A-Za-z0-9+,\-]+)", data)})
    lines, low_y, skipped = [], None, 0
    for m in re.finditer(rb"<<(.*?)>>\s*stream\r?\n(.*?)\r?\nendstream", data, re.S):
        raw = m.group(2)
        if b"FlateDecode" in m.group(1):
            try:
                raw = zlib.decompress(raw)
            except zlib.error:
                skipped += 1
                continue
        # text this reader cannot decode (hex strings, TJ arrays): the extraction is incomplete
        skipped += len(re.findall(rb"<[0-9A-Fa-f\s]*>\s*Tj|\]\s*TJ", raw))
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
    return {"pages": pages, "box": box, "fonts": fonts, "text": "\n".join(lines), "low_y": low_y,
            "skipped_text": skipped}


def independent_text(path):
    """Second extractor, independent from this script (macOS only). None if unavailable."""
    try:
        if path.lower().endswith(".docx") and shutil.which("textutil"):
            r = subprocess.run(["textutil", "-convert", "txt", "-stdout", path],
                               capture_output=True, text=True, timeout=60)
            return ("textutil", r.stdout) if r.returncode == 0 else None
        if path.lower().endswith(".pdf") and sys.platform == "darwin" and shutil.which("osascript"):
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
    stem = os.path.splitext(n)[0]
    # Generated names have an explicit type between underscores, independent of the person's name.
    kinds = {"resume": "cv", "cv": "cv", "cover-letter": "letter", "lettre-de-motivation": "letter"}
    parts = stem.split("_")
    if len(parts) > 1 and parts[1] in kinds:
        return kinds[parts[1]]
    if parts[0] in kinds:
        return kinds[parts[0]]
    return "letter" if re.search(r"(?:^|[ _-])(?:letter|lettre)(?:$|[ _-])", stem) else "cv"


def expectations(pkg, kind):
    """Every string the package puts on the page, as build_docs writes it (clean() substitutions applied)."""
    cv = pkg["cv"]
    exp = [cv["name"]] + list(cv.get("contact", []))
    if kind == "cv":
        exp.append(cv.get("headline", ""))
        for sec in cv.get("sections", []):
            exp.append(sec["title"].upper())
            for it in sec.get("items", []):
                label = it.get("label")
                if label and not it.get("heading") and slug(label).lower() != slug(sec["title"]).lower():
                    exp.append(label)
                exp += [it.get(k, "") for k in ("heading", "subheading", "location", "dates")]
                exp += [b["text"] for b in it.get("bullets", [])]
                exp.append(it.get("text", ""))
    elif pkg.get("letter"):
        L = pkg["letter"]
        exp += [L.get(k, "") for k in ("date", "subject", "salutation", "closing", "signature")]
        exp += list(L.get("recipient", [])) + [p["text"] for p in L["paragraphs"]]
    return [clean(e) for e in exp if e]


def winansi_gap(s):
    out = []
    for c in s:
        try:
            c.encode("cp1252")
        except UnicodeEncodeError:
            out.append(c)
    return out


def check_manifest(files, pkg):
    """The checked files must be the ones build_docs.py produced from this package's current content."""
    strict = isinstance(pkg.get("meta", {}).get("schema"), int) and pkg["meta"]["schema"] >= 2
    results = []
    by_dir = {}
    for f in files:
        by_dir.setdefault(os.path.dirname(os.path.abspath(f)), []).append(f)
    for d, fs in sorted(by_dir.items()):
        path = os.path.join(d, MANIFEST)
        res = {"file": path, "kind": "manifest", "errors": [], "warnings": []}
        results.append(res)
        if not os.path.exists(path):
            (res["errors"] if strict else res["warnings"]).append(
                "no %s next to the documents: cannot show they were built from this package (run build_docs.py)"
                % MANIFEST)
            continue
        with open(path, encoding="utf-8-sig") as fh:
            m = json.load(fh)
        if not isinstance(m, dict) or not isinstance(m.get("files"), dict):
            res["errors"].append("build.json must contain a files object")
            continue
        if m.get("package_sha256") != package_hash(pkg):
            res["errors"].append("the package changed after build_docs.py ran: rebuild the documents")
        for f in fs:
            name = os.path.basename(f)
            if name not in m.get("files", {}):
                res["errors"].append("%s was not produced by the last build_docs.py run (left by an earlier attempt?)"
                                     % name)
            elif file_hash(f) != m["files"][name]:
                res["errors"].append("%s changed after build_docs.py wrote it" % name)
    return results


def has_hidden_text(doc, styles):
    """Check direct properties, document defaults and referenced/default styles (including their bases)."""
    document = ET.fromstring(doc)
    nodes = list(document.iter())
    if styles:
        root = ET.fromstring(styles)
        by_id = {s.get(W + "styleId"): s for s in root.findall(W + "style")}
        used = {s.get(W + "styleId") for s in by_id.values()
                if s.get(W + "default", "").lower() in ("1", "true", "on")}
        used |= {e.get(W + "val") for e in document.iter() if e.tag in (W + "pStyle", W + "rStyle")}
        pending, seen = list(used), set()
        while pending:
            sid = pending.pop()
            if sid in seen or sid not in by_id:
                continue
            seen.add(sid)
            style = by_id[sid]
            nodes.extend(style.iter())
            base = style.find(W + "basedOn")
            if base is not None:
                pending.append(base.get(W + "val"))
        defaults = root.find(W + "docDefaults")
        if defaults is not None:
            nodes.extend(defaults.iter())
    return any(e.tag == W + "vanish" and e.get(W + "val", "true").lower() not in ("0", "false", "off")
               for e in nodes)


def check_file(path, market, expects, max_pages):
    low = path.lower()
    kind = kind_of(path)
    res = {"file": path, "kind": kind, "errors": [], "warnings": [], "extractors": []}
    err, warn = res["errors"].append, res["warnings"].append
    papers = MARKET_PAPER.get(market, ["letter", "a4"])
    if low.endswith(".docx"):
        with zipfile.ZipFile(path) as z:
            names = z.namelist()
            doc = z.read("word/document.xml").decode("utf-8")
            styles = z.read("word/styles.xml").decode("utf-8") if "word/styles.xml" in names else ""
        for pat, msg in ((r"<w:tbl[ >]", "table"), (r"<w:drawing|<w:pict|<v:shape|<w:object", "image/shape"),
                          (r"<w:txbxContent", "text box"),
                         (r"<w:fldSimple|<w:instrText", "field code")):
            if re.search(pat, doc):
                err("DOCX contains %s (layout hazard for parsers)" % msg)
        if has_hidden_text(doc, styles):
            err("DOCX contains hidden text in direct properties, defaults or an applicable style")
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
    elif low.endswith(".pdf"):
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
    lost = sorted({c for m in missing for c in winansi_gap(m)}) if low.endswith(".pdf") else []
    if lost:
        err("characters outside the PDF font (WinAnsi) print as '?': %s. Export the DOCX to PDF with Word or "
            "LibreOffice; never strip them" % " ".join(lost))
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
    if hasattr(sys.stdout, "reconfigure"):  # a redirected Windows console would otherwise write cp1252
        sys.stdout.reconfigure(encoding="utf-8")
    files, input_errors = [], []
    for pattern in a.files:
        matches = [pattern] if os.path.isfile(pattern) else sorted(glob.glob(pattern)) if glob.has_magic(pattern) else []
        matches = [f for f in matches if os.path.isfile(f)]
        if not matches:
            input_errors.append({"file": pattern, "kind": "input", "errors": ["no files match this path or pattern"]})
        files += [f for f in matches if f not in files]
    if input_errors:
        print(json.dumps({"ok": False, "results": input_errors}, indent=2, ensure_ascii=False))
        return 1
    if a.text:
        for f in files:
            try:
                if f.lower().endswith((".docx", ".pdf")):
                    print(docx_text(f) if f.lower().endswith(".docx") else pdf_info(f)["text"])
                else:
                    with open(f, encoding="utf-8-sig") as fh:
                        print(fh.read())
            except (OSError, ValueError, KeyError, zipfile.BadZipFile, ET.ParseError) as exc:
                print(json.dumps({"ok": False, "file": f, "errors": [str(exc)]}, ensure_ascii=False))
                return 1
        return 0
    pkg = None
    if a.package:
        try:
            with open(a.package, encoding="utf-8-sig") as fh:
                pkg = json.load(fh)
        except (OSError, ValueError) as exc:
            print(json.dumps({"ok": False, "file": a.package, "errors": [str(exc)]}, ensure_ascii=False))
            return 1
    market = (a.market or (pkg or {}).get("meta", {}).get("market") or "INTERNATIONAL").upper()
    results = []
    for f in files:
        exp = list(a.expect) + (expectations(pkg, kind_of(f)) if pkg else [])
        try:
            results.append(check_file(f, market, exp, a.max_pages))
        except (OSError, ValueError, KeyError, zipfile.BadZipFile, ET.ParseError) as exc:
            results.append({"file": f, "kind": kind_of(f), "errors": [str(exc)], "warnings": []})
    if pkg:
        try:
            results += check_manifest(files, pkg)
        except (OSError, ValueError) as exc:
            results.append({"kind": "manifest", "errors": [str(exc)], "warnings": []})
    ok = not any(r["errors"] for r in results)
    print(json.dumps({"ok": ok, "market": market, "results": results}, indent=2, ensure_ascii=False))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
