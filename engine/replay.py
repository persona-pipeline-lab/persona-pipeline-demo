# -*- coding: utf-8 -*-
"""Replay mode (no model needed) and the manifest.

replay():  uses the saved answers in outputs_example/ and runs
           manifest check -> build (hash check) -> rebuilt-vs-saved comparison -> acceptance
           -> read saved coding results -> dataset -> audit.
snapshot(): copies a finished run (outputs/) to outputs_example/ and writes manifest.json.

manifest.json records the SHA-256 of the templates, the people's texts, persons.csv and the
generation-relevant part of the config, plus the generation/coding model and time stamps.
If any of them differs from the current file, replay stops before doing anything else
(when a text is edited, the saved answers must be regenerated).
"""
import glob
import json
import os
import platform
import shutil
import sys
import tempfile
import time

from . import accept, audit, build_dataset, build_prompts
from . import common as C
from .code_outputs import coding_section

SNAPSHOT_ITEMS = ["ledger.jsonl", "mixed_mapping.csv", "sent", "generated", "coding", "acceptance.csv", "rejects.csv",
                  "acceptance_summary.csv", "dataset_A.csv", "dataset_B.csv", "dataset_NOTICE.txt", "audit_report.txt",
                  "audit_report_rows.csv"]


def config_subset(cfg):
    sec, cparams = coding_section(cfg)
    return {"conditions": cfg["conditions"], "reps": cfg["reps"], "scenarios": cfg["scenarios"],
            "generation_model": cfg["generation"]["model"], "generation_params": cfg["generation"]["params"],
            "accept": cfg["accept"], "coding_blocks": cfg["coding"]["blocks"], "coding_model": sec["model"],
            "coding_params": {k: v for k, v in cparams.items()}, "placeholders": cfg["placeholders"],
            "templates": cfg["templates"]}


def current_hashes(cfg):
    tdir = C.path_of(cfg, "templates_dir")
    tpl = {fn: C.sha_file(os.path.join(tdir, fn)) for fn in sorted(set(build_prompts.template_files(cfg).values()))}
    tpl[cfg["templates"]["hashes"]] = C.sha_file(os.path.join(tdir, cfg["templates"]["hashes"]))
    persons = C.read_persons(cfg)
    texts = {}
    for r in persons:
        p, _ = C.read_person_text(cfg, r["person_id"])
        texts[r["person_id"]] = C.sha_file(p)
    return {"templates": tpl, "persons_csv": C.sha_file(C.path_of(cfg, "persons_csv")), "texts": texts,
            "config_subset_sha256": C.sha_text(json.dumps(config_subset(cfg), sort_keys=True, ensure_ascii=False))}


def make_manifest(cfg, out_dir):
    h = current_hashes(cfg)
    gens = [C.read_json(p) for p in sorted(glob.glob(os.path.join(out_dir, "generated", "*.json")))]
    sec, cparams = coding_section(cfg)
    stamps = sorted(g["timestamp_requested"] for g in gens) if gens else []
    return {
        "manifest_version": 1,
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "templates": h["templates"], "persons_csv": h["persons_csv"], "texts": h["texts"],
        "config_subset_sha256": h["config_subset_sha256"],
        "generation": {"model": cfg["generation"]["model"],
                       "actual_model_ids": sorted({g["actual_model"] for g in gens if g.get("actual_model")}),
                       "endpoint_kind": cfg["generation"].get("endpoint_kind", ""),
                       "reasoning_effort": cfg["generation"]["params"].get("reasoning_effort"),
                       "params": {k: cfg["generation"]["params"][k] for k in ("temperature", "top_p", "max_tokens", "seed_base")},
                       "n_records": len(gens), "first_request": stamps[0] if stamps else "", "last_request": stamps[-1] if stamps else ""},
        "coding": {"model": sec["model"], "endpoint_kind": sec.get("endpoint_kind") or "",
                   "same_as_generation": sec["same_as_generation"], "blocks": [b["name"] for b in cfg["coding"]["blocks"]]},
        "python": platform.python_version(),
    }


