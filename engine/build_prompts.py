# -*- coding: utf-8 -*-
"""Step 1: assemble the text to be sent from templates + each person's text.

  sent text = header + [persona block with the person's text] + scenario + questions + output format
              (parts joined by one blank line; the persona block is omitted for C0)

Conditions
  C3        the person's own text
  C0        no persona block at all (identical text for every slot)
  C3W       the next person's text (cyclic shift by one, in persons.csv order)
  C3-mixed  the person's own episodes replaced, one by one, by episodes of other persons
            (see mixed_texts)

Before anything is built, the SHA-256 of every template file is compared with
templates/frozen_hashes.csv. The SHA-256 of every sent text is written to the ledger.
"""
import os
import re
import time

from . import common as C

REQUIRED_CONDITIONS = ("C3", "C0", "C3W", "C3-mixed")


class FrozenHashError(Exception):
    pass


# ------------------------------------------------------------------ templates
def template_files(cfg):
    """All template files that take part in the build, as {logical_name: file_name}."""
    t = cfg["templates"]
    files = {"header": t["header"], "persona": t["persona"], "questions": t["questions"],
             "output_format": t["output_format"], "coding_prompt": t["coding_prompt"],
             "generation_params": t["generation_params"]}
    for s in cfg["scenarios"]:
        files["scenario:" + s["id"]] = s["file"]
    return files


def verify_frozen(cfg):
    """Compare every template file with templates/frozen_hashes.csv. Raises FrozenHashError.
    Returns {file_name: sha256}."""
    tdir = C.path_of(cfg, "templates_dir")
    rec_path = os.path.join(tdir, cfg["templates"]["hashes"])
    if not os.path.exists(rec_path):
        raise FrozenHashError("hash record not found: %s" % rec_path)
    rec = {r["file"]: r["sha256"].strip().lower() for r in C.read_csv(rec_path)}
    bad, out = [], {}
    for logical, fn in template_files(cfg).items():
        p = os.path.join(tdir, fn)
        if fn not in rec:
            bad.append("not in hash record: %s" % fn)
            continue
        if not os.path.exists(p):
            bad.append("missing file: %s" % fn)
            continue
        cur = C.sha_file(p)
        out[fn] = cur
        if cur != rec[fn]:
            bad.append("SHA-256 mismatch: %s (record %s.. file %s..)" % (fn, rec[fn][:12], cur[:12]))
    if bad:
        raise FrozenHashError("template check failed (%d): %s" % (len(bad), "; ".join(bad)))
    return out


def check_params_match_frozen(cfg):
    """config params must equal the frozen generation_params.yaml (temperature, top_p, max_tokens)."""
    fz = C.load_yaml(os.path.join(C.path_of(cfg, "templates_dir"), cfg["templates"]["generation_params"]))
    g = cfg["generation"]["params"]
    bad = [k for k in ("temperature", "top_p", "max_tokens") if g.get(k) != fz.get(k)]
    if bad:
        raise FrozenHashError("config params differ from generation_params.yaml: %s" % ", ".join(bad))


def load_templates(cfg):
    tdir = C.path_of(cfg, "templates_dir")

    def rd(fn):
        return C.read_text(os.path.join(tdir, fn)).strip("\n")
    t = cfg["templates"]
    tpl = {"header": rd(t["header"]), "persona": rd(t["persona"]), "questions": rd(t["questions"]),
           "output_format": rd(t["output_format"]),
           "scenarios": {s["id"]: rd(s["file"]) for s in cfg["scenarios"]}}
    ph = cfg["placeholders"]["persona"]
    if ph not in tpl["persona"]:
        raise ValueError("persona block has no %s placeholder" % ph)
    return tpl


def assemble(cfg, tpl, scenario_id, body=None):
    seq = [tpl["header"]]
    if body is not None:
        seq.append(tpl["persona"].replace(cfg["placeholders"]["persona"], body, 1))
    seq += [tpl["scenarios"][scenario_id], tpl["questions"], tpl["output_format"]]
    return "\n\n".join(seq)


# ------------------------------------------------------------------ people / texts
def load_people(cfg):
    persons = C.read_persons(cfg)
    bodies, files = {}, {}
    for r in persons:
        p, t = C.read_person_text(cfg, r["person_id"])
        bodies[r["person_id"]] = C.autobiography_body(t)
        files[r["person_id"]] = C.sha_file(p)
    return persons, bodies, files


def renumber_heading(episode, n):
    """Replace only the leading number of an episode heading such as '## (3) ...'
    (full-width or half-width parentheses). Headings without a leading number are left as they are."""
    return re.sub(r"^(## )[（(]\d+[）)]", lambda m: "%s（%d）" % (m.group(1), n), episode, count=1)


