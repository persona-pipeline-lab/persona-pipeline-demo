# -*- coding: utf-8 -*-
"""Shared helpers: config loading, file reading, hashing, CSV/JSONL I/O.

No prompt wording is hard-coded here. All texts come from template files
(projects/<project>/templates/) and all settings come from config/demo.yaml
(+ the project's own config.yaml, which is merged on top).
"""
import copy
import csv
import hashlib
import io
import json
import os
import re

import yaml


# ---------------------------------------------------------------- hashing
def sha_bytes(b):
    return hashlib.sha256(b).hexdigest()


def sha_text(s):
    return sha_bytes(s.encode("utf-8"))


def sha_file(path):
    with open(path, "rb") as f:
        return sha_bytes(f.read())


# ---------------------------------------------------------------- reading
def read_text(path):
    """UTF-8 (BOM tolerated), CRLF normalised to LF."""
    with open(path, "rb") as f:
        t = f.read().decode("utf-8-sig")
    return t.replace("\r\n", "\n")


def extract_block(path, heading_prefix):
    """Return the text between the first two `---` lines that follow the
    first `## <heading_prefix>...` heading (leading/trailing newlines removed).
    This is the rule the original study used to extract frozen text."""
    lines = read_text(path).split("\n")
    start = None
    for i, line in enumerate(lines):
        if line.startswith("## ") and line[3:].startswith(heading_prefix):
            start = i
            break
    if start is None:
        raise ValueError("heading '%s' not found in %s" % (heading_prefix, path))
    fences = []
    for j in range(start + 1, len(lines)):
        if lines[j].startswith("## ") and not fences:
            raise ValueError("no fence line after heading '%s'" % heading_prefix)
        if lines[j].strip() == "---":
            fences.append(j)
            if len(fences) == 2:
                break
        elif lines[j].startswith("## ") and len(fences) == 1:
            raise ValueError("fence not closed for heading '%s'" % heading_prefix)
    if len(fences) != 2:
        raise ValueError("two fence lines not found for '%s' in %s" % (heading_prefix, path))
    return "\n".join(lines[fences[0] + 1:fences[1]]).strip("\n")


def split_blocks(text):
    """Split a file that holds several blocks separated by lines that are exactly `---`."""
    parts, cur = [], []
    for line in text.replace("\r\n", "\n").split("\n"):
        if line.strip() == "---":
            parts.append("\n".join(cur).strip("\n"))
            cur = []
        else:
            cur.append(line)
    parts.append("\n".join(cur).strip("\n"))
    return [p for p in parts if p.strip()]


def autobiography_body(text):
    """Return the text from the first `## ` heading onward (front matter and a leading H1 are dropped)."""
    t = text.replace("\r\n", "\n")
    m = re.search(r"^## ", t, re.M)
    if not m:
        raise ValueError("no '## ' heading in the person's text")
    return t[m.start():].strip("\n")


def split_episodes(body):
    """Split a body into episodes, one per `## ` heading (heading line included)."""
    idx = [m.start() for m in re.finditer(r"^## ", body, re.M)]
    if not idx or idx[0] != 0:
        raise ValueError("body must start with a '## ' heading")
    idx.append(len(body))
    return [body[idx[i]:idx[i + 1]].strip("\n") for i in range(len(idx) - 1)]


# ---------------------------------------------------------------- csv / jsonl
def read_csv(path):
    with io.open(path, encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def write_csv(path, header, rows):
    """rows: list of dicts or lists. Written as UTF-8 with BOM so spreadsheets open Japanese text correctly."""
    ensure_dir(os.path.dirname(path))
    with io.open(path, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f, lineterminator="\n")
        w.writerow(header)
        for r in rows:
            w.writerow([r.get(h, "") for h in header] if isinstance(r, dict) else r)


def read_jsonl(path):
    with io.open(path, encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def write_jsonl(path, rows):
    ensure_dir(os.path.dirname(path))
    with io.open(path, "w", encoding="utf-8", newline="\n") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")


def read_json(path):
    with io.open(path, encoding="utf-8") as f:
        return json.load(f)


def write_json(path, obj):
    ensure_dir(os.path.dirname(path))
    with io.open(path, "w", encoding="utf-8", newline="\n") as f:
        json.dump(obj, f, ensure_ascii=False, indent=1)
        f.write("\n")


def write_bytes(path, data):
    ensure_dir(os.path.dirname(path))
    with open(path, "wb") as f:
        f.write(data)


def ensure_dir(path):
    if path:
        os.makedirs(path, exist_ok=True)


def job_filename(job_id, ext):
    """Job ids contain '|', which Windows cannot use in file names."""
    return job_id.replace("|", "__") + ext


# ---------------------------------------------------------------- config
def deep_merge(base, over):
    out = copy.deepcopy(base)
    for k, v in (over or {}).items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = deep_merge(out[k], v)
        else:
            out[k] = copy.deepcopy(v)
    return out


def load_yaml(path):
    with io.open(path, encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def load_config(config_path, project=None):
    """Load config/demo.yaml and merge <project>/config.yaml on top.

    The repository root is the parent of the directory that holds demo.yaml.
    Relative paths in `paths` are resolved against the project directory.
    """
    config_path = os.path.abspath(config_path)
    root = os.path.dirname(os.path.dirname(config_path))
    cfg = load_yaml(config_path)
    proj_rel = project or cfg.get("project")
    if not proj_rel:
        raise ValueError("config has no 'project' entry (use --project)")
    proj_dir = proj_rel if os.path.isabs(proj_rel) else os.path.join(root, proj_rel)
    proj_dir = os.path.normpath(proj_dir)
    pcfg = os.path.join(proj_dir, "config.yaml")
    if os.path.exists(pcfg):
        cfg = deep_merge(cfg, load_yaml(pcfg))
    cfg["_root"] = root
    cfg["_project_dir"] = proj_dir
    cfg["_config_path"] = config_path
    cfg["_project_config_path"] = pcfg if os.path.exists(pcfg) else None
    return cfg


def path_of(cfg, key):
    """Absolute path for an entry of cfg['paths'] (relative to the project directory)."""
    p = cfg["paths"][key]
    return os.path.normpath(p if os.path.isabs(p) else os.path.join(cfg["_project_dir"], p))


def read_persons(cfg):
    rows = read_csv(path_of(cfg, "persons_csv"))
    if not rows:
        raise ValueError("persons.csv has no data rows")
    if "person_id" not in rows[0]:
        raise ValueError("persons.csv needs a 'person_id' column")
    ids = [r["person_id"] for r in rows]
    if len(set(ids)) != len(ids):
        raise ValueError("duplicate person_id in persons.csv")
    return rows


def read_person_text(cfg, person_id):
    p = os.path.join(path_of(cfg, "texts_dir"), person_id + ".md")
    return p, read_text(p)