def verify_manifest(cfg, manifest):
    """Return a list of differences between the manifest and the current files (empty = consistent)."""
    h = current_hashes(cfg)
    diff = []
    for fn, sha in manifest["templates"].items():
        cur = h["templates"].get(fn)
        if cur != sha:
            diff.append("template %s: manifest %s.. current %s.." % (fn, sha[:12], (cur or "missing")[:12]))
    for fn in h["templates"]:
        if fn not in manifest["templates"]:
            diff.append("template %s is not in the manifest" % fn)
    if manifest["persons_csv"] != h["persons_csv"]:
        diff.append("persons.csv differs")
    for pid, sha in manifest["texts"].items():
        if h["texts"].get(pid) != sha:
            diff.append("text %s differs or is missing" % pid)
    for pid in h["texts"]:
        if pid not in manifest["texts"]:
            diff.append("text %s is not in the manifest" % pid)
    if manifest["config_subset_sha256"] != h["config_subset_sha256"]:
        diff.append("generation-relevant config differs")
    return diff


def snapshot(cfg, out_dir, example_dir):
    """Copy a finished run to outputs_example/ and write manifest.json."""
    if os.path.exists(example_dir):
        shutil.rmtree(example_dir)
    C.ensure_dir(example_dir)
    for item in SNAPSHOT_ITEMS:
        src = os.path.join(out_dir, item)
        if os.path.isdir(src):
            shutil.copytree(src, os.path.join(example_dir, item))
        elif os.path.exists(src):
            shutil.copy2(src, os.path.join(example_dir, item))
    m = make_manifest(cfg, out_dir)
    C.write_json(os.path.join(example_dir, "manifest.json"), m)
    print("snapshot written to %s (manifest.json with %d template hashes, %d text hashes)"
          % (example_dir, len(m["templates"]), len(m["texts"])))
    return m


def _same_file(a, b):
    return os.path.exists(a) and os.path.exists(b) and C.sha_file(a) == C.sha_file(b)


def replay(cfg, example_dir=None, workdir=None):
    """Run the whole pipeline on saved answers. Returns True when every check passed."""
    example_dir = example_dir or C.path_of(cfg, "example_dir")
    mpath = os.path.join(example_dir, "manifest.json")
    if not os.path.exists(mpath):
        print("[replay] STOP: %s not found" % mpath)
        return False
    workdir = workdir or tempfile.mkdtemp(prefix="demo_replay_")
    C.ensure_dir(workdir)
    print("[replay] example: %s\n[replay] workdir: %s" % (example_dir, workdir))
    ok = True

    # 1. manifest against the current files (before anything else)
    diff = verify_manifest(cfg, C.read_json(mpath))
    if diff:
        print("[replay] STOP: manifest does not match the current files (%d):" % len(diff))
        for d in diff:
            print("  - " + d)
        print("[replay] If you edited a text or a template, the saved answers must be regenerated.")
        return False
    print("[replay] manifest check: OK (templates, persons.csv, %d texts, config subset)"
          % len(C.read_json(mpath)["texts"]))

    # 2. build from templates (frozen-hash assertion inside) and compare with the saved ledger
    build_prompts.build(cfg, workdir)
    fresh = C.read_jsonl(os.path.join(workdir, "ledger.jsonl"))
    saved_path = os.path.join(example_dir, "ledger.jsonl")
    if os.path.exists(saved_path):
        saved = {r["job_id"]: r["sent_sha256"] for r in C.read_jsonl(saved_path)}
        same = sum(1 for r in fresh if saved.get(r["job_id"]) == r["sent_sha256"])
        print("[replay] rebuilt texts whose SHA-256 equals the saved ledger: %d / %d (saved ledger has %d rows)"
              % (same, len(fresh), len(saved)))
        ok = ok and same == len(fresh) == len(saved)

    # 3. acceptance (rejects are printed first)
    accept.run(cfg, os.path.join(workdir, "ledger.jsonl"), os.path.join(example_dir, "generated"), workdir)

    # 4. saved coding results -> dataset
    build_dataset.run(cfg, workdir, coding_dir=example_dir, dataset_dir=workdir)
    for name in ("dataset_A.csv", "dataset_B.csv"):
        ex = os.path.join(example_dir, name)
        if os.path.exists(ex):
            same = _same_file(os.path.join(workdir, name), ex)
            print("[replay] %s identical to the saved example: %s" % (name, "yes" if same else "NO"))
            ok = ok and same

    # 5. audit: fresh ledger vs the saved sent files and saved output records
    a_ok, _ = audit.run(cfg, os.path.join(workdir, "ledger.jsonl"), os.path.join(example_dir, "sent"),
                        os.path.join(example_dir, "generated"), os.path.join(workdir, "audit_report.txt"))
    ok = ok and a_ok
    print("[replay] RESULT = %s" % ("OK" if ok else "NOT OK"))
    return ok