def mixed_texts(order, bodies):
    """C3-mixed. For each person, every episode (= one '## ' section) of the person's text is
    replaced by one episode of another person's text:
      * the unused episode (within this person's new text) whose character count is closest;
      * ties: the earlier one in (persons.csv order, appearance order);
      * no randomness;
      * the leading number of the heading is renumbered 1..n in the new order.
    Returns ({person_id: new_body}, mapping rows)."""
    eps = {p: C.split_episodes(bodies[p]) for p in order}
    pool = [(p, i, e) for p in order for i, e in enumerate(eps[p])]
    out, rows = {}, []
    for p in order:
        used, new = set(), []
        for i, e in enumerate(eps[p]):
            cands = [(abs(len(c) - len(e)), k) for k, (q, j, c) in enumerate(pool) if q != p and k not in used]
            if not cands:
                raise ValueError("C3-mixed: no unused episode left for %s (need more persons or episodes)" % p)
            _, k = min(cands)
            used.add(k)
            q, j, c = pool[k]
            new.append(renumber_heading(c, i + 1))
            rows.append({"person_id": p, "new_ep_num": i + 1, "source_person": q, "source_ep_index": j + 1,
                         "replaced_ep_index": i + 1, "replaced_chars": len(e), "new_chars": len(c)})
        out[p] = "\n\n".join(new)
    return out, rows


# ------------------------------------------------------------------ ledger
def build_ledger(cfg, now=None):
    """Return (rows, texts, mixed_rows). texts maps job_id -> sent text."""
    gen = cfg["generation"]
    conds = cfg["conditions"]
    for c in conds:
        if c not in REQUIRED_CONDITIONS:
            raise ValueError("unknown condition: %s" % c)
    persons, bodies, text_files = load_people(cfg)
    order = [r["person_id"] for r in persons]
    if "C3W" in conds and len(order) < 2:
        raise ValueError("C3W needs at least two persons")
    shift = {p: order[(i + 1) % len(order)] for i, p in enumerate(order)}
    mixed, mixed_rows = ({}, [])
    if "C3-mixed" in conds:
        mixed, mixed_rows = mixed_texts(order, bodies)
    tpl = load_templates(cfg)
    file_sha = verify_frozen(cfg)
    tmap = cfg["templates"]
    hrec_sha = C.sha_file(os.path.join(C.path_of(cfg, "templates_dir"), tmap["hashes"]))
    p = gen["params"]
    rows, texts, seq = [], {}, 0
    stamp = now or time.strftime("%Y-%m-%dT%H:%M:%S")
    for cond in conds:
        for sc in cfg["scenarios"]:
            for slot, pid in enumerate(order, 1):
                for rep in range(1, cfg["reps"] + 1):
                    seq += 1
                    if cond == "C0":
                        owner, source, body = "", "", None
                        label = "C0slot%02d" % slot
                    else:
                        owner = pid
                        label = pid
                        if cond == "C3":
                            source, body = pid, bodies[pid]
                        elif cond == "C3W":
                            source, body = shift[pid], bodies[shift[pid]]
                        else:
                            source, body = "mixed", mixed[pid]
                    job_id = "%s|%s|%s|%d" % (label, cond, sc["id"], rep)
                    text = assemble(cfg, tpl, sc["id"], body)
                    texts[job_id] = text
                    rows.append({
                        "seq": seq, "job_id": job_id, "person_id": owner, "slot": slot, "condition": cond,
                        "scenario": sc["id"], "rep": rep, "model": gen["model"], "source_person": source,
                        "body_sha256": C.sha_text(body) if body is not None else "",
                        "body_chars": len(body) if body is not None else 0,
                        "parts": {"header": file_sha[tmap["header"]],
                                  "persona": file_sha[tmap["persona"]] if body is not None else "",
                                  "scenario": file_sha[sc["file"]], "questions": file_sha[tmap["questions"]],
                                  "output_format": file_sha[tmap["output_format"]]},
                        "sent_sha256": C.sha_text(text), "sent_chars": len(text),
                        "built_path": "built/" + C.job_filename(job_id, ".txt"),
                        "params": {"temperature": p["temperature"], "top_p": p["top_p"], "max_tokens": p["max_tokens"],
                                   "seed": p["seed_base"] * 100 + rep, "reasoning_effort": p.get("reasoning_effort")},
                        "frozen_hash_record_sha256": hrec_sha, "built_at": stamp,
                    })
    ids = [r["job_id"] for r in rows]
    assert len(ids) == len(set(ids)), "duplicate job_id"
    return rows, texts, mixed_rows


def build(cfg, out_dir):
    """Assert frozen hashes, build all sent texts, write ledger + built/ + mixed mapping."""
    check_params_match_frozen(cfg)
    rows, texts, mixed_rows = build_ledger(cfg)
    for r in rows:
        C.write_bytes(os.path.join(out_dir, r["built_path"]), texts[r["job_id"]].encode("utf-8"))
    C.write_jsonl(os.path.join(out_dir, "ledger.jsonl"), rows)
    if mixed_rows:
        C.write_csv(os.path.join(out_dir, "mixed_mapping.csv"),
                    ["person_id", "new_ep_num", "source_person", "source_ep_index", "replaced_ep_index",
                     "replaced_chars", "new_chars"], mixed_rows)
    uniq = len({r["sent_sha256"] for r in rows})
    print("built %d texts (%d unique SHA-256) -> %s" % (len(rows), uniq, out_dir))
    return rows
