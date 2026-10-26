# -*- coding: utf-8 -*-
"""Pre-push scan of the repository for things that must not be published.

  python tools/check_forbidden.py [ROOT]

Checks
  * absolute paths: C:\\Users, /home/, /Users/
  * forbidden words (Dropbox and scratchpad, matched case-insensitively); project-specific labels go in the
    external list given by DEMO_NAME_LIST, like names
  * secret-looking strings (sk-..., AKIA..., ghp_..., AIza..., api_key = <long token>)
  * .ipynb files: non-empty outputs, execution counts, and metadata keys beyond kernelspec/language_info
  * optional: names listed in the file named by the environment variable DEMO_NAME_LIST
    (one name per line; the list itself must never be put in the repository)
  * optional: 12-character verbatim matches against the text files under DEMO_CORPUS_DIR
    (checked only against files below an `inputs/texts` folder)

Exit status 1 if anything is found. A clean result is NOT a guarantee: the scan can miss things.
This file is excluded from its own scan (it contains the words it looks for), and so is BUILD_REPORT.md.
"""
import json
import os
import re
import sys

SKIP_DIRS = {".git", "__pycache__", ".pytest_cache", "outputs", ".venv", "venv", "node_modules"}
SKIP_FILES = {os.path.join("tools", "check_forbidden.py"), "BUILD_REPORT.md"}

PATH_PATTERNS = [("abs_path", re.compile(r"[A-Za-z]:[\\/]+Users|/home/|/Users/"))]
# Personal names and model names are NOT listed here (this file is public); put them in the
# external list given by DEMO_NAME_LIST.
WORDS = [("scratchpad", re.I), ("Dropbox", re.I)]
WORD_PATTERNS = [("word:" + w, re.compile(re.escape(w), fl)) for w, fl in WORDS]
SECRET_PATTERNS = [
    ("secret", re.compile(r"sk-[A-Za-z0-9_-]{16,}")),
    ("secret", re.compile(r"AKIA[0-9A-Z]{16}")),
    ("secret", re.compile(r"gh[pousr]_[A-Za-z0-9]{20,}")),
    ("secret", re.compile(r"AIza[0-9A-Za-z_-]{30,}")),
    ("secret", re.compile(r"(?i)api[_-]?key[\"']?\s*[:=]\s*[\"']?[A-Za-z0-9_-]{20,}")),
]
SHINGLE = 12


def iter_files(root):
    for d, dirs, files in os.walk(root):
        dirs[:] = [x for x in dirs if x not in SKIP_DIRS]
        for f in files:
            p = os.path.join(d, f)
            rel = os.path.relpath(p, root)
            if rel in SKIP_FILES:
                continue
            yield p, rel


def read_text_or_none(p):
    try:
        with open(p, "rb") as f:
            return f.read().decode("utf-8-sig")
    except (UnicodeDecodeError, OSError):
        return None


def norm(s):
    return re.sub(r"\s+", "", s)


def corpus_shingles(corpus_dir):
    sh = set()
    for d, _, files in os.walk(corpus_dir):
        for f in files:
            t = read_text_or_none(os.path.join(d, f))
            if t:
                t = norm(t)
                sh.update(t[i:i + SHINGLE] for i in range(len(t) - SHINGLE + 1))
    return sh


def scan_ipynb(text):
    out = []
    try:
        nb = json.loads(text)
    except Exception:  # noqa: BLE001
        return ["ipynb:unparseable"]
    extra = set((nb.get("metadata") or {}).keys()) - {"kernelspec", "language_info"}
    if extra:
        out.append("ipynb:notebook metadata keys " + ",".join(sorted(extra)))
    for i, c in enumerate(nb.get("cells", [])):
        if c.get("outputs"):
            out.append("ipynb:cell %d has outputs" % i)
        if c.get("execution_count") is not None:
            out.append("ipynb:cell %d has an execution count" % i)
        cm = set((c.get("metadata") or {}).keys()) - {"id"}
        if cm:
            out.append("ipynb:cell %d metadata keys %s" % (i, ",".join(sorted(cm))))
    return out


def scan(root, names=None, corpus=None):
    """Return a list of (relative path, line number or 0, category, detail)."""
    findings = []
    names = names or []
    for p, rel in iter_files(root):
        text = read_text_or_none(p)
        if text is None:
            continue
        if p.endswith(".ipynb"):
            findings += [(rel, 0, "ipynb", d) for d in scan_ipynb(text)]
        lines = text.split("\n")
        for n, line in enumerate(lines, 1):
            for cat, rx in PATH_PATTERNS + WORD_PATTERNS + SECRET_PATTERNS:
                if rx.search(line):
                    findings.append((rel, n, cat, "pattern hit"))
            for k, name in enumerate(names):
                if name and name in line:
                    findings.append((rel, n, "name_list", "entry #%d" % (k + 1)))
        if corpus and (os.sep + "inputs" + os.sep + "texts" + os.sep) in (os.sep + rel):
            t = norm(text)
            hits = sum(1 for i in range(len(t) - SHINGLE + 1) if t[i:i + SHINGLE] in corpus)
            if hits:
                findings.append((rel, 0, "corpus_12char", "%d overlapping 12-character windows" % hits))
    return findings


def main(argv=None):
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    argv = sys.argv[1:] if argv is None else argv
    root = os.path.abspath(argv[0]) if argv else os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    names, corpus = [], None
    nl = os.environ.get("DEMO_NAME_LIST")
    if nl:
        names = [x.strip() for x in open(nl, encoding="utf-8-sig").read().split("\n") if x.strip()]
        print("name list: %d entries (from DEMO_NAME_LIST)" % len(names))
    else:
        print("name list: not given (DEMO_NAME_LIST unset) -> names NOT checked")
    cd = os.environ.get("DEMO_CORPUS_DIR")
    if cd:
        corpus = corpus_shingles(cd)
        print("corpus: %d windows (from DEMO_CORPUS_DIR)" % len(corpus))
    else:
        print("corpus: not given (DEMO_CORPUS_DIR unset) -> 12-character overlap NOT checked")
    n_files = sum(1 for _ in iter_files(root))
    f = scan(root, names, corpus)
    for rel, n, cat, d in f:
        print("FOUND %s:%s [%s] %s" % (rel, n or "-", cat, d))
    print("scanned %d files under the given root; findings: %d" % (n_files, len(f)))
    print("(0 findings is not a guarantee; check git status and the diff by eye as well)")
    return 1 if f else 0


if __name__ == "__main__":
    sys.exit(main())
